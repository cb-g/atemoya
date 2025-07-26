open Unix
open Printf

let setup_logging (tickers : string list) : unit =
  let now = Unix.localtime (Unix.time ()) in
  let timestamp =
    sprintf "%04d-%02d-%02d_%02d-%02d-%02d"
      (1900 + now.tm_year)
      (now.tm_mon + 1)
      now.tm_mday
      now.tm_hour
      now.tm_min
      now.tm_sec
  in
  let joined_tickers = String.concat "_" tickers in
  let filename = sprintf "log/val/dcf_probabilistic/IVPS_%s_%s.log" timestamp joined_tickers in

  ignore (Sys.command "mkdir -p log/val/dcf_probabilistic");
  let log_fd = Unix.openfile filename [O_WRONLY; O_CREAT; O_TRUNC] 0o644 in
  ignore (Unix.dup2 log_fd Unix.stdout);
  ignore (Unix.dup2 log_fd Unix.stderr);

  printf "[INFO] Logging to: %s\n%!" filename

let classify_relation ivps price =
  let tolerance = 0.05 *. price in
  if ivps > price +. tolerance then "undervalued"
  else if ivps < price -. tolerance then "overvalued"
  else "fairly valued"

let calculate_margin_of_safety ivps price =
  (ivps -. price) /. price *. 100.0

let mean lst =
  let n = float_of_int (List.length lst) in
  List.fold_left ( +. ) 0.0 lst /. n

let stddev lst =
  let m = mean lst in
  let n = float_of_int (List.length lst) in
  let var = List.fold_left (fun acc x -> acc +. (x -. m) ** 2.0) 0.0 lst /. n in
  sqrt var

let minmax lst =
  match lst with
  | [] -> nan, nan
  | x :: xs -> List.fold_left (fun (lo, hi) v -> (min lo v, max hi v)) (x, x) xs

let split4 lst =
    let rec aux l (a, b, c, d) =
      match l with
      | [] -> (List.rev a, List.rev b, List.rev c, List.rev d)
      | (x1, x2, x3, x4) :: xs -> aux xs (x1 :: a, x2 :: b, x3 :: c, x4 :: d)
    in
    aux lst ([], [], [], [])

let () =
  let filename = "data/val/dcf/input_for_probabilistic.json" in
  let inputs = Atemoya.Dcf_probabilistic.load_inputs filename in
  let tickers = List.map fst inputs in
  setup_logging tickers;

  let csv_out = open_out "data/val/dcf/output_of_probabilistic.csv" in
  fprintf csv_out "ticker,price,ivps_fcfe,ivps_fcff,mos_fcfe,mos_fcff,std_fcfe,std_fcff,fcfe_distribution,fcff_distribution\n%!";

  List.iter (fun (tkr, input) ->
    let n = 1000 in
    Printf.printf "[%s] Running %d FCFE simulations...\n%!" tkr n;
    let fcfe_vals = Atemoya.Dcf_probabilistic.run_monte_carlo input ~n ~fcfe:true in
    let mean_fcfe = List.fold_left ( +. ) 0.0 fcfe_vals /. float_of_int n in
    let std_fcfe = stddev fcfe_vals in
    let min_fcfe, max_fcfe = minmax fcfe_vals in
    Printf.printf "[%s] FCFE Monte Carlo → mean valuation: %.2f\n%!" tkr mean_fcfe;

    Printf.printf "[%s] Running %d FCFF simulations...\n%!" tkr n;
    let fcff_vals = Atemoya.Dcf_probabilistic.run_monte_carlo input ~n ~fcfe:false in
    let mean_fcff = List.fold_left ( +. ) 0.0 fcff_vals /. float_of_int n in
    let std_fcff = stddev fcff_vals in
    let min_fcff, max_fcff = minmax fcff_vals in
    Printf.printf "[%s] FCFF Monte Carlo → mean valuation: %.2f\n%!" tkr mean_fcff;

    let ivps_fcfe = mean_fcfe in  (* already per-share from run_monte_carlo *) 
    let ivps_fcff = mean_fcff -. (input.mvb /. input.so) in  (* subtract per-share debt *)
    Printf.printf "[%s] IVPS (FCFE-based): %.2f\n%!" tkr ivps_fcfe;
    Printf.printf "[%s] IVPS (FCFF-based): %.2f\n%!" tkr ivps_fcff;

    let price = input.mve /. input.so in  (* market price per share *)

    let fcfe_class = classify_relation ivps_fcfe price in
    let fcff_class = classify_relation ivps_fcff price in

    let mos_fcfe = calculate_margin_of_safety ivps_fcfe price in
    let mos_fcff = calculate_margin_of_safety ivps_fcff price in

    Printf.printf "\n------------------------------------------------------------\n%!";
    Printf.printf "[%s] Probabilistic Valuation Summary\n" tkr;
    Printf.printf "------------------------------------------------------------\n%!";
    Printf.printf "→ Market Price       : %.2f %s\n" price input.currency;
    Printf.printf "→ IVPS (FCFE-based)  : %.2f (%s); Margin of Safety: %.2f%%\n"
      ivps_fcfe fcfe_class mos_fcfe;
    Printf.printf "→ IVPS (FCFF-based)  : %.2f (%s); Margin of Safety: %.2f%%\n"
      ivps_fcff fcff_class mos_fcff;

    (* Basic recommendation logic *)
    let signal =
      match (fcfe_class, fcff_class) with
      | ("undervalued", "undervalued") -> "Strong Buy – Both cash flow bases suggest upside."
      | ("undervalued", "fairly valued")
      | ("fairly valued", "undervalued") -> "Buy – One base undervalued, the other consistent."
      | ("overvalued", "overvalued") -> "Avoid – Both signals suggest overpricing."
      | _ -> "Hold – Mixed or neutral signals; price mostly reflects fundamentals."
    in

    Printf.printf "→ FCFE Valuation Stats:\n";
    Printf.printf "     Mean: %.2f | Stddev: %.2f | Min: %.2f | Max: %.2f\n"
      mean_fcfe std_fcfe min_fcfe max_fcfe;
    Printf.printf "→ FCFF Valuation Stats:\n";
    Printf.printf "     Mean: %.2f | Stddev: %.2f | Min: %.2f | Max: %.2f\n"
      mean_fcff std_fcff min_fcff max_fcff;

    Printf.printf "→ Signal             : %s\n%!" signal;
    Printf.printf "------------------------------------------------------------\n\n%!";

    fprintf csv_out "%s,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%s,%s\n%!"
      tkr price ivps_fcfe ivps_fcff mos_fcfe mos_fcff std_fcfe std_fcff
      "gaussian" "gaussian";

  ) inputs;

  close_out csv_out;


  (* === save simulation matrix for plotting === *)
  let n = 1000 in

  let results =
    List.map (fun (tkr, input) ->
      let sims_fcfe = Atemoya.Dcf_probabilistic.run_monte_carlo input ~n ~fcfe:true in
      let sims_fcff = Atemoya.Dcf_probabilistic.run_monte_carlo input ~n ~fcfe:false in
      let price = input.mve /. input.so in
      (tkr, sims_fcfe, sims_fcff, price)
    ) inputs
  in

  let tickers, sim_matrix_fcfe, sim_matrix_fcff, prices =
    split4 results
  in

  let rec transpose matrix =
    match matrix with
    | [] | [] :: _ -> []
    | _ -> List.map List.hd matrix :: transpose (List.map List.tl matrix)
  in

  let sim_matrix_fcfe_t = transpose sim_matrix_fcfe in
  let sim_matrix_fcff_t = transpose sim_matrix_fcff in

  (* save FCFE simulations *)
  let oc_fcfe = open_out "data/val/dcf/output_simulations_fcfe.csv" in
  Printf.fprintf oc_fcfe "%s\n%!" (String.concat "," tickers);
  List.iter (fun row ->
    Printf.fprintf oc_fcfe "%s\n%!" (String.concat "," (List.map string_of_float row))
  ) sim_matrix_fcfe_t;
  close_out oc_fcfe;

  (* save FCFF simulations *)
  let oc_fcff = open_out "data/val/dcf/output_simulations_fcff.csv" in
  Printf.fprintf oc_fcff "%s\n%!" (String.concat "," tickers);
  List.iter (fun row ->
    Printf.fprintf oc_fcff "%s\n%!" (String.concat "," (List.map string_of_float row))
  ) sim_matrix_fcff_t;
  close_out oc_fcff;

  (* save prices *)
  let oc_price = open_out "data/val/dcf/market_prices.csv" in
  Printf.fprintf oc_price "ticker,price\n%!";
  List.iter2 (fun tkr price ->
    Printf.fprintf oc_price "%s,%.2f\n%!" tkr price
  ) tickers prices;
  close_out oc_price;

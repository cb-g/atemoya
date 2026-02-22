(** Perpetual futures pricing CLI.

    Usage:
      perpetual_futures --spot 50000 --kappa 0.001 --type linear
      perpetual_futures --data market_data.json --r_a 0.05 --r_b 0.0
      perpetual_futures --option call --strike 50000 --spot 48000 --sigma 0.8
*)

open Perpetual_futures

let () =
  let spot = ref 0.0 in
  let kappa = ref 0.001 in  (* Default: ~1000 mean maturity *)
  let iota = ref 0.0 in
  let r_a = ref 0.05 in     (* USD risk-free rate *)
  let r_b = ref 0.0 in      (* Crypto "rate" *)
  let r_c = ref None in     (* Third currency rate for quanto *)
  let sigma_x = ref 0.8 in  (* Volatility *)
  let sigma_z = ref None in
  let rho = ref 1.0 in
  let contract_type = ref "linear" in
  let data_file = ref "" in
  let output_file = ref "" in

  (* Everlasting option params *)
  let option_mode = ref false in
  let option_type = ref "call" in
  let strike = ref 0.0 in

  (* Option grid mode *)
  let grid_mode = ref false in
  let spot_min = ref 0.0 in
  let spot_max = ref 0.0 in
  let n_points = ref 100 in

  let usage = "perpetual_futures - Price perpetual futures and everlasting options\n\n" ^
              "Usage:\n" ^
              "  perpetual_futures --spot <price> --kappa <rate> [options]\n" ^
              "  perpetual_futures --option <call|put> --strike <K> --spot <S> --sigma <vol>\n" ^
              "  perpetual_futures --grid --strike <K> --spot-min <min> --spot-max <max>\n\n" ^
              "Options:" in

  let speclist = [
    ("--spot", Arg.Set_float spot, " Spot price");
    ("--kappa", Arg.Set_float kappa, " Premium rate (anchoring intensity)");
    ("--iota", Arg.Set_float iota, " Interest factor");
    ("--r_a", Arg.Set_float r_a, " Quote currency risk-free rate (default: 0.05)");
    ("--r_b", Arg.Set_float r_b, " Base currency risk-free rate (default: 0.0)");
    ("--r_c", Arg.Float (fun f -> r_c := Some f), " Third currency rate (quanto only)");
    ("--sigma", Arg.Set_float sigma_x, " Volatility (default: 0.8)");
    ("--sigma_z", Arg.Float (fun f -> sigma_z := Some f), " Third currency volatility (quanto)");
    ("--rho", Arg.Set_float rho, " Correlation (quanto, default: 1.0)");
    ("--type", Arg.Set_string contract_type, " Contract type: linear, inverse, quanto");
    ("--data", Arg.Set_string data_file, " Market data JSON file");
    ("--output", Arg.Set_string output_file, " Output JSON file");
    ("--option", Arg.String (fun s -> option_mode := true; option_type := s), " Price everlasting option (call/put)");
    ("--strike", Arg.Set_float strike, " Option strike price");
    ("--grid", Arg.Set grid_mode, " Generate option price grid");
    ("--spot-min", Arg.Set_float spot_min, " Min spot for grid");
    ("--spot-max", Arg.Set_float spot_max, " Max spot for grid");
    ("--n-points", Arg.Set_int n_points, " Number of grid points (default: 100)");
  ] in

  Arg.parse speclist (fun _ -> ()) usage;

  (* Everlasting option grid mode *)
  if !grid_mode then begin
    if !strike <= 0.0 then begin
      Printf.eprintf "Error: --strike required for grid mode\n";
      exit 1
    end;
    if !spot_min <= 0.0 || !spot_max <= 0.0 then begin
      Printf.eprintf "Error: --spot-min and --spot-max required for grid mode\n";
      exit 1
    end;

    let step = (!spot_max -. !spot_min) /. float_of_int (!n_points - 1) in
    let spots = List.init !n_points (fun i -> !spot_min +. float_of_int i *. step) in

    let grid = Everlasting.option_price_grid
      ~kappa:!kappa ~r_a:!r_a ~r_b:!r_b ~sigma:!sigma_x
      ~strike:!strike ~spots in

    let output = if !output_file <> "" then !output_file
                 else "pricing/perpetual_futures/output/option_grid.csv" in
    Io.write_option_grid output grid;
    Printf.printf "Option grid written to %s\n" output;
    exit 0
  end;

  (* Everlasting option mode *)
  if !option_mode then begin
    if !spot <= 0.0 then begin
      Printf.eprintf "Error: --spot required for option pricing\n";
      exit 1
    end;
    if !strike <= 0.0 then begin
      Printf.eprintf "Error: --strike required for option pricing\n";
      exit 1
    end;

    let opt_type = match !option_type with
      | "call" | "Call" -> Types.Call
      | "put" | "Put" -> Types.Put
      | _ ->
          Printf.eprintf "Error: option type must be 'call' or 'put'\n";
          exit 1
    in

    let opt : Types.everlasting_option = {
      opt_type;
      strike = !strike;
      kappa = !kappa;
      r_a = !r_a;
      r_b = !r_b;
      sigma = !sigma_x;
    } in

    let result = Everlasting.price_option opt ~spot:!spot in
    Io.print_option_result opt_type result;
    exit 0
  end;

  (* Perpetual futures pricing mode *)
  if !spot <= 0.0 && !data_file = "" then begin
    Printf.eprintf "Error: either --spot or --data required\n";
    Arg.usage speclist usage;
    exit 1
  end;

  let ct = match Types.string_to_contract_type !contract_type with
    | Some t -> t
    | None ->
        Printf.eprintf "Error: invalid contract type '%s'\n" !contract_type;
        exit 1
  in

  let pair : Types.currency_pair = {
    base = "BTC";
    quote = "USD";
    terciary = if ct = Quanto then Some "ETH" else None;
  } in

  let rates : Types.interest_rates = {
    r_a = !r_a;
    r_b = !r_b;
    r_c = !r_c;
  } in

  let funding : Types.funding_params = {
    kappa = !kappa;
    iota = !iota;
  } in

  let volatility = if ct = Quanto then
    Some { Types.sigma_x = !sigma_x; sigma_z = !sigma_z; rho_xz = Some !rho }
  else
    None
  in

  let contract : Types.perpetual_contract = {
    contract_type = ct;
    pair;
    rates;
    funding;
    volatility;
  } in

  let spot_price, market_data_opt = if !data_file <> "" then begin
    let market = Io.read_market_data !data_file in
    (market.index_price, Some market)
  end else
    (!spot, None)
  in

  let result = Pricing.price_contract contract ~spot:spot_price in

  Io.print_pricing_dashboard ct result;

  if !output_file <> "" then begin
    (match market_data_opt with
     | Some market ->
         let mispricing = market.mark_price -. result.futures_price in
         let mispricing_pct = if result.futures_price > 0.0 then
           mispricing /. result.futures_price *. 100.0 else 0.0 in
         let signal = if mispricing_pct > 0.1 then "SHORT"
                      else if mispricing_pct < -0.1 then "LONG"
                      else "NEUTRAL" in
         let analysis : Types.analysis_result = {
           market;
           theoretical = result;
           mispricing;
           mispricing_pct;
           arbitrage_signal = signal;
         } in
         Io.write_analysis_result !output_file analysis
     | None ->
         Io.write_pricing_result !output_file result);
    Printf.printf "Results written to %s\n" !output_file
  end

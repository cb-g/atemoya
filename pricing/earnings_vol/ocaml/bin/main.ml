(** Earnings Volatility Scanner - Main CLI *)

open Earnings_vol_lib

let print_header text =
  print_endline "";
  print_endline ("═══ " ^ text ^ " ═══");
  print_endline ""

(** Read CSV data *)
let read_csv filename =
  let ic = open_in filename in
  let _ = input_line ic in  (* Skip header *)
  let lines = ref [] in
  try
    while true do
      lines := input_line ic :: !lines
    done;
    List.rev !lines
  with End_of_file ->
    close_in ic;
    List.rev !lines

(** Parse IV term structure from CSV *)
let parse_term_structure ticker filename =
  let lines = read_csv filename in
  let observations = List.map (fun line ->
    let parts = String.split_on_char ',' line in
    match parts with
    | exp_date :: days :: iv :: strike :: _ ->
        {
          Types.expiration_date = String.trim exp_date;
          days_to_expiry = int_of_string (String.trim days);
          atm_iv = float_of_string (String.trim iv);
          strike = float_of_string (String.trim strike);
        }
    | _ -> failwith "Invalid IV data format"
  ) lines in
  Term_structure.build_term_structure ~ticker ~observations:(Array.of_list observations)

(** Parse earnings event from CSV *)
let parse_earnings filename =
  let lines = read_csv filename in
  match lines with
  | line :: _ ->
      let parts = String.split_on_char ',' line in
      (match parts with
       | ticker :: date :: days :: spot :: vol :: _ ->
           {
             Types.ticker = String.trim ticker;
             earnings_date = String.trim date;
             days_to_earnings = int_of_string (String.trim days);
             spot_price = float_of_string (String.trim spot);
             avg_volume_30d = float_of_string (String.trim vol);
           }
       | _ -> failwith "Invalid earnings data format")
  | [] -> failwith "Empty earnings data"

(** Parse price history *)
let parse_prices filename =
  let lines = read_csv filename in
  Array.of_list (List.map (fun line ->
    let parts = String.split_on_char ',' line in
    match parts with
    | _date :: price :: _ -> float_of_string (String.trim price)
    | _ -> failwith "Invalid price format"
  ) lines)

let () =
  let ticker = ref "SPY" in
  let account_size = ref 10000.0 in
  let fractional_kelly = ref 0.30 in  (* 30% Kelly default *)
  let structure = ref "calendar" in
  
  let usage_msg = "Earnings Volatility Scanner and Position Sizer" in
  let speclist = [
    ("-ticker", Arg.Set_string ticker, "Ticker symbol (default: SPY)");
    ("-account", Arg.Set_float account_size, "Account size (default: 10000)");
    ("-kelly", Arg.Set_float fractional_kelly, "Fractional Kelly (default: 0.30)");
    ("-structure", Arg.Set_string structure, "Structure: straddle|calendar (default: calendar)");
  ] in
  
  Arg.parse speclist (fun _ -> ()) usage_msg;
  
  print_header "Earnings Volatility Scanner";
  
  (* Read data files *)
  let earnings_file = Printf.sprintf "pricing/earnings_vol/data/%s_earnings.csv" !ticker in
  let iv_file = Printf.sprintf "pricing/earnings_vol/data/%s_iv_term.csv" !ticker in
  let prices_file = Printf.sprintf "pricing/earnings_vol/data/%s_prices.csv" !ticker in
  
  let earnings = parse_earnings earnings_file in
  let term_struct = parse_term_structure !ticker iv_file in
  let prices = parse_prices prices_file in
  
  (* Calculate realized volatility *)
  let realized_vol = Term_structure.calculate_realized_vol 
    ~prices 
    ~annualization_factor:252.0 
  in
  
  (* Calculate IV/RV ratio *)
  let iv_rv = Term_structure.calculate_iv_rv_ratio
    ~implied_vol:term_struct.front_month_iv
    ~realized_vol
  in
  
  (* Apply filters *)
  let criteria = Types.default_criteria in
  let filter_result = Filters.apply_filters
    ~term_structure:term_struct
    ~volume:earnings.avg_volume_30d
    ~iv_rv:iv_rv
    ~criteria:criteria
  in
  
  (* Print results *)
  Printf.printf "\nTicker: %s\n" earnings.ticker;
  Printf.printf "Earnings Date: %s\n" earnings.earnings_date;
  Printf.printf "Days to Earnings: %d\n" earnings.days_to_earnings;
  Printf.printf "Spot Price: $%.2f\n" earnings.spot_price;
  
  Printf.printf "\n=== Term Structure ===\n";
  Printf.printf "Front Month IV: %.2f%%\n" (term_struct.front_month_iv *. 100.0);
  Printf.printf "Back Month IV (45d): %.2f%%\n" (term_struct.back_month_iv *. 100.0);
  Printf.printf "Term Slope: %.4f\n" term_struct.term_structure_slope;
  Printf.printf "Term Ratio: %.2f\n" term_struct.term_structure_ratio;
  
  Printf.printf "\n=== IV vs RV ===\n";
  Printf.printf "Implied Vol (30d): %.2f%%\n" (iv_rv.implied_vol_30d *. 100.0);
  Printf.printf "Realized Vol (30d): %.2f%%\n" (iv_rv.realized_vol_30d *. 100.0);
  Printf.printf "IV/RV Ratio: %.2f\n" iv_rv.iv_rv_ratio;
  
  Filters.print_filter_result filter_result;
  
  (* Position sizing if recommended or consider *)
  if filter_result.recommendation <> "Avoid" then begin
    let premium = earnings.spot_price *. term_struct.front_month_iv *. 0.10 in
    let sizing = match !structure with
      | "straddle" -> 
          Kelly_sizing.size_straddle 
            ~account_size:!account_size
            ~fractional_kelly:!fractional_kelly
            ~straddle_premium:premium
      | _ ->
          Kelly_sizing.size_calendar
            ~account_size:!account_size
            ~fractional_kelly:!fractional_kelly
            ~calendar_debit:premium
    in
    Kelly_sizing.print_kelly_sizing sizing
  end;
  
  print_endline "\n✓ Analysis complete"

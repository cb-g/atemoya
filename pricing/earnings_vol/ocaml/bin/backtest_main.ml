(** Historical Backtest Runner *)

open Earnings_vol_lib

(** Read CSV helper *)
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

(** Parse historical event from CSV line *)
let parse_historical_event line =
  let parts = String.split_on_char ',' line in
  match parts with
  | ticker :: earnings_date :: pre_close :: post_open :: post_close ::
    avg_volume :: rv :: implied_vol :: front_iv :: back_iv :: term_slope ::
    iv_rv_ratio :: _ ->
      Some {
        Backtest.ticker = String.trim ticker;
        earnings_date = String.trim earnings_date;
        pre_close = float_of_string (String.trim pre_close);
        post_open = float_of_string (String.trim post_open);
        post_close = float_of_string (String.trim post_close);
        avg_volume_30d = float_of_string (String.trim avg_volume);
        rv_30d = float_of_string (String.trim rv);
        implied_vol_30d = float_of_string (String.trim implied_vol);
        front_month_iv = float_of_string (String.trim front_iv);
        back_month_iv = float_of_string (String.trim back_iv);
        term_slope = float_of_string (String.trim term_slope);
        iv_rv_ratio = float_of_string (String.trim iv_rv_ratio);
      }
  | _ -> None

(** Write trade results to CSV *)
let write_trade_results filename trades =
  let oc = open_out filename in
  Printf.fprintf oc "ticker,earnings_date,position_type,return_pct,stock_move_pct,passed_filters\n";

  Array.iter (fun (trade : Backtest.trade_result) ->
    let pos_type = match trade.position_type with
      | Types.LongCalendar -> "LongCalendar"
      | Types.ShortStraddle -> "ShortStraddle"
    in
    Printf.fprintf oc "%s,%s,%s,%.4f,%.4f,%b\n"
      trade.ticker
      trade.earnings_date
      pos_type
      trade.return_pct
      trade.stock_move_pct
      trade.passed_filters
  ) trades;

  close_out oc

let () =
  let structure = ref "calendar" in
  let input_file = ref "pricing/earnings_vol/data/backtest/historical_combined.csv" in
  let output_file = ref "pricing/earnings_vol/data/backtest/backtest_results.csv" in

  let usage_msg = "Historical Backtest for Earnings Volatility Strategy" in
  let speclist = [
    ("-structure", Arg.Set_string structure, "Structure: straddle|calendar (default: calendar)");
    ("-input", Arg.Set_string input_file, "Input CSV file with historical data");
    ("-output", Arg.Set_string output_file, "Output CSV file for results");
  ] in

  Arg.parse speclist (fun _ -> ()) usage_msg;

  Printf.printf "\n═══ Earnings Volatility Backtest ═══\n";
  Printf.printf "Structure: %s\n" !structure;
  Printf.printf "Input: %s\n" !input_file;

  (* Read historical events *)
  let lines = read_csv !input_file in
  let events = List.filter_map parse_historical_event lines in
  let events_array = Array.of_list events in

  Printf.printf "Loaded %d historical events\n" (Array.length events_array);

  (* Determine position type *)
  let position_type = match !structure with
    | "straddle" -> Types.ShortStraddle
    | _ -> Types.LongCalendar
  in

  (* Run backtest *)
  let criteria = Types.default_criteria in

  let trade_results = Array.map (fun event ->
    Backtest.simulate_trade ~event ~position_type ~criteria
  ) events_array in

  (* Calculate years spanned by the backtest *)
  let years =
    if Array.length events_array < 2 then 1.0
    else
      let first_date = events_array.(0).Backtest.earnings_date in
      let last_date = events_array.(Array.length events_array - 1).Backtest.earnings_date in
      (* Parse YYYY-MM-DD dates to approximate year span *)
      let parse_year_frac s =
        try
          let y = float_of_string (String.sub s 0 4) in
          let m = float_of_string (String.sub s 5 2) in
          let d = float_of_string (String.sub s 8 2) in
          y +. (m -. 1.0) /. 12.0 +. (d -. 1.0) /. 365.0
        with _ -> 0.0
      in
      let span = parse_year_frac last_date -. parse_year_frac first_date in
      if span > 0.0 then span else 1.0
  in

  Printf.printf "Backtest span: %.2f years\n" years;

  (* Calculate statistics *)
  let stats = Backtest.calculate_stats
    ~trades:trade_results
    ~total_events:(Array.length events_array)
    ~years
  in

  (* Print results *)
  Backtest.print_stats stats !structure;

  (* Save trade results *)
  write_trade_results !output_file trade_results;
  Printf.printf "\n✓ Trade results saved: %s\n" !output_file

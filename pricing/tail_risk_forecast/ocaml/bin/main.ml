(** Tail Risk Forecasting CLI

    Usage:
      tail_risk_forecast --ticker AAPL
      tail_risk_forecast --ticker AAPL --json
      tail_risk_forecast --data path/to/intraday.json
*)

open Tail_risk_forecast

let () =
  let ticker = ref "" in
  let data_path = ref "" in
  let output_json = ref false in
  let jump_threshold = ref Jump_detection.default_threshold in

  let specs = [
    ("--ticker", Arg.Set_string ticker, "Ticker symbol (e.g., AAPL)");
    ("--data", Arg.Set_string data_path, "Path to intraday data JSON");
    ("--json", Arg.Set output_json, "Output JSON instead of console");
    ("--jump-threshold", Arg.Set_float jump_threshold, "Jump detection threshold (default: 2.5 std devs)");
  ] in

  let usage = "tail_risk_forecast --ticker SYMBOL [--json]" in
  Arg.parse specs (fun _ -> ()) usage;

  (* Determine data path *)
  let input_path =
    if !data_path <> "" then !data_path
    else if !ticker <> "" then
      Printf.sprintf "pricing/tail_risk_forecast/data/intraday_%s.json" !ticker
    else begin
      Printf.eprintf "Error: Must specify --ticker or --data\n";
      exit 1
    end
  in

  let ticker_name = if !ticker <> "" then !ticker else "UNKNOWN" in

  (* Load data *)
  match Io.read_intraday_data input_path with
  | None ->
    Printf.eprintf "Error: Could not read data from %s\n" input_path;
    Printf.eprintf "Run: python pricing/tail_risk_forecast/python/fetch/fetch_intraday.py --ticker %s\n" ticker_name;
    exit 1
  | Some data ->
    let ticker_name = if data.ticker <> "" then data.ticker else ticker_name in

    (* Compute realized variance series *)
    let rv_series = Realized_variance.compute_rv_series data in

    if Array.length rv_series < Har_rv.min_observations then begin
      Printf.eprintf "Error: Need at least %d observations, got %d\n"
        Har_rv.min_observations (Array.length rv_series);
      exit 1
    end;

    (* Estimate HAR model *)
    let har_model = Har_rv.estimate_har rv_series in

    (* Detect jumps *)
    let jumps = Jump_detection.detect_all_jumps ~threshold:!jump_threshold rv_series in

    (* Generate forecast *)
    let forecast = Var_forecast.forecast_tail_risk har_model rv_series jumps in

    (* Build result *)
    let now = Unix.gettimeofday () in
    let tm = Unix.localtime now in
    let analysis_date = Printf.sprintf "%04d-%02d-%02d"
      (tm.Unix.tm_year + 1900) (tm.Unix.tm_mon + 1) tm.Unix.tm_mday in

    let result : Types.analysis_result = {
      ticker = ticker_name;
      analysis_date;
      rv_series;
      har_model;
      recent_jumps = jumps;
      forecast;
    } in

    (* Output *)
    if !output_json then begin
      let output_path = Printf.sprintf "pricing/tail_risk_forecast/output/forecast_%s.json" ticker_name in
      Io.write_result_json output_path result;
      Printf.printf "Results written to %s\n" output_path
    end else
      Io.print_forecast result

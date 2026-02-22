(** Main CLI for dividend income analysis *)

open Dividend_income

(** Analyze a single ticker *)
let analyze_ticker ~data_dir ~output_dir ~ddm_params ticker =
  let data_file = Filename.concat data_dir (Printf.sprintf "dividend_data_%s.json" ticker) in

  if not (Sys.file_exists data_file) then begin
    Printf.eprintf "Data file not found: %s\n" data_file;
    Printf.eprintf "Run Python fetcher first: uv run valuation/dividend_income/python/fetch/fetch_dividend_data.py --ticker %s\n" ticker;
    None
  end else begin
    Printf.printf "Analyzing %s...\n" ticker;

    (* Read data *)
    let data = Io.read_dividend_data data_file in

    (* Calculate metrics *)
    let dividend_metrics = Dividend_metrics.calculate_metrics data in
    let growth_metrics = Dividend_metrics.calculate_growth_metrics data in
    let ddm_valuation = Ddm.calculate_ddm_valuation data ddm_params in
    let safety_score = Safety_scoring.calculate_safety_score data in
    let signal = Safety_scoring.determine_signal data safety_score ddm_valuation in

    (* Build result *)
    let result : Types.dividend_result = {
      ticker = data.ticker;
      company_name = data.company_name;
      sector = data.sector;
      current_price = data.current_price;
      dividend_metrics;
      growth_metrics;
      ddm_valuation;
      safety_score;
      signal;
    } in

    (* Write result *)
    let output_file = Filename.concat output_dir (Printf.sprintf "dividend_result_%s.json" ticker) in
    Io.write_result output_file result;
    Printf.printf "Result written to: %s\n" output_file;

    (* Print to stdout *)
    Io.print_result result;

    Some result
  end

(** Run Python data fetcher *)
let run_fetcher ~python_cmd ~ticker ~output_dir =
  let cmd = Printf.sprintf "%s valuation/dividend_income/python/fetch/fetch_dividend_data.py --ticker %s --output %s"
    python_cmd ticker output_dir in
  let exit_code = Sys.command cmd in
  if exit_code <> 0 then
    Printf.eprintf "Warning: Python fetcher failed for %s\n" ticker

(** Main entry point *)
let () =
  let ticker = ref "" in
  let tickers = ref "" in
  let data_dir = ref "valuation/dividend_income/data" in
  let output_dir = ref "valuation/dividend_income/output" in
  let python_cmd = ref "" in
  let do_compare = ref false in
  let required_return = ref 0.08 in
  let terminal_growth = ref 0.03 in

  let specs = [
    ("--ticker", Arg.Set_string ticker, "Single ticker to analyze");
    ("--tickers", Arg.Set_string tickers, "Comma-separated list of tickers");
    ("--data", Arg.Set_string data_dir, "Data directory (default: valuation/dividend_income/data)");
    ("--output", Arg.Set_string output_dir, "Output directory (default: valuation/dividend_income/output)");
    ("--python", Arg.Set_string python_cmd, "Python command to fetch data (e.g., 'uv run')");
    ("--compare", Arg.Set do_compare, "Compare multiple tickers");
    ("--required-return", Arg.Set_float required_return, "Required return for DDM (default: 0.08)");
    ("--terminal-growth", Arg.Set_float terminal_growth, "Terminal growth rate for DDM (default: 0.03)");
  ] in

  let usage = "Dividend Income Analysis\n\nUsage: dividend_income [OPTIONS]\n" in
  Arg.parse specs (fun _ -> ()) usage;

  (* Ensure output directory exists *)
  (try Unix.mkdir !output_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());

  (* Build DDM params *)
  let ddm_params = Ddm.default_params
    ~required_return:!required_return
    ~terminal_growth:!terminal_growth
    ~high_growth_years:5
    ()
  in

  (* Get list of tickers *)
  let ticker_list =
    if !tickers <> "" then
      String.split_on_char ',' !tickers |> List.map String.trim
    else if !ticker <> "" then
      [!ticker]
    else begin
      Printf.eprintf "Error: Must specify --ticker or --tickers\n";
      exit 1
    end
  in

  (* Fetch data if python command provided *)
  if !python_cmd <> "" then begin
    List.iter (fun t ->
      run_fetcher ~python_cmd:!python_cmd ~ticker:t ~output_dir:!data_dir
    ) ticker_list
  end else
    Printf.printf "Skipping fetch (no --python specified), using existing data\n";

  (* Analyze tickers *)
  let results = List.filter_map (fun t ->
    analyze_ticker ~data_dir:!data_dir ~output_dir:!output_dir ~ddm_params t
  ) ticker_list in

  (* Print comparison if requested or multiple tickers *)
  if !do_compare || List.length results > 1 then begin
    Io.print_comparison results;

    (* Write comparison JSON *)
    let comparison_file = Filename.concat !output_dir "dividend_comparison.json" in
    let json = `Assoc [
      ("results", `List (List.map (fun r ->
        `Assoc [
          ("ticker", `String r.Types.ticker);
          ("yield_pct", `Float r.dividend_metrics.yield_pct);
          ("payout_ratio", `Float r.dividend_metrics.payout_ratio_eps);
          ("dgr_5y", `Float r.growth_metrics.dgr_5y);
          ("safety_score", `Float r.safety_score.total_score);
          ("grade", `String r.safety_score.grade);
          ("signal", `String (Types.string_of_income_signal r.signal));
        ]
      ) results));
      ("highest_yield", `String (match List.sort (fun a b ->
        compare b.Types.dividend_metrics.yield_pct a.dividend_metrics.yield_pct) results with
        | h :: _ -> h.ticker | [] -> ""));
      ("safest", `String (match List.sort (fun a b ->
        compare b.Types.safety_score.total_score a.safety_score.total_score) results with
        | h :: _ -> h.ticker | [] -> ""));
    ] in
    Yojson.Basic.to_file comparison_file json;
    Printf.printf "Comparison written to: %s\n" comparison_file
  end;

  Printf.printf "\nAnalysis complete.\n"

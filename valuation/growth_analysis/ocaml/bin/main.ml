(** Main CLI for growth analysis *)

open Growth_analysis

(** Analyze a single ticker *)
let analyze_ticker ~data_dir ~output_dir ticker =
  let data_file = Filename.concat data_dir (Printf.sprintf "growth_data_%s.json" ticker) in

  if not (Sys.file_exists data_file) then begin
    Printf.eprintf "Data file not found: %s\n" data_file;
    Printf.eprintf "Run Python fetcher first: uv run valuation/growth_analysis/python/fetch/fetch_growth_data.py --ticker %s\n" ticker;
    None
  end else begin
    Printf.printf "Analyzing %s...\n" ticker;

    (* Read and analyze *)
    let data = Io.read_growth_data data_file in
    let result = Scoring.analyze data in

    (* Write result *)
    let output_file = Filename.concat output_dir (Printf.sprintf "growth_result_%s.json" ticker) in
    Io.write_result output_file result;
    Printf.printf "Result written to: %s\n" output_file;

    (* Print to stdout *)
    Io.print_result result;

    Some result
  end

(** Run Python fetcher *)
let run_fetcher ~python_cmd ~ticker ~output_dir =
  let cmd = Printf.sprintf "%s valuation/growth_analysis/python/fetch/fetch_growth_data.py --ticker %s --output %s"
    python_cmd ticker output_dir in
  let exit_code = Sys.command cmd in
  if exit_code <> 0 then
    Printf.eprintf "Warning: Python fetcher failed for %s\n" ticker

(** Main entry point *)
let () =
  let ticker = ref "" in
  let tickers = ref "" in
  let data_dir = ref "valuation/growth_analysis/data" in
  let output_dir = ref "valuation/growth_analysis/output" in
  let python_cmd = ref "" in
  let do_compare = ref false in

  let specs = [
    ("--ticker", Arg.Set_string ticker, "Single ticker to analyze");
    ("--tickers", Arg.Set_string tickers, "Comma-separated list of tickers");
    ("--data", Arg.Set_string data_dir, "Data directory (default: valuation/growth_analysis/data)");
    ("--output", Arg.Set_string output_dir, "Output directory (default: valuation/growth_analysis/output)");
    ("--python", Arg.Set_string python_cmd, "Python command to fetch data (e.g., 'uv run')");
    ("--compare", Arg.Set do_compare, "Compare multiple tickers");
  ] in

  let usage = "Growth Stock Analysis\n\nUsage: growth_analysis [OPTIONS]\n" in
  Arg.parse specs (fun _ -> ()) usage;

  (* Ensure output directory exists *)
  (try Unix.mkdir !output_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());

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
    analyze_ticker ~data_dir:!data_dir ~output_dir:!output_dir t
  ) ticker_list in

  (* Print comparison if requested or multiple tickers *)
  if !do_compare || List.length results > 1 then begin
    let sorted = Scoring.compare results in
    Io.print_comparison sorted;

    (* Write comparison JSON *)
    let comparison_file = Filename.concat !output_dir "growth_comparison.json" in
    let json = `Assoc [
      ("results", `List (List.map (fun r ->
        `Assoc [
          ("ticker", `String r.Types.ticker);
          ("revenue_growth_pct", `Float r.growth_metrics.revenue_growth_pct);
          ("rule_of_40", `Float r.growth_metrics.rule_of_40);
          ("score", `Float r.score.total_score);
          ("grade", `String r.score.grade);
          ("signal", `String (Types.string_of_growth_signal r.signal));
        ]
      ) sorted));
      ("highest_growth", `String (match sorted with h :: _ -> h.ticker | [] -> ""));
      ("best_score", `String (match sorted with h :: _ -> h.ticker | [] -> ""));
    ] in
    Yojson.Basic.to_file comparison_file json;
    Printf.printf "Comparison written to: %s\n" comparison_file
  end;

  Printf.printf "\nAnalysis complete.\n"

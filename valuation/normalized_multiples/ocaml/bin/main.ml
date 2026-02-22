(** Normalized Multiples Analysis CLI *)

open Normalized_multiples

let usage = {|
Normalized Multiples Analysis

Analyze stocks using valuation multiples with explicit time windows (TTM/NTM).
Compares to sector benchmarks and calculates quality-adjusted valuations.

Usage:
  multiples --tickers AAPL                 Single ticker analysis
  multiples --mode compare --tickers AAPL,MSFT,GOOGL    Compare multiple tickers

Options:
  --tickers <list>    Comma-separated ticker symbols (required)
  --mode <mode>       Analysis mode: 'single' or 'compare' (default: single)
  --data <dir>        Data directory (default: valuation/normalized_multiples/data)
  --output <dir>      Output directory (default: valuation/normalized_multiples/output)
  --python <cmd>      Python command to run fetcher (e.g., '.venv/bin/python3')
  --json              Output JSON instead of formatted text
  --help              Show this help

Examples:
  multiples --tickers AAPL --python '.venv/bin/python3'
  multiples --mode compare --tickers AAPL,MSFT,GOOGL,AMZN
|}

let run_python_fetcher python_cmd ticker data_dir =
  let cmd = Printf.sprintf "%s valuation/normalized_multiples/python/fetch/fetch_multiples_data.py --ticker %s --output %s"
    python_cmd ticker data_dir in
  let exit_code = Sys.command cmd in
  if exit_code <> 0 then
    Printf.eprintf "Warning: Failed to fetch data for %s\n" ticker

let () =
  let mode = ref "single" in
  let tickers_str = ref "" in
  let data_dir = ref "valuation/normalized_multiples/data" in
  let output_dir = ref "valuation/normalized_multiples/output" in
  let python_cmd = ref "" in
  let json_output = ref false in

  let spec = [
    ("--mode", Arg.Set_string mode, "Analysis mode: single or compare");
    ("--tickers", Arg.Set_string tickers_str, "Comma-separated list of tickers");
    ("--data", Arg.Set_string data_dir, "Data directory");
    ("--output", Arg.Set_string output_dir, "Output directory");
    ("--python", Arg.Set_string python_cmd, "Python command for fetching");
    ("--json", Arg.Set json_output, "Output JSON");
    ("--help", Arg.Unit (fun () -> print_string usage; exit 0), "Show help");
    ("-h", Arg.Unit (fun () -> print_string usage; exit 0), "Show help");
  ] in

  Arg.parse spec (fun _ -> ()) usage;

  if !tickers_str = "" then begin
    Printf.eprintf "Error: --tickers is required\n";
    print_string usage;
    exit 1
  end;

  let tickers = String.split_on_char ',' !tickers_str
    |> List.map String.trim
    |> List.map String.uppercase_ascii in

  (* Ensure output directory exists *)
  (try Unix.mkdir !output_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());

  (* Fetch data if python command provided *)
  if !python_cmd <> "" then begin
    Printf.printf "Fetching data...\n";
    List.iter (fun t -> run_python_fetcher !python_cmd t !data_dir) tickers
  end;

  (* Load company data *)
  let load_company ticker =
    let filename = Printf.sprintf "%s/multiples_data_%s.json" !data_dir ticker in
    if Sys.file_exists filename then
      Some (Io.read_multiples_data filename)
    else begin
      Printf.eprintf "Warning: No data file for %s\n" ticker;
      None
    end
  in

  let companies = List.filter_map load_company tickers in

  if List.length companies = 0 then begin
    Printf.eprintf "Error: No company data found. Run with --python to fetch data.\n";
    exit 1
  end;

  (* Get sector from first company for benchmark *)
  let sector = (List.hd companies).sector in
  let benchmark = Io.load_sector_benchmark !data_dir sector in

  if benchmark.sample_size = 0 then
    Printf.printf "Note: Using default benchmarks (run fetch_sector_benchmarks.py for sector data)\n\n";

  (* Run analysis *)
  match !mode with
  | "single" ->
    let company = List.hd companies in
    let result = Scoring.analyze_single company benchmark in
    if !json_output then
      Io.write_single_result_json !output_dir result
    else
      Io.print_single_result result

  | "compare" ->
    let result = Scoring.analyze_comparative companies benchmark in
    if !json_output then
      Io.write_comparative_result_json !output_dir result
    else
      Io.print_comparative_result result

  | _ ->
    Printf.eprintf "Unknown mode: %s (use 'single' or 'compare')\n" !mode;
    exit 1

(** GARP/PEG Analysis - Main executable *)

open Garp_peg

(** Parse command line arguments *)
let parse_args () =
  let ticker = ref "" in
  let data_dir = ref "valuation/garp_peg/data" in
  let output_dir = ref "valuation/garp_peg/output" in
  let python_fetch = ref "" in
  let compare_mode = ref false in
  let tickers = ref [] in

  let usage = "Usage: garp_peg [options]\n\nOptions:" in
  let spec = [
    ("--ticker", Arg.Set_string ticker, "Ticker symbol to analyze");
    ("--tickers", Arg.String (fun s -> tickers := String.split_on_char ',' s),
     "Comma-separated list of tickers for comparison");
    ("--data", Arg.Set_string data_dir, "Data directory (default: valuation/garp_peg/data)");
    ("--output", Arg.Set_string output_dir, "Output directory (default: valuation/garp_peg/output)");
    ("--python", Arg.Set_string python_fetch, "Path to Python fetch script");
    ("--compare", Arg.Set compare_mode, "Enable comparison mode for multiple tickers");
  ] in

  Arg.parse spec (fun _ -> ()) usage;

  if !ticker = "" && !tickers = [] then begin
    Printf.eprintf "Error: Must specify --ticker or --tickers\n";
    Arg.usage spec usage;
    exit 1
  end;

  (* If single ticker specified, add to tickers list *)
  if !ticker <> "" && !tickers = [] then
    tickers := [!ticker];

  (!tickers, !data_dir, !output_dir, !python_fetch, !compare_mode)


(** Run Python fetch script for a ticker *)
let fetch_data python_script ticker output_dir =
  if python_script = "" then
    Printf.printf "Skipping fetch (no --python specified), using existing data\n"
  else begin
    Printf.printf "Fetching data for %s...\n" ticker;
    let cmd = Printf.sprintf "uv run python %s --ticker %s --output %s"
      python_script ticker output_dir in
    let ret = Sys.command cmd in
    if ret <> 0 then begin
      Printf.eprintf "Warning: Python fetch failed for %s (exit code %d)\n" ticker ret;
    end
  end


(** Analyze a single ticker *)
let analyze_ticker data_dir output_dir ticker =
  let data_file = Printf.sprintf "%s/garp_data_%s.json" data_dir ticker in

  if not (Sys.file_exists data_file) then begin
    Printf.eprintf "Error: Data file not found: %s\n" data_file;
    Printf.eprintf "Run with --python to fetch data first\n";
    None
  end else begin
    Printf.printf "Analyzing %s...\n" ticker;

    (* Read data and analyze *)
    let data = Io.read_garp_data data_file in
    let result = Scoring.analyze data in

    (* Write individual result *)
    let output_file = Printf.sprintf "%s/garp_result_%s.json" output_dir ticker in
    Io.write_garp_result output_file result;
    Printf.printf "Result written to: %s\n" output_file;

    (* Print to console *)
    Io.print_result result;

    Some result
  end


let () =
  let tickers, data_dir, output_dir, python_script, compare_mode = parse_args () in

  (* Ensure output directory exists *)
  if not (Sys.file_exists output_dir) then
    Unix.mkdir output_dir 0o755;

  (* Fetch data for all tickers if python script specified *)
  List.iter (fun ticker ->
    fetch_data python_script ticker data_dir
  ) tickers;

  (* Analyze all tickers *)
  let results = List.filter_map (fun ticker ->
    analyze_ticker data_dir output_dir ticker
  ) tickers in

  (* If multiple tickers, do comparison *)
  if compare_mode || List.length results > 1 then begin
    Printf.printf "\n";
    let comparison = Scoring.compare results in
    Io.print_comparison comparison;

    (* Write comparison results *)
    let comp_file = Printf.sprintf "%s/garp_comparison.json" output_dir in
    Io.write_comparison comp_file comparison;
    Printf.printf "Comparison written to: %s\n" comp_file;
  end;

  Printf.printf "\nAnalysis complete.\n"

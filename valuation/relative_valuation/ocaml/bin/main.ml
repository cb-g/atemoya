(** Main CLI for relative valuation analysis *)

open Relative_valuation

(** Run Python fetcher *)
let run_fetcher ~python_cmd ~target ~peers ~output_dir =
  let peers_str = String.concat "," peers in
  let cmd = Printf.sprintf "%s valuation/relative_valuation/python/fetch/fetch_peer_data.py --target %s --peers %s --output %s"
    python_cmd target peers_str output_dir in
  let exit_code = Sys.command cmd in
  if exit_code <> 0 then
    Printf.eprintf "Warning: Python fetcher failed\n"

(** Main entry point *)
let () =
  let target = ref "" in
  let peers = ref "" in
  let data_dir = ref "valuation/relative_valuation/data" in
  let output_dir = ref "valuation/relative_valuation/output" in
  let python_cmd = ref "" in

  let specs = [
    ("--target", Arg.Set_string target, "Target ticker to analyze");
    ("--peers", Arg.Set_string peers, "Comma-separated list of peer tickers");
    ("--data", Arg.Set_string data_dir, "Data directory (default: valuation/relative_valuation/data)");
    ("--output", Arg.Set_string output_dir, "Output directory (default: valuation/relative_valuation/output)");
    ("--python", Arg.Set_string python_cmd, "Python command to fetch data (e.g., 'uv run')");
  ] in

  let usage = "Relative Valuation Analysis\n\nUsage: relative_valuation [OPTIONS]\n" in
  Arg.parse specs (fun _ -> ()) usage;

  if !target = "" then begin
    Printf.eprintf "Error: Must specify --target\n";
    exit 1
  end;

  (* Ensure output directory exists *)
  (try Unix.mkdir !output_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());

  (* Parse peers *)
  let peer_list =
    if !peers <> "" then
      String.split_on_char ',' !peers |> List.map String.trim
    else
      []
  in

  (* Fetch data if python command provided *)
  if !python_cmd <> "" && List.length peer_list > 0 then begin
    run_fetcher ~python_cmd:!python_cmd ~target:!target ~peers:peer_list ~output_dir:!data_dir
  end else if !python_cmd = "" then
    Printf.printf "Skipping fetch (no --python specified), using existing data\n";

  (* Read data file *)
  let data_file = Filename.concat !data_dir (Printf.sprintf "peer_data_%s.json" !target) in

  if not (Sys.file_exists data_file) then begin
    Printf.eprintf "Data file not found: %s\n" data_file;
    Printf.eprintf "Run with --python and --peers to fetch data first\n";
    exit 1
  end;

  Printf.printf "Analyzing %s...\n" !target;

  (* Read and analyze *)
  let peer_data = Io.read_peer_data data_file in
  let result = Scoring.analyze peer_data in

  (* Write result *)
  let output_file = Filename.concat !output_dir (Printf.sprintf "relative_result_%s.json" !target) in
  Io.write_result output_file result;
  Printf.printf "Result written to: %s\n" output_file;

  (* Print to stdout *)
  Io.print_result result;

  Printf.printf "Analysis complete.\n"

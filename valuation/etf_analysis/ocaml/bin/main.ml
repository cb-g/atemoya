(** ETF Analysis CLI *)

open Etf_analysis

let usage = {|
ETF Analysis Tool

Usage:
  etf_analysis <data_file.json>              Analyze single ETF
  etf_analysis --compare <file1> <file2> ... Compare multiple ETFs

Options:
  --compare      Compare multiple ETFs side by side
  --holdings N   Number of top holdings to display (default: 10)
  --help         Show this help message

Examples:
  # Analyze single ETF
  etf_analysis data/etf_data_SPY.json

  # Analyze with more holdings
  etf_analysis --holdings 15 data/etf_data_SPY.json

  # Compare S&P 500 ETFs
  etf_analysis --compare data/etf_data_SPY.json data/etf_data_VOO.json data/etf_data_IVV.json

  # Compare with custom holdings count
  etf_analysis --holdings 20 --compare data/etf_data_JEPI.json data/etf_data_QYLD.json
|}

(* Global holdings count - default 10 *)
let holdings_count = ref 10

let analyze_single (filename : string) : unit =
  try
    let data = Io.parse_etf_data filename in
    let result = Scoring.analyze_etf data in

    (* Print to console *)
    Io.print_result ~max_holdings:!holdings_count result;

    (* Save to output file *)
    let output_dir = Filename.dirname (Filename.dirname filename) ^ "/output" in
    (try Unix.mkdir output_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());

    let output_file = output_dir ^ "/etf_result_" ^ data.ticker ^ ".json" in
    Io.save_result result output_file;
    Printf.printf "\nResults saved to %s\n" output_file

  with
  | Sys_error msg ->
    Printf.eprintf "Error reading file: %s\n" msg;
    exit 1
  | Yojson.Json_error msg ->
    Printf.eprintf "Error parsing JSON: %s\n" msg;
    exit 1

let compare_multiple (filenames : string list) : unit =
  try
    let results = List.map (fun filename ->
        let data = Io.parse_etf_data filename in
        Scoring.analyze_etf data
      ) filenames
    in

    let comparison = Scoring.compare_etfs results in

    (* Print to console *)
    Io.print_comparison ~max_holdings:!holdings_count comparison;

    (* Also print detailed analysis for each *)
    Printf.printf "\n%s\n" (String.make 80 '=');
    Printf.printf "DETAILED ANALYSIS\n";
    Printf.printf "%s\n" (String.make 80 '=');
    List.iter (Io.print_result ~max_holdings:!holdings_count) results;

    (* Save comparison to output *)
    let first_file = List.hd filenames in
    let output_dir = Filename.dirname (Filename.dirname first_file) ^ "/output" in
    (try Unix.mkdir output_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());

    let output_file = output_dir ^ "/etf_comparison.json" in
    Io.save_comparison comparison output_file;
    Printf.printf "\nComparison saved to %s\n" output_file

  with
  | Sys_error msg ->
    Printf.eprintf "Error reading file: %s\n" msg;
    exit 1
  | Yojson.Json_error msg ->
    Printf.eprintf "Error parsing JSON: %s\n" msg;
    exit 1

(* Parse --holdings N from args, return remaining args *)
let rec parse_holdings args =
  match args with
  | "--holdings" :: n :: rest ->
    (try
       holdings_count := int_of_string n;
       parse_holdings rest
     with Failure _ ->
       Printf.eprintf "Error: --holdings requires a number\n";
       exit 1)
  | x :: rest ->
    let remaining = parse_holdings rest in
    x :: remaining
  | [] -> []

let () =
  let args = Array.to_list Sys.argv |> List.tl in
  let args = parse_holdings args in

  match args with
  | [] | ["--help"] | ["-h"] ->
    print_string usage
  | ["--compare"] ->
    Printf.eprintf "Error: --compare requires at least 2 ETF data files\n";
    exit 1
  | "--compare" :: files when List.length files >= 2 ->
    compare_multiple files
  | [filename] ->
    analyze_single filename
  | _ ->
    Printf.eprintf "Error: Invalid arguments. Use --help for usage.\n";
    exit 1

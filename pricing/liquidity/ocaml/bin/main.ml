(** Liquidity Analysis - Main Entry Point *)

let default_window = 20

let () =
  let data_file = ref "" in
  let output_file = ref "" in
  let window = ref default_window in
  let json_output = ref false in

  let usage = "Usage: liquidity_analysis --data <file> [--output <file>] [--window <n>] [--json]" in
  let spec = [
    ("--data", Arg.Set_string data_file, "Input market data JSON file");
    ("--output", Arg.Set_string output_file, "Output results JSON file");
    ("--window", Arg.Set_int window, Printf.sprintf "Analysis window (default: %d)" default_window);
    ("--json", Arg.Set json_output, "Output JSON only (no console)");
  ] in
  Arg.parse spec (fun _ -> ()) usage;

  if !data_file = "" then begin
    Printf.eprintf "Error: --data required\n";
    exit 1
  end;

  (* Load market data *)
  let data_list = Liquidity.Io.load_market_data !data_file in
  Printf.printf "Loaded %d tickers\n" (List.length data_list);

  (* Run analysis *)
  let results = Liquidity.Analysis.analyze_all data_list ~window:!window in
  let sorted = Liquidity.Analysis.sort_by_liquidity results in

  (* Output results *)
  if not !json_output then begin
    List.iter Liquidity.Analysis.print_result sorted;
    Liquidity.Analysis.print_summary sorted
  end;

  (* Save JSON if output file specified *)
  if !output_file <> "" then begin
    Liquidity.Io.save_results !output_file sorted;
    Printf.printf "\nResults saved to: %s\n" !output_file
  end

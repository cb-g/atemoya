(** Main entry point for DCF scenario analysis *)

open Dcf_deterministic

let () =
  (* Parse command line arguments *)
  let ticker = ref "" in
  let data_dir = ref "../data" in
  let output_dir = ref "../output" in
  let python_script = ref "../python/fetch_financials.py" in

  let speclist = [
    ("-ticker", Arg.Set_string ticker, "Ticker symbol to analyze");
    ("-data-dir", Arg.Set_string data_dir, "Data directory path (default: ../data)");
    ("-output-dir", Arg.Set_string output_dir, "Output directory path (default: ../output)");
    ("-python", Arg.Set_string python_script, "Python fetcher script path");
  ] in

  let usage_msg = "DCF Scenario Analysis Tool\nUsage: dcf_scenarios -ticker TICKER [options]" in
  Arg.parse speclist (fun _ -> ()) usage_msg;

  if !ticker = "" then begin
    Printf.eprintf "Error: -ticker argument is required\n";
    Arg.usage speclist usage_msg;
    exit 1
  end;

  try
    (* Step 1: Fetch financial data using Python script *)
    Printf.printf "Fetching financial data for %s...\n" !ticker;
    let fetch_cmd = Printf.sprintf "uv run %s --ticker %s --output /tmp" !python_script !ticker in
    let fetch_status = Sys.command fetch_cmd in
    if fetch_status <> 0 then begin
      Printf.eprintf "Error: Failed to fetch financial data\n";
      exit 1
    end;

    (* Step 2: Load configuration *)
    Printf.printf "Loading configuration...\n";
    let config = Io.load_config !data_dir in

    (* Step 3: Load market and financial data *)
    let market_data_file = Printf.sprintf "/tmp/dcf_market_data_%s.json" !ticker in
    let financial_data_file = Printf.sprintf "/tmp/dcf_financial_data_%s.json" !ticker in

    let market_data = Io.load_market_data market_data_file in
    let financial_data = Io.load_financial_data financial_data_file in

    (* Step 4: Run scenario analysis *)
    Printf.printf "Running scenario analysis (Bull/Base/Bear)...\n";
    match Scenarios.run_scenario_analysis ~market_data ~financial_data ~config with
    | None ->
        Printf.eprintf "Error: Scenario analysis failed (valuation error)\n";
        exit 1

    | Some comparison ->
        (* Step 5: Output results *)
        Printf.printf "%s\n" (Io.format_scenario_comparison comparison);

        (* Step 6: Write CSV output *)
        let csv_filename = Printf.sprintf "%s/scenarios_%s.csv" !output_dir !ticker in
        Io.write_scenario_csv ~filename:csv_filename ~comparison;
        Printf.printf "Scenario results written to: %s\n" csv_filename;

        (* Step 7: Generate visualizations *)
        Printf.printf "Generating visualizations...\n";
        let viz_cmd = Printf.sprintf
          "uv run ../python/viz/plot_scenarios.py --csv %s --ticker %s --price %.2f --output %s"
          csv_filename !ticker market_data.price !output_dir in
        let viz_status = Sys.command viz_cmd in
        if viz_status = 0 then
          Printf.printf "Visualizations saved to: %s\n" !output_dir
        else
          Printf.eprintf "Warning: Visualization generation failed\n";

  with
  | Sys_error msg ->
      Printf.eprintf "System error: %s\n" msg;
      exit 1
  | Yojson.Json_error msg ->
      Printf.eprintf "JSON parsing error: %s\n" msg;
      exit 1
  | e ->
      Printf.eprintf "Unexpected error: %s\n" (Printexc.to_string e);
      exit 1

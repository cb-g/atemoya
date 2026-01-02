(** Main entry point for DCF sensitivity analysis *)

open Dcf_deterministic

let () =
  (* Parse command line arguments *)
  let ticker = ref "" in
  let data_dir = ref "../data" in
  let output_dir = ref "../output" in
  let python_script = ref "../python/fetch_financials.py" in

  (* Optional parameter overrides *)
  let projection_years_override = ref None in
  let terminal_growth_override = ref None in
  let growth_clamp_upper_override = ref None in
  let growth_clamp_lower_override = ref None in
  let rfr_duration_override = ref None in

  let speclist = [
    ("-ticker", Arg.Set_string ticker, "Ticker symbol to analyze");
    ("-data-dir", Arg.Set_string data_dir, "Data directory path (default: ../data)");
    ("-output-dir", Arg.Set_string output_dir, "Output directory for CSV files (default: ../output)");
    ("-python", Arg.Set_string python_script, "Python fetcher script path");
    ("-projection-years", Arg.Int (fun x -> projection_years_override := Some x), "Override projection years (default: from config)");
    ("-terminal-growth", Arg.Float (fun x -> terminal_growth_override := Some x), "Override terminal growth rate (default: from config)");
    ("-growth-clamp-upper", Arg.Float (fun x -> growth_clamp_upper_override := Some x), "Override upper growth clamp (default: from config)");
    ("-growth-clamp-lower", Arg.Float (fun x -> growth_clamp_lower_override := Some x), "Override lower growth clamp (default: from config)");
    ("-rfr-duration", Arg.Int (fun x -> rfr_duration_override := Some x), "Override risk-free rate duration in years (default: from config)");
  ] in

  let usage_msg = "DCF Sensitivity Analysis Tool\nUsage: dcf_sensitivity -ticker TICKER [options]" in
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
    let base_config = Io.load_config !data_dir in

    (* Apply command-line overrides *)
    let config =
      let params = base_config.Types.params in
      let overridden_params = Types.{
        projection_years = (match !projection_years_override with Some x -> x | None -> params.projection_years);
        terminal_growth_rate = (match !terminal_growth_override with Some x -> x | None -> params.terminal_growth_rate);
        growth_clamp_upper = (match !growth_clamp_upper_override with Some x -> x | None -> params.growth_clamp_upper);
        growth_clamp_lower = (match !growth_clamp_lower_override with Some x -> x | None -> params.growth_clamp_lower);
        rfr_duration = (match !rfr_duration_override with Some x -> x | None -> params.rfr_duration);
      } in
      { base_config with params = overridden_params }
    in

    (* Step 3: Load market and financial data from /tmp *)
    let market_data_file = Printf.sprintf "/tmp/dcf_market_data_%s.json" !ticker in
    let financial_data_file = Printf.sprintf "/tmp/dcf_financial_data_%s.json" !ticker in

    Printf.printf "Loading market data...\n";
    let market_data = Io.load_market_data market_data_file in

    Printf.printf "Loading financial data...\n";
    let financial_data = Io.load_financial_data financial_data_file in

    (* Step 4: Look up configuration parameters for this ticker *)
    let country = market_data.country in
    let industry = market_data.industry in

    (* Get risk-free rate for specified duration *)
    let rfr_duration = config.params.rfr_duration in
    let risk_free_rate =
      match List.assoc_opt country config.risk_free_rates with
      | Some rates ->
          (match List.assoc_opt rfr_duration rates with
           | Some rate -> rate
           | None ->
               Printf.eprintf "Warning: No %d-year RFR for %s, using first available\n" rfr_duration country;
               snd (List.hd rates))
      | None ->
          Printf.eprintf "Error: No risk-free rate data for country %s\n" country;
          exit 1
    in

    let equity_risk_premium =
      match List.assoc_opt country config.equity_risk_premiums with
      | Some erp -> erp
      | None ->
          Printf.eprintf "Error: No equity risk premium data for country %s\n" country;
          exit 1
    in

    let unlevered_beta =
      match List.assoc_opt industry config.industry_betas with
      | Some beta -> beta
      | None ->
          Printf.eprintf "Warning: No beta for industry %s, using 1.0\n" industry;
          1.0
    in

    let tax_rate =
      match List.assoc_opt country config.tax_rates with
      | Some rate -> rate
      | None ->
          Printf.eprintf "Error: No tax rate data for country %s\n" country;
          exit 1
    in

    (* Step 5: Calculate cost of capital *)
    Printf.printf "Calculating cost of capital...\n";
    let cost_of_capital = Capital_structure.calculate_cost_of_capital
      ~market_data
      ~financial_data
      ~unlevered_beta
      ~risk_free_rate
      ~equity_risk_premium
      ~tax_rate
    in

    (* Step 6: Run sensitivity analysis *)
    Printf.printf "\n========================================\n";
    Printf.printf "SENSITIVITY ANALYSIS: %s\n" !ticker;
    Printf.printf "========================================\n\n";

    let results = Sensitivity.run_sensitivity_analysis
      ~market_data
      ~financial_data
      ~config
      ~cost_of_capital
      ~tax_rate
    in

    (* Step 7: Write results to CSV *)
    Printf.printf "\nWriting sensitivity results to CSV files...\n";
    Sensitivity.write_sensitivity_csv
      ~output_dir:!output_dir
      ~ticker:!ticker
      ~results
      ~market_price:market_data.price;

    Printf.printf "\n========================================\n";
    Printf.printf "Sensitivity analysis complete for %s\n" !ticker;
    Printf.printf "Results saved to: %s\n" !output_dir;
    Printf.printf "========================================\n";

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

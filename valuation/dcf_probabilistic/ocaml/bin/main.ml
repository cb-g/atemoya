(** Main entry point for DCF probabilistic valuation *)

open Dcf_probabilistic

let () =
  (* Parse command line arguments *)
  let ticker = ref "" in
  let data_dir = ref "../data" in
  let log_dir = ref "../log" in
  let output_dir = ref "../output" in
  let python_script = ref "../python/fetch/fetch_financials_ts.py" in

  let speclist = [
    ("-ticker", Arg.Set_string ticker, "Ticker symbol to value");
    ("-data-dir", Arg.Set_string data_dir, "Data directory path");
    ("-log-dir", Arg.Set_string log_dir, "Log directory path");
    ("-output-dir", Arg.Set_string output_dir, "Output directory path");
    ("-python", Arg.Set_string python_script, "Python fetcher script path");
  ] in

  let usage_msg = "DCF Probabilistic Valuation Tool\nUsage: dcf_probabilistic -ticker TICKER [options]" in
  Arg.parse speclist (fun _ -> ()) usage_msg;

  if !ticker = "" then begin
    Printf.eprintf "Error: -ticker argument is required\n";
    Arg.usage speclist usage_msg;
    exit 1
  end;

  try
    (* Step 1: Fetch financial data using Python script *)
    Printf.printf "Fetching 4-year time series data for %s...\n" !ticker;
    let fetch_cmd = Printf.sprintf "uv run %s --ticker %s --output /tmp" !python_script !ticker in
    let fetch_status = Sys.command fetch_cmd in
    if fetch_status <> 0 then begin
      Printf.eprintf "Error: Failed to fetch financial data\n";
      exit 1
    end;

    (* Step 2: Load configuration *)
    Printf.printf "Loading configuration...\n";
    let config = Io.load_config !data_dir in

    (* Step 3: Load market and time series data *)
    let market_data_file = Printf.sprintf "/tmp/dcf_prob_market_data_%s.json" !ticker in
    let time_series_file = Printf.sprintf "/tmp/dcf_prob_time_series_%s.json" !ticker in

    Printf.printf "Loading market data...\n";
    let market_data = Io.load_market_data market_data_file in

    Printf.printf "Loading time series data...\n";
    let time_series = Io.load_time_series time_series_file in

    (* Step 4: Look up configuration parameters *)
    let country = market_data.country in
    let sector = market_data.sector in
    let industry = market_data.industry in

    (* Get sector-specific priors *)
    let sector_priors = Io.get_sector_priors config sector in
    Printf.printf "Using priors for sector: %s\n" sector;

    let rfr_duration = config.simulation_config.rfr_duration in
    let risk_free_rate =
      match List.assoc_opt country config.risk_free_rates with
      | Some rates ->
          (match List.assoc_opt rfr_duration rates with
           | Some rate -> rate
           | None -> snd (List.hd rates))
      | None ->
          Printf.eprintf "Error: No risk-free rate for %s\n" country;
          exit 1
    in

    let equity_risk_premium =
      match List.assoc_opt country config.equity_risk_premiums with
      | Some erp -> erp
      | None ->
          Printf.eprintf "Error: No equity risk premium for %s\n" country;
          exit 1
    in

    let unlevered_beta =
      match List.assoc_opt industry config.industry_betas with
      | Some beta -> beta
      | None -> 1.0
    in

    let tax_rate =
      match List.assoc_opt country config.tax_rates with
      | Some rate -> rate
      | None ->
          Printf.eprintf "Error: No tax rate for %s\n" country;
          exit 1
    in

    (* Step 5: Calculate cost of capital (deterministic) *)
    Printf.printf "Calculating cost of capital...\n";

    (* Calculate leveraged beta *)
    let total_value = market_data.mve +. market_data.mvb in
    let de_ratio = if market_data.mve = 0.0 then 0.0 else market_data.mvb /. market_data.mve in
    let leveraged_beta = unlevered_beta *. (1.0 +. (1.0 -. tax_rate) *. de_ratio) in

    (* Calculate cost of equity *)
    let ce = risk_free_rate +. (leveraged_beta *. equity_risk_premium) in

    (* Calculate cost of borrowing *)
    let cb = if market_data.mvb = 0.0 then 0.0
      else
        (* Estimate from interest expense if available, else use approximation *)
        risk_free_rate +. 0.02
    in

    (* Calculate WACC *)
    let wacc = if total_value = 0.0 then ce
      else
        let equity_weight = market_data.mve /. total_value in
        let debt_weight = market_data.mvb /. total_value in
        (equity_weight *. ce) +. (debt_weight *. cb *. (1.0 -. tax_rate))
    in

    let cost_of_capital = Types.{
      ce;
      cb;
      wacc;
      leveraged_beta;
      risk_free_rate;
      equity_risk_premium;
    } in

    (* Step 6: Run Monte Carlo simulations *)
    Printf.printf "Running Monte Carlo simulations (%d iterations)...\n"
      config.simulation_config.num_simulations;

    Printf.printf "  Simulating FCFE valuations...\n";
    let simulations_fcfe = Monte_carlo.run_fcfe_simulations
      ~market_data
      ~time_series
      ~cost_of_capital
      ~config:config.simulation_config
      ~roe_prior:sector_priors.roe_prior
      ~retention_prior:sector_priors.retention_prior
    in

    Printf.printf "  Simulating FCFF valuations...\n";
    let simulations_fcff = Monte_carlo.run_fcff_simulations
      ~market_data
      ~time_series
      ~cost_of_capital
      ~config:config.simulation_config
      ~roic_prior:sector_priors.roic_prior
      ~tax_rate
    in

    (* Step 7: Compute statistics *)
    Printf.printf "Computing statistics...\n";
    let fcfe_stats = Statistics.compute_statistics simulations_fcfe in
    let fcff_stats = Statistics.compute_statistics simulations_fcff in

    let fcfe_metrics = Statistics.compute_probability_metrics
      ~simulations:simulations_fcfe
      ~price:market_data.price
    in

    let fcff_metrics = Statistics.compute_probability_metrics
      ~simulations:simulations_fcff
      ~price:market_data.price
    in

    (* Classify valuations *)
    let fcfe_class = Statistics.classify_valuation
      ~mean_ivps:fcfe_stats.mean
      ~price:market_data.price
      ~tolerance:0.05
    in

    let fcff_class = Statistics.classify_valuation
      ~mean_ivps:fcff_stats.mean
      ~price:market_data.price
      ~tolerance:0.05
    in

    let signal = Statistics.generate_signal ~fcfe_class ~fcff_class in

    (* Compute tail risk metrics *)
    let fcfe_tail_risk = Statistics.compute_tail_risk_metrics
      ~simulations:simulations_fcfe
      ~price:market_data.price
    in

    let fcff_tail_risk = Statistics.compute_tail_risk_metrics
      ~simulations:simulations_fcff
      ~price:market_data.price
    in

    (* Generate stress scenarios *)
    Printf.printf "Generating stress scenarios...\n";
    let stress_scenarios = Stress.generate_stress_scenarios
      ~market_data
      ~time_series
      ~cost_of_capital
      ~config:config.simulation_config
      ~roe_prior:sector_priors.roe_prior
      ~retention_prior:sector_priors.retention_prior
      ~roic_prior:sector_priors.roic_prior
      ~tax_rate
    in

    (* Create valuation result *)
    let result = Types.{
      ticker = market_data.ticker;
      price = market_data.price;
      num_simulations = config.simulation_config.num_simulations;
      fcfe_stats;
      fcfe_metrics;
      fcfe_class;
      fcfe_tail_risk;
      fcff_stats;
      fcff_metrics;
      fcff_class;
      fcff_tail_risk;
      signal;
      cost_of_capital;
      simulations_fcfe;
      simulations_fcff;
      stress_scenarios;
    } in

    (* Step 8: Output results *)
    Printf.printf "%s\n" (Io.format_valuation_result result);

    (* Step 9: Write outputs *)
    let log_filename = Io.create_log_filename ~base_dir:!log_dir ~ticker:!ticker in
    Io.write_log ~filename:log_filename ~result;
    Printf.printf "Results written to: %s\n" log_filename;

    (* Write CSV outputs to data subdirectory *)
    (* Create data directory if it doesn't exist *)
    let data_dir = Filename.concat !output_dir "data" in
    if not (Sys.file_exists data_dir) then
      Unix.mkdir data_dir 0o755;

    let summary_file = Filename.concat data_dir "probabilistic_summary.csv" in
    let fcfe_matrix_file = Filename.concat data_dir "simulations_fcfe.csv" in
    let fcff_matrix_file = Filename.concat data_dir "simulations_fcff.csv" in
    let prices_file = Filename.concat data_dir "market_prices.csv" in

    Io.write_summary_csv ~filename:summary_file ~results:[result];
    Io.write_simulation_matrices ~fcfe_file:fcfe_matrix_file ~fcff_file:fcff_matrix_file ~results:[result];
    Io.write_market_prices ~filename:prices_file ~results:[result];

    Printf.printf "CSV outputs written to: %s\n" data_dir;

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

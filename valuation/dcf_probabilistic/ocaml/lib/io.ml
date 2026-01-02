(** I/O operations for probabilistic DCF *)

open Yojson.Basic.Util

(** Helper to convert JSON number (int or float) to float *)
let to_number json =
  try to_float json
  with Yojson.Basic.Util.Type_error _ -> float_of_int (to_int json)

(** Load simulation configuration *)
let load_simulation_config filename =
  let json = Yojson.Basic.from_file filename in
  let open Types in

  (* Helper to get optional bool with default *)
  let get_bool_opt key default_val =
    try json |> member key |> to_bool
    with _ -> default_val
  in

  (* Helper to get optional float with default *)
  let get_float_opt key default_val =
    try json |> member key |> to_number
    with _ -> default_val
  in

  (* Helper to parse 2D array (correlation matrix) *)
  let parse_correlation_matrix key =
    try
      let matrix_json = json |> member key |> to_list in
      Array.of_list (List.map (fun row ->
        Array.of_list (List.map to_number (to_list row))
      ) matrix_json)
    with _ ->
      (* Default correlation matrix based on key *)
      if key = "financials_correlation" then
        (* 6×6 matrix for [NI, EBIT, CapEx, Depr, CA, CL] - from copula module *)
        [|
          (*       NI    EBIT  CapEx  Depr   CA    CL   *)
          [| 1.00; 0.90; 0.60; 0.35; 0.30; 0.25 |];  (* NI *)
          [| 0.90; 1.00; 0.55; 0.30; 0.35; 0.30 |];  (* EBIT *)
          [| 0.60; 0.55; 1.00; 0.40; 0.40; 0.35 |];  (* CapEx *)
          [| 0.35; 0.30; 0.40; 1.00; 0.25; 0.20 |];  (* Depreciation *)
          [| 0.30; 0.35; 0.40; 0.25; 1.00; 0.70 |];  (* Current Assets *)
          [| 0.25; 0.30; 0.35; 0.20; 0.70; 1.00 |];  (* Current Liabilities *)
        |]
      else
        (* Default: 3×3 identity matrix for discount rates *)
        [| [| 1.0; 0.0; 0.0 |];
           [| 0.0; 1.0; 0.0 |];
           [| 0.0; 0.0; 1.0 |] |]
  in

  (* Helper to parse regime_parameters *)
  let parse_regime_parameters regime_json =
    let open Types in
    let corr_key = "correlation" in
    let corr_matrix =
      try
        let matrix_json = regime_json |> member corr_key |> to_list in
        Array.of_list (List.map (fun row ->
          Array.of_list (List.map to_number (to_list row))
        ) matrix_json)
      with _ ->
        [| [| 1.0; 0.0; 0.0 |];
           [| 0.0; 1.0; 0.0 |];
           [| 0.0; 0.0; 1.0 |] |]
    in
    {
      rfr_volatility = regime_json |> member "rfr_volatility" |> to_number;
      erp_volatility = regime_json |> member "erp_volatility" |> to_number;
      beta_volatility = regime_json |> member "beta_volatility" |> to_number;
      correlation = corr_matrix;
    }
  in

  (* Helper to parse regime_config *)
  let parse_regime_config () =
    try
      let regime_json = json |> member "regime_switching" in
      let open Types in
      Some {
        crisis_probability = regime_json |> member "crisis_probability" |> to_number;
        normal_regime = parse_regime_parameters (regime_json |> member "normal_regime");
        crisis_regime = parse_regime_parameters (regime_json |> member "crisis_regime");
      }
    with _ -> None
  in

  {
    num_simulations = json |> member "num_simulations" |> to_int;
    projection_years = json |> member "projection_years" |> to_int;
    terminal_growth_rate = json |> member "terminal_growth_rate" |> member "default" |> to_number;
    growth_clamp_upper = json |> member "growth_clamp" |> member "upper" |> to_number;
    growth_clamp_lower = json |> member "growth_clamp" |> member "lower" |> to_number;
    rfr_duration = json |> member "rfr_duration" |> to_int;
    use_bayesian_priors = json |> member "use_bayesian_priors" |> to_bool;
    prior_weight = json |> member "prior_weight" |> to_number;
    use_stochastic_discount_rates = get_bool_opt "use_stochastic_discount_rates" false;
    rfr_volatility = get_float_opt "rfr_volatility" 0.005;  (* 50 bps default *)
    beta_volatility = get_float_opt "beta_volatility" 0.1;  (* 0.1 default *)
    erp_volatility = get_float_opt "erp_volatility" 0.01;   (* 1% default *)
    use_time_varying_growth = get_bool_opt "use_time_varying_growth" false;
    growth_mean_reversion_speed = get_float_opt "growth_mean_reversion_speed" 0.3;  (* λ = 0.3 default *)
    use_growth_rate_sampling = get_bool_opt "use_growth_rate_sampling" true;  (* Default to RECOMMENDED approach *)
    use_correlated_discount_rates = get_bool_opt "use_correlated_discount_rates" true;  (* Default to RECOMMENDED approach *)
    discount_rate_correlation = parse_correlation_matrix "discount_rate_correlation";
    use_regime_switching = get_bool_opt "use_regime_switching" true;  (* Default to RECOMMENDED approach *)
    regime_config = parse_regime_config ();
    use_copula_financials = get_bool_opt "use_copula_financials" true;  (* Default to RECOMMENDED approach *)
    financials_correlation = parse_correlation_matrix "financials_correlation";  (* 6×6 matrix for [NI, EBIT, CapEx, Depr, CA, CL] *)
  }

(** Load Bayesian priors *)
let load_bayesian_priors filename =
  let json = Yojson.Basic.from_file filename in
  let open Types in

  let parse_beta_prior p =
    {
      alpha = p |> member "alpha" |> to_number;
      beta = p |> member "beta" |> to_number;
      lower_bound = p |> member "lower_bound" |> to_number;
      upper_bound = p |> member "upper_bound" |> to_number;
    }
  in

  let parse_sector_priors s_json =
    {
      roe_prior = s_json |> member "roe_prior" |> parse_beta_prior;
      retention_prior = s_json |> member "retention_prior" |> parse_beta_prior;
      roic_prior = s_json |> member "roic_prior" |> parse_beta_prior;
    }
  in

  (* Load default priors *)
  let default_priors = json |> member "default" |> parse_sector_priors in

  (* Load industry-specific priors *)
  let industries = json |> member "industries" |> to_assoc in
  let industry_priors_list = List.map (fun (sector_name, sector_json) ->
    (sector_name, parse_sector_priors sector_json)
  ) industries in

  (* Prepend default priors with special key *)
  ("default", default_priors) :: industry_priors_list

let load_risk_free_rates filename =
  let json = Yojson.Basic.from_file filename in
  json |> to_assoc |> List.map (fun (country, rates_json) ->
    let rates = rates_json |> to_assoc |> List.map (fun (duration_str, rate) ->
      let duration = int_of_string (String.sub duration_str 0 (String.length duration_str - 1)) in
      (duration, to_number rate)
    ) in
    (country, rates)
  )

let load_equity_risk_premiums filename =
  let json = Yojson.Basic.from_file filename in
  json |> to_assoc |> List.map (fun (country, erp) -> (country, to_number erp))

let load_industry_betas filename =
  let json = Yojson.Basic.from_file filename in
  json |> to_assoc |> List.map (fun (industry, beta) -> (industry, to_number beta))

let load_tax_rates filename =
  let json = Yojson.Basic.from_file filename in
  json |> to_assoc |> List.map (fun (country, rate) -> (country, to_number rate))

let load_config data_dir =
  let open Types in
  let sim_config = load_simulation_config (Filename.concat data_dir "params_probabilistic.json") in
  let industry_priors = load_bayesian_priors (Filename.concat data_dir "bayesian_priors.json") in

  {
    risk_free_rates = load_risk_free_rates (Filename.concat data_dir "risk_free_rates.json");
    equity_risk_premiums = load_equity_risk_premiums (Filename.concat data_dir "equity_risk_premiums.json");
    industry_betas = load_industry_betas (Filename.concat data_dir "industry_betas.json");
    tax_rates = load_tax_rates (Filename.concat data_dir "tax_rates.json");
    simulation_config = sim_config;
    industry_priors;
  }

(** Get priors for a specific sector, fallback to default if not found *)
let get_sector_priors config sector =
  let open Types in
  match List.assoc_opt sector config.industry_priors with
  | Some priors -> priors
  | None ->
      (* Fallback to default priors *)
      match List.assoc_opt "default" config.industry_priors with
      | Some default -> default
      | None -> failwith "No default priors found in configuration"

let load_market_data filename =
  let json = Yojson.Basic.from_file filename in
  let open Types in
  {
    ticker = json |> member "ticker" |> to_string;
    price = json |> member "price" |> to_number;
    mve = json |> member "mve" |> to_number;
    mvb = json |> member "mvb" |> to_number;
    shares_outstanding = json |> member "shares_outstanding" |> to_number;
    currency = json |> member "currency" |> to_string;
    country = json |> member "country" |> to_string;
    sector = json |> member "sector" |> to_string;
    industry = json |> member "industry" |> to_string;
  }

let load_time_series filename =
  let json = Yojson.Basic.from_file filename in
  let ts = json |> member "time_series" in
  let open Types in

  let to_array name = ts |> member name |> to_list |> List.map to_number |> Array.of_list in

  {
    ebit = to_array "ebit";
    net_income = to_array "net_income";
    capex = to_array "capex";
    depreciation = to_array "depreciation";
    current_assets = to_array "current_assets";
    current_liabilities = to_array "current_liabilities";
    book_value_equity = to_array "book_value_equity";
    dividend_payout = to_array "dividend_payout";
    invested_capital = to_array "invested_capital";
  }

(** CSV writing *)

(* Helper to read existing CSV lines *)
let read_csv_lines filename =
  if Sys.file_exists filename then
    let ic = open_in filename in
    let rec read_lines acc =
      try
        let line = input_line ic in
        read_lines (line :: acc)
      with End_of_file ->
        close_in ic;
        List.rev acc
    in
    read_lines []
  else
    []

let write_summary_csv ~filename ~results =
  let existing_lines = read_csv_lines filename in
  let header = "ticker,price,num_sims,fcfe_mean,fcfe_std,fcfe_min,fcfe_max,fcfe_p50,fcfe_class,fcfe_prob_under,fcff_mean,fcff_std,fcff_min,fcff_max,fcff_p50,fcff_class,fcff_prob_under,signal" in

  (* Filter out duplicate tickers if file exists *)
  let filtered_results =
    if existing_lines = [] then
      results
    else
      let existing_tickers = List.tl existing_lines |> List.map (fun line ->
        match String.split_on_char ',' line with
        | ticker :: _ -> ticker
        | [] -> ""
      ) in
      List.filter (fun r -> not (List.mem r.Types.ticker existing_tickers)) results
  in

  let data_lines = List.map (fun result ->
    let open Types in
    Printf.sprintf "%s,%.2f,%d,%.2f,%.2f,%.2f,%.2f,%.2f,%s,%.4f,%.2f,%.2f,%.2f,%.2f,%.2f,%s,%.4f,%s"
      result.ticker result.price result.num_simulations
      result.fcfe_stats.mean result.fcfe_stats.std result.fcfe_stats.min
      result.fcfe_stats.max result.fcfe_stats.percentile_50
      (Statistics.class_to_string result.fcfe_class)
      result.fcfe_metrics.prob_undervalued
      result.fcff_stats.mean result.fcff_stats.std result.fcff_stats.min
      result.fcff_stats.max result.fcff_stats.percentile_50
      (Statistics.class_to_string result.fcff_class)
      result.fcff_metrics.prob_undervalued
      (Statistics.signal_to_string result.signal)
  ) filtered_results in

  let lines =
    if existing_lines = [] then
      header :: data_lines
    else
      existing_lines @ data_lines
  in

  let oc = open_out filename in
  List.iter (fun line -> Printf.fprintf oc "%s\n" line) lines;
  close_out oc

let write_simulation_matrices ~fcfe_file ~fcff_file ~results =
  (* Check if files exist and read existing data *)
  let existing_fcfe_lines = read_csv_lines fcfe_file in
  let existing_fcff_lines = read_csv_lines fcff_file in

  (* Get new data *)
  let all_new_tickers = List.map (fun r -> r.Types.ticker) results in

  (* Filter out duplicate tickers if files already exist *)
  let new_tickers, filtered_results =
    if existing_fcfe_lines = [] then
      (all_new_tickers, results)
    else
      let fcfe_header = List.hd existing_fcfe_lines in
      let existing_tickers = String.split_on_char ',' fcfe_header in
      (* Only keep tickers that don't already exist *)
      let filtered = List.filter (fun r -> not (List.mem r.Types.ticker existing_tickers)) results in
      let filtered_tickers = List.map (fun r -> r.Types.ticker) filtered in
      (filtered_tickers, filtered)
  in

  (* If no new tickers to add, just return *)
  if new_tickers = [] then () else

  (* Get target simulation count from config *)
  let target_sims = List.fold_left (fun acc r -> max acc r.Types.num_simulations) 0 filtered_results in

  (* Merge with existing data *)
  let fcfe_lines, fcff_lines =
    if existing_fcfe_lines = [] then
      (* No existing data, create new *)
      (* IMPORTANT: Use target simulation count to ensure alignment across all tickers *)
      let header = String.concat "," new_tickers in
      let fcfe_data = ref [header] in
      let fcff_data = ref [header] in

      (* Write exactly target_sims rows for perfect alignment *)
      for i = 0 to target_sims - 1 do
        let fcfe_row = List.map (fun r ->
          if i < Array.length r.Types.simulations_fcfe then
            Printf.sprintf "%.2f" r.Types.simulations_fcfe.(i)
          else "nan"  (* Use "nan" instead of empty string for explicit NaN *)
        ) filtered_results in
        fcfe_data := !fcfe_data @ [String.concat "," fcfe_row];

        let fcff_row = List.map (fun r ->
          if i < Array.length r.Types.simulations_fcff then
            Printf.sprintf "%.2f" r.Types.simulations_fcff.(i)
          else "nan"
        ) filtered_results in
        fcff_data := !fcff_data @ [String.concat "," fcff_row];
      done;
      (!fcfe_data, !fcff_data)
    else
      (* Append to existing data *)
      let fcfe_header = List.hd existing_fcfe_lines in
      let fcff_header = List.hd existing_fcff_lines in
      let fcfe_body = List.tl existing_fcfe_lines in
      let fcff_body = List.tl existing_fcff_lines in

      let new_ticker_str = String.concat "," new_tickers in
      let new_fcfe_header = fcfe_header ^ "," ^ new_ticker_str in
      let new_fcff_header = fcff_header ^ "," ^ new_ticker_str in

      (* CRITICAL FIX: Use existing row count to force perfect alignment *)
      (* Do NOT use max - always match existing exactly *)
      let existing_rows = List.length fcfe_body in
      let total_rows = existing_rows in  (* Force exact match *)

      let fcfe_data = ref [new_fcfe_header] in
      let fcff_data = ref [new_fcff_header] in

      Printf.eprintf "Appending %d new ticker(s) to existing %d rows (target: %d simulations)\n"
        (List.length new_tickers) existing_rows target_sims;

      for i = 0 to total_rows - 1 do
        (* Get existing row data, pad with empty if beyond existing data *)
        let existing_fcfe =
          if i < List.length fcfe_body then
            List.nth fcfe_body i
          else
            String.make (String.length fcfe_header) ',' (* Create empty row with right number of commas *)
        in
        let existing_fcff =
          if i < List.length fcff_body then
            List.nth fcff_body i
          else
            String.make (String.length fcff_header) ','
        in

        (* Append new ticker columns, using "nan" for missing data *)
        let new_fcfe_cols = List.map (fun r ->
          if i < Array.length r.Types.simulations_fcfe then
            Printf.sprintf "%.2f" r.Types.simulations_fcfe.(i)
          else "nan"  (* Explicit NaN for padding *)
        ) filtered_results in

        let new_fcff_cols = List.map (fun r ->
          if i < Array.length r.Types.simulations_fcff then
            Printf.sprintf "%.2f" r.Types.simulations_fcff.(i)
          else "nan"
        ) filtered_results in

        let fcfe_row = existing_fcfe ^ "," ^ (String.concat "," new_fcfe_cols) in
        let fcff_row = existing_fcff ^ "," ^ (String.concat "," new_fcff_cols) in

        fcfe_data := !fcfe_data @ [fcfe_row];
        fcff_data := !fcff_data @ [fcff_row];
      done;
      (!fcfe_data, !fcff_data)
  in

  (* Write updated files *)
  let oc_fcfe = open_out fcfe_file in
  List.iter (fun line -> Printf.fprintf oc_fcfe "%s\n" line) fcfe_lines;
  close_out oc_fcfe;

  let oc_fcff = open_out fcff_file in
  List.iter (fun line -> Printf.fprintf oc_fcff "%s\n" line) fcff_lines;
  close_out oc_fcff

let write_market_prices ~filename ~results =
  let existing_lines = read_csv_lines filename in
  let lines =
    if existing_lines = [] then
      (* No existing file, create new with header *)
      let header = "ticker,price" in
      let data_lines = List.map (fun r ->
        Printf.sprintf "%s,%.2f" r.Types.ticker r.Types.price
      ) results in
      header :: data_lines
    else
      (* Filter out duplicate tickers *)
      let existing_tickers = List.tl existing_lines |> List.map (fun line ->
        match String.split_on_char ',' line with
        | ticker :: _ -> ticker
        | [] -> ""
      ) in
      let new_lines = results
        |> List.filter (fun r -> not (List.mem r.Types.ticker existing_tickers))
        |> List.map (fun r -> Printf.sprintf "%s,%.2f" r.Types.ticker r.Types.price)
      in
      existing_lines @ new_lines
  in
  let oc = open_out filename in
  List.iter (fun line -> Printf.fprintf oc "%s\n" line) lines;
  close_out oc

(** Logging *)

let format_valuation_result result =
  let open Types in
  let open Printf in

  let buffer = Buffer.create 2048 in
  let bprintf = Buffer.add_string buffer in

  bprintf (sprintf "\n========================================\n");
  bprintf (sprintf "Probabilistic DCF Valuation: %s\n" result.ticker);
  bprintf (sprintf "========================================\n\n");

  bprintf (sprintf "Simulation Parameters:\n");
  bprintf (sprintf "  Number of simulations: %d\n" result.num_simulations);
  bprintf (sprintf "  Market price: $%.2f\n" result.price);
  bprintf (sprintf "\n");

  bprintf (sprintf "Cost of Capital:\n");
  bprintf (sprintf "  Cost of Equity: %.2f%%\n" (result.cost_of_capital.ce *. 100.0));
  bprintf (sprintf "  WACC: %.2f%%\n" (result.cost_of_capital.wacc *. 100.0));
  bprintf (sprintf "  Leveraged Beta: %.2f\n" result.cost_of_capital.leveraged_beta);
  bprintf (sprintf "\n");

  bprintf (sprintf "FCFE Valuation (Equity Method):\n");
  bprintf (sprintf "  Mean IVPS: $%.2f\n" result.fcfe_stats.mean);
  bprintf (sprintf "  Std Dev: $%.2f\n" result.fcfe_stats.std);
  bprintf (sprintf "  Median: $%.2f\n" result.fcfe_stats.percentile_50);
  bprintf (sprintf "  Range: $%.2f - $%.2f\n" result.fcfe_stats.min result.fcfe_stats.max);
  bprintf (sprintf "  90%% Confidence: $%.2f - $%.2f\n"
    result.fcfe_stats.percentile_5 result.fcfe_stats.percentile_95);
  bprintf (sprintf "  Classification: %s\n" (Statistics.class_to_string result.fcfe_class));
  bprintf (sprintf "  P(Undervalued): %.1f%%\n" (result.fcfe_metrics.prob_undervalued *. 100.0));
  bprintf (sprintf "  Expected Surplus: $%.2f (%.1f%%)\n"
    result.fcfe_metrics.expected_surplus
    (result.fcfe_metrics.expected_surplus_pct *. 100.0));
  bprintf (sprintf "  Tail Risk Metrics:\n");
  bprintf (sprintf "    VaR (5%%): $%.2f\n" result.fcfe_tail_risk.var_5);
  bprintf (sprintf "    CVaR (5%%): $%.2f\n" result.fcfe_tail_risk.cvar_5);
  bprintf (sprintf "    Max Drawdown: $%.2f\n" result.fcfe_tail_risk.max_drawdown);
  bprintf (sprintf "    Downside Deviation: $%.2f\n" result.fcfe_tail_risk.downside_deviation);
  bprintf (sprintf "\n");

  bprintf (sprintf "FCFF Valuation (Firm Method):\n");
  bprintf (sprintf "  Mean IVPS: $%.2f\n" result.fcff_stats.mean);
  bprintf (sprintf "  Std Dev: $%.2f\n" result.fcff_stats.std);
  bprintf (sprintf "  Median: $%.2f\n" result.fcff_stats.percentile_50);
  bprintf (sprintf "  Range: $%.2f - $%.2f\n" result.fcff_stats.min result.fcff_stats.max);
  bprintf (sprintf "  90%% Confidence: $%.2f - $%.2f\n"
    result.fcff_stats.percentile_5 result.fcff_stats.percentile_95);
  bprintf (sprintf "  Classification: %s\n" (Statistics.class_to_string result.fcff_class));
  bprintf (sprintf "  P(Undervalued): %.1f%%\n" (result.fcff_metrics.prob_undervalued *. 100.0));
  bprintf (sprintf "  Expected Surplus: $%.2f (%.1f%%)\n"
    result.fcff_metrics.expected_surplus
    (result.fcff_metrics.expected_surplus_pct *. 100.0));
  bprintf (sprintf "  Tail Risk Metrics:\n");
  bprintf (sprintf "    VaR (5%%): $%.2f\n" result.fcff_tail_risk.var_5);
  bprintf (sprintf "    CVaR (5%%): $%.2f\n" result.fcff_tail_risk.cvar_5);
  bprintf (sprintf "    Max Drawdown: $%.2f\n" result.fcff_tail_risk.max_drawdown);
  bprintf (sprintf "    Downside Deviation: $%.2f\n" result.fcff_tail_risk.downside_deviation);
  bprintf (sprintf "\n");

  (* Stress test scenarios *)
  if List.length result.stress_scenarios > 0 then begin
    bprintf "Stress Test Scenarios:\n";
    List.iter (fun scenario ->
      bprintf (sprintf "\n  %s:\n" scenario.name);
      bprintf (sprintf "    Description: %s\n" scenario.description);
      let fcfe_diff = scenario.ivps_fcfe -. result.price in
      let fcfe_diff_pct = if result.price > 0.0 then (fcfe_diff /. result.price) *. 100.0 else 0.0 in
      bprintf (sprintf "    IVPS (FCFE): $%.2f (%+.1f%% vs market)\n" scenario.ivps_fcfe fcfe_diff_pct);
      let fcff_diff = scenario.ivps_fcff -. result.price in
      let fcff_diff_pct = if result.price > 0.0 then (fcff_diff /. result.price) *. 100.0 else 0.0 in
      bprintf (sprintf "    IVPS (FCFF): $%.2f (%+.1f%% vs market)\n" scenario.ivps_fcff fcff_diff_pct);
      bprintf (sprintf "    Cost of Equity: %.2f%%\n" (scenario.discount_rate_ce *. 100.0));
      bprintf (sprintf "    WACC: %.2f%%\n" (scenario.discount_rate_wacc *. 100.0));
    ) result.stress_scenarios;
    bprintf "\n";
  end;

  bprintf (sprintf "Investment Signal: %s\n" (Statistics.signal_to_colored_string result.signal));
  bprintf (sprintf "  %s\n" (Statistics.signal_explanation result.signal));
  bprintf (sprintf "\n");

  Buffer.contents buffer

let write_log ~filename ~result =
  let oc = open_out filename in
  output_string oc (format_valuation_result result);
  close_out oc

let create_log_filename ~base_dir ~ticker =
  let timestamp = Unix.time () |> Unix.localtime in
  let open Unix in
  Printf.sprintf "%s/dcf_prob_%s_%04d%02d%02d_%02d%02d%02d.log"
    base_dir
    ticker
    (timestamp.tm_year + 1900)
    (timestamp.tm_mon + 1)
    timestamp.tm_mday
    timestamp.tm_hour
    timestamp.tm_min
    timestamp.tm_sec

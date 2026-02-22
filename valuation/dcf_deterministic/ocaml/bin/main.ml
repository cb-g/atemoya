(** Main entry point for DCF deterministic valuation *)

open Dcf_deterministic

let () =
  (* Parse command line arguments *)
  let ticker = ref "" in
  let data_dir = ref "valuation/dcf_deterministic/data" in
  let log_dir = ref "valuation/dcf_deterministic/log" in
  let python_script = ref "valuation/dcf_deterministic/python/fetch_financials.py" in
  let vix_script = ref "valuation/dcf_deterministic/python/fetch_vix.py" in

  (* Optional parameter overrides *)
  let projection_years_override = ref None in
  let terminal_growth_override = ref None in
  let growth_clamp_upper_override = ref None in
  let growth_clamp_lower_override = ref None in
  let rfr_duration_override = ref None in

  (* ERP mode overrides *)
  let erp_mode_override = ref None in  (* "static" or "dynamic" *)
  let vix_override = ref None in       (* Manual VIX override *)

  (* O&G options *)
  let fetch_sec_reserves = ref false in

  let speclist = [
    ("-ticker", Arg.Set_string ticker, "Ticker symbol to value");
    ("-data-dir", Arg.Set_string data_dir, "Data directory path (default: valuation/dcf_deterministic/data)");
    ("-log-dir", Arg.Set_string log_dir, "Log directory path (default: valuation/dcf_deterministic/log)");
    ("-python", Arg.Set_string python_script, "Python fetcher script path");
    ("-vix-script", Arg.Set_string vix_script, "Python VIX fetcher script path");
    ("-projection-years", Arg.Int (fun x -> projection_years_override := Some x), "Override projection years (default: from config)");
    ("-terminal-growth", Arg.Float (fun x -> terminal_growth_override := Some x), "Override terminal growth rate (default: from config)");
    ("-growth-clamp-upper", Arg.Float (fun x -> growth_clamp_upper_override := Some x), "Override upper growth clamp (default: from config)");
    ("-growth-clamp-lower", Arg.Float (fun x -> growth_clamp_lower_override := Some x), "Override lower growth clamp (default: from config)");
    ("-rfr-duration", Arg.Int (fun x -> rfr_duration_override := Some x), "Override risk-free rate duration in years (default: from config)");
    ("-erp-static", Arg.Unit (fun () -> erp_mode_override := Some "static"), "Use static Damodaran ERP (default)");
    ("-erp-dynamic", Arg.Unit (fun () -> erp_mode_override := Some "dynamic"), "Use dynamic VIX-adjusted ERP");
    ("-vix", Arg.Float (fun x -> vix_override := Some x), "Manual VIX override (for dynamic ERP mode)");
    ("-fetch-sec-reserves", Arg.Set fetch_sec_reserves, "Fetch O&G reserves from SEC 10-K (requires edgartools)");
  ] in

  let usage_msg = "DCF Deterministic Valuation Tool\nUsage: dcf_deterministic -ticker TICKER [options]\n\nERP Modes:\n  -erp-static   Use Damodaran country ERPs (default, updated annually)\n  -erp-dynamic  Adjust base ERP using current VIX (real-time risk adjustment)" in
  Arg.parse speclist (fun _ -> ()) usage_msg;

  if !ticker = "" then begin
    Printf.eprintf "Error: -ticker argument is required\n";
    Arg.usage speclist usage_msg;
    exit 1
  end;

  try
    (* Step 1: Fetch financial data using Python script *)
    Printf.printf "Fetching financial data for %s...\n" !ticker;
    let sec_flag = if !fetch_sec_reserves then " --fetch-sec-reserves" else "" in
    let fetch_cmd = Printf.sprintf "uv run %s --ticker %s --output /tmp%s" !python_script !ticker sec_flag in
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

      (* Apply ERP mode override *)
      let erp_mode = match !erp_mode_override with
        | Some "dynamic" -> Types.ERPDynamic
        | Some "static" -> Types.ERPStatic
        | _ -> params.erp_params.mode
      in

      let overridden_params = Types.{
        projection_years = (match !projection_years_override with Some x -> x | None -> params.projection_years);
        terminal_growth_rate = (match !terminal_growth_override with Some x -> x | None -> params.terminal_growth_rate);
        growth_clamp_upper = (match !growth_clamp_upper_override with Some x -> x | None -> params.growth_clamp_upper);
        growth_clamp_lower = (match !growth_clamp_lower_override with Some x -> x | None -> params.growth_clamp_lower);
        rfr_duration = (match !rfr_duration_override with Some x -> x | None -> params.rfr_duration);
        mean_reversion_enabled = params.mean_reversion_enabled;
        mean_reversion_lambda = params.mean_reversion_lambda;
        erp_params = {
          mode = erp_mode;
          vix_mean = params.erp_params.vix_mean;
          vix_sensitivity = params.erp_params.vix_sensitivity;
        };
      } in
      { base_config with params = overridden_params }
    in

    (* Fetch VIX if using dynamic ERP mode *)
    let current_vix = match config.params.erp_params.mode with
      | Types.ERPDynamic ->
          begin match !vix_override with
          | Some vix ->
              Printf.printf "Using manual VIX override: %.2f\n" vix;
              Some vix
          | None ->
              Printf.printf "Fetching current VIX for dynamic ERP...\n";
              let vix_cmd = Printf.sprintf "uv run %s --quiet 2>/dev/null" !vix_script in
              let ic = Unix.open_process_in vix_cmd in
              begin try
                let vix_str = input_line ic in
                let _ = Unix.close_process_in ic in
                let vix = float_of_string vix_str in
                Printf.printf "Current VIX: %.2f\n" vix;
                Some vix
              with End_of_file | Failure _ ->
                Printf.eprintf "Warning: Could not fetch VIX, falling back to static ERP\n";
                let _ = Unix.close_process_in ic in
                None
              end
          end
      | Types.ERPStatic -> None
    in

    (* Step 3: Load market and financial data from /tmp *)
    let market_data_file = Printf.sprintf "/tmp/dcf_market_data_%s.json" !ticker in
    let financial_data_file = Printf.sprintf "/tmp/dcf_financial_data_%s.json" !ticker in

    Printf.printf "Loading market data...\n";
    let market_data = Io.load_market_data market_data_file in

    Printf.printf "Loading financial data...\n";
    let financial_data = Io.load_financial_data financial_data_file in

    (* Check if this is a bank - use different valuation model *)
    if financial_data.is_bank then begin
      Printf.printf "Detected bank: using Excess Return Model...\n";

      (* Get parameters for bank valuation *)
      let country = market_data.country in

      (* Get risk-free rate *)
      let rfr_duration = config.params.rfr_duration in
      let risk_free_rate =
        match List.assoc_opt country config.risk_free_rates with
        | Some rates ->
            (match List.assoc_opt rfr_duration rates with
             | Some rate -> rate
             | None -> snd (List.hd rates))
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

      (* Run bank valuation *)
      let bank_result = Bank.value_bank
        ~financial:financial_data
        ~market:market_data
        ~risk_free_rate
        ~equity_risk_premium
        ~terminal_growth_rate:config.params.terminal_growth_rate
        ~projection_years:config.params.projection_years
      in

      (* Create wrapper result for output compatibility *)
      let empty_projection = Types.{
        fcfe = [||];
        fcff = [||];
        growth_rate_fcfe = 0.0;
        growth_rate_fcff = 0.0;
        growth_clamped_fcfe = false;
        growth_clamped_fcff = false;
      } in

      let empty_cost_of_capital = Types.{
        ce = bank_result.cost_of_equity;
        cb = 0.0;
        wacc = bank_result.cost_of_equity;
        leveraged_beta = 1.0;
        risk_free_rate;
        equity_risk_premium;
        erp_source_used = Types.Static;
        erp_base = equity_risk_premium;
        erp_vix_adjustment = 1.0;
        smb_loading = 0.0;
        hml_loading = 0.0;
        size_premium = 0.0;
        value_premium = 0.0;
      } in

      let result = Types.{
        ticker = market_data.ticker;
        price = market_data.price;
        pve = 0.0;
        pvf_minus_debt = 0.0;
        ivps_fcfe = bank_result.fair_value_per_share;
        ivps_fcff = bank_result.fair_value_per_share;
        margin_of_safety_fcfe = bank_result.margin_of_safety;
        margin_of_safety_fcff = bank_result.margin_of_safety;
        implied_growth_fcfe = None;
        implied_growth_fcff = None;
        signal = bank_result.signal;
        cost_of_capital = empty_cost_of_capital;
        projection = empty_projection;
        bank_result = Some bank_result;
        insurance_result = None;
        oil_gas_result = None;
      } in

      (* Output results *)
      Printf.printf "%s\n" (Io.format_valuation_result result);

      (* Write to log file *)
      let log_filename = Io.create_log_filename ~base_dir:!log_dir ~ticker:!ticker in
      Io.write_log ~filename:log_filename ~result;
      Printf.printf "Results written to: %s\n" log_filename
    end
    else if financial_data.is_insurance then begin
      Printf.printf "Detected insurance company: using Float-Based Model...\n";

      (* Get parameters for insurance valuation *)
      let country = market_data.country in

      (* Get risk-free rate *)
      let rfr_duration = config.params.rfr_duration in
      let risk_free_rate =
        match List.assoc_opt country config.risk_free_rates with
        | Some rates ->
            (match List.assoc_opt rfr_duration rates with
             | Some rate -> rate
             | None -> snd (List.hd rates))
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

      (* Run insurance valuation *)
      let insurance_result = Insurance.value_insurance
        ~financial:financial_data
        ~market:market_data
        ~risk_free_rate
        ~equity_risk_premium
        ~terminal_growth_rate:config.params.terminal_growth_rate
        ~projection_years:config.params.projection_years
      in

      (* Create wrapper result for output compatibility *)
      let empty_projection = Types.{
        fcfe = [||];
        fcff = [||];
        growth_rate_fcfe = 0.0;
        growth_rate_fcff = 0.0;
        growth_clamped_fcfe = false;
        growth_clamped_fcff = false;
      } in

      let empty_cost_of_capital = Types.{
        ce = insurance_result.cost_of_equity;
        cb = 0.0;
        wacc = insurance_result.cost_of_equity;
        leveraged_beta = 1.0;
        risk_free_rate;
        equity_risk_premium;
        erp_source_used = Types.Static;
        erp_base = equity_risk_premium;
        erp_vix_adjustment = 1.0;
        smb_loading = 0.0;
        hml_loading = 0.0;
        size_premium = 0.0;
        value_premium = 0.0;
      } in

      let result = Types.{
        ticker = market_data.ticker;
        price = market_data.price;
        pve = 0.0;
        pvf_minus_debt = 0.0;
        ivps_fcfe = insurance_result.fair_value_per_share;
        ivps_fcff = insurance_result.fair_value_per_share;
        margin_of_safety_fcfe = insurance_result.margin_of_safety;
        margin_of_safety_fcff = insurance_result.margin_of_safety;
        implied_growth_fcfe = None;
        implied_growth_fcff = None;
        signal = insurance_result.signal;
        cost_of_capital = empty_cost_of_capital;
        projection = empty_projection;
        bank_result = None;
        insurance_result = Some insurance_result;
        oil_gas_result = None;
      } in

      (* Output results *)
      Printf.printf "%s\n" (Io.format_valuation_result result);

      (* Write to log file *)
      let log_filename = Io.create_log_filename ~base_dir:!log_dir ~ticker:!ticker in
      Io.write_log ~filename:log_filename ~result;
      Printf.printf "Results written to: %s\n" log_filename
    end
    else if financial_data.is_oil_gas then begin
      Printf.printf "Detected O&G E&P company: using NAV Model...\n";

      (* Get parameters for O&G valuation *)
      let country = market_data.country in

      (* Get risk-free rate *)
      let rfr_duration = config.params.rfr_duration in
      let risk_free_rate =
        match List.assoc_opt country config.risk_free_rates with
        | Some rates ->
            (match List.assoc_opt rfr_duration rates with
             | Some rate -> rate
             | None -> snd (List.hd rates))
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

      let tax_rate =
        match List.assoc_opt country config.tax_rates with
        | Some rate -> rate
        | None ->
            Printf.eprintf "Error: No tax rate data for country %s\n" country;
            exit 1
      in

      (* Default commodity prices - could be fetched from market data *)
      let oil_price = 75.0 in  (* WTI *)
      let gas_price = 3.0 in   (* Henry Hub *)

      (* Run O&G valuation *)
      let oil_gas_result = Oil_gas.value_oil_gas
        ~financial:financial_data
        ~market:market_data
        ~risk_free_rate
        ~equity_risk_premium
        ~tax_rate
        ~oil_price
        ~gas_price
      in

      (* Create wrapper result for output compatibility *)
      let empty_projection = Types.{
        fcfe = [||];
        fcff = [||];
        growth_rate_fcfe = 0.0;
        growth_rate_fcff = 0.0;
        growth_clamped_fcfe = false;
        growth_clamped_fcff = false;
      } in

      let empty_cost_of_capital = Types.{
        ce = oil_gas_result.cost_of_capital;
        cb = 0.0;
        wacc = oil_gas_result.cost_of_capital;
        leveraged_beta = 1.0;
        risk_free_rate;
        equity_risk_premium;
        erp_source_used = Types.Static;
        erp_base = equity_risk_premium;
        erp_vix_adjustment = 1.0;
        smb_loading = 0.0;
        hml_loading = 0.0;
        size_premium = 0.0;
        value_premium = 0.0;
      } in

      let result = Types.{
        ticker = market_data.ticker;
        price = market_data.price;
        pve = 0.0;
        pvf_minus_debt = 0.0;
        ivps_fcfe = oil_gas_result.fair_value_per_share;
        ivps_fcff = oil_gas_result.fair_value_per_share;
        margin_of_safety_fcfe = oil_gas_result.margin_of_safety;
        margin_of_safety_fcff = oil_gas_result.margin_of_safety;
        implied_growth_fcfe = None;
        implied_growth_fcff = None;
        signal = oil_gas_result.signal;
        cost_of_capital = empty_cost_of_capital;
        projection = empty_projection;
        bank_result = None;
        insurance_result = None;
        oil_gas_result = Some oil_gas_result;
      } in

      (* Output results *)
      Printf.printf "%s\n" (Io.format_valuation_result result);

      (* Write to log file *)
      let log_filename = Io.create_log_filename ~base_dir:!log_dir ~ticker:!ticker in
      Io.write_log ~filename:log_filename ~result;
      Printf.printf "Results written to: %s\n" log_filename
    end
    else begin
    (* Standard non-bank/non-insurance valuation follows *)

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

    let terminal_growth_rate = config.params.terminal_growth_rate in

    (* Step 5: Calculate cost of capital *)
    Printf.printf "Calculating cost of capital...\n";

    (* Build ERP config based on mode *)
    let erp_config = match (config.params.erp_params.mode, current_vix) with
      | (Types.ERPDynamic, Some vix) ->
          (* Dynamic mode with VIX available *)
          Some Types.{
            source = Dynamic {
              vix_mean = config.params.erp_params.vix_mean;
              sensitivity = config.params.erp_params.vix_sensitivity;
            };
            base_erp = equity_risk_premium;
            current_vix = Some vix;
          }
      | _ ->
          (* Static mode or VIX unavailable - use default static *)
          None
    in

    let cost_of_capital = Capital_structure.calculate_cost_of_capital
      ?erp_config
      ~market_data
      ~financial_data
      ~unlevered_beta
      ~risk_free_rate
      ~equity_risk_premium
      ~tax_rate
      ()
    in

    (* Step 6: Create cash flow projection *)
    Printf.printf "Projecting cash flows...\n";
    let projection = Projection.create_projection
      ~financial_data
      ~market_data
      ~tax_rate
      ~params:config.params
    in

    (* Step 7: Calculate present values *)
    Printf.printf "Calculating present values...\n";
    let pve_opt = Valuation.calculate_pve
      ~projection
      ~cost_of_equity:cost_of_capital.ce
      ~terminal_growth_rate
    in

    let pvf_opt = Valuation.calculate_pvf
      ~projection
      ~wacc:cost_of_capital.wacc
      ~terminal_growth_rate
    in

    match pve_opt, pvf_opt with
    | None, _ ->
        Printf.eprintf "Error: Failed to calculate PVE (terminal growth >= discount rate?)\n";
        exit 1
    | _, None ->
        Printf.eprintf "Error: Failed to calculate PVF (terminal growth >= WACC?)\n";
        exit 1
    | Some pve, Some pvf ->
        (* Calculate intrinsic values per share *)
        let ivps_fcfe = pve /. market_data.shares_outstanding in
        let pvf_minus_debt = pvf -. market_data.mvb in
        let ivps_fcff = pvf_minus_debt /. market_data.shares_outstanding in

        (* Calculate margins of safety *)
        let margin_of_safety_fcfe = Signal.calculate_margin_of_safety
          ~intrinsic_value:ivps_fcfe
          ~market_price:market_data.price
        in
        let margin_of_safety_fcff = Signal.calculate_margin_of_safety
          ~intrinsic_value:ivps_fcff
          ~market_price:market_data.price
        in

        (* Solve for implied growth rates *)
        Printf.printf "Solving for market-implied growth rates...\n";
        let fcfe_0 = Cash_flow.calculate_fcfe ~financial_data ~market_data in
        let fcff_0 = Cash_flow.calculate_fcff ~financial_data ~tax_rate in

        let implied_growth_fcfe = Solver.solve_implied_fcfe_growth
          ~fcfe_0
          ~shares_outstanding:market_data.shares_outstanding
          ~market_price:market_data.price
          ~cost_of_equity:cost_of_capital.ce
          ~terminal_growth_rate
          ~projection_years:config.params.projection_years
          ~max_iterations:100
          ~tolerance:0.01
        in

        let implied_growth_fcff = Solver.solve_implied_fcff_growth
          ~fcff_0
          ~shares_outstanding:market_data.shares_outstanding
          ~market_price:market_data.price
          ~debt:market_data.mvb
          ~wacc:cost_of_capital.wacc
          ~terminal_growth_rate
          ~projection_years:config.params.projection_years
          ~max_iterations:100
          ~tolerance:0.01
        in

        (* Generate investment signal *)
        let signal = Signal.classify_investment_signal
          ~ivps_fcfe
          ~ivps_fcff
          ~market_price:market_data.price
          ~tolerance:0.05  (* 5% tolerance *)
        in

        (* Create valuation result *)
        let result = Types.{
          ticker = market_data.ticker;
          price = market_data.price;
          pve;
          pvf_minus_debt;
          ivps_fcfe;
          ivps_fcff;
          margin_of_safety_fcfe;
          margin_of_safety_fcff;
          implied_growth_fcfe;
          implied_growth_fcff;
          signal;
          cost_of_capital;
          projection;
          bank_result = None;
          insurance_result = None;
          oil_gas_result = None;
        } in

        (* Step 8: Output results *)
        Printf.printf "%s\n" (Io.format_valuation_result result);

        (* Step 9: Write to log file *)
        let log_filename = Io.create_log_filename ~base_dir:!log_dir ~ticker:!ticker in
        Io.write_log ~filename:log_filename ~result;
        Printf.printf "Results written to: %s\n" log_filename
    end  (* end of non-bank else branch *)

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

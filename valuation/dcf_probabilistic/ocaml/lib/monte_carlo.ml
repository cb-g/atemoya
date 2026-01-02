(** Monte Carlo simulation engine for probabilistic DCF *)

open Types

(** Helper: Project cash flows with time-varying growth rates *)
let project_cash_flows_varying ~cf_0 ~growth_rates =
  (* growth_rates is an array of length = projection years *)
  let _, cash_flows = Array.fold_left (fun (prev_cf, cfs) g_t ->
    let next_cf = prev_cf *. (1.0 +. g_t) in
    (next_cf, next_cf :: cfs)
  ) (cf_0, []) growth_rates in
  Array.of_list (List.rev cash_flows)

(** Helper: Project cash flows with constant growth (legacy) *)
let project_cash_flows ~cf_0 ~growth_rate ~years =
  Array.init years (fun i ->
    let t = float_of_int (i + 1) in
    cf_0 *. ((1.0 +. growth_rate) ** t)
  )

(** Generate time-varying growth path with mean reversion *)
let generate_growth_path ~initial_growth ~terminal_growth ~years ~lambda =
  (* g_t = g_LT + (g_0 - g_LT) * exp(-λ * t) *)
  Array.init years (fun i ->
    let t = float_of_int (i + 1) in
    let decay = exp (-.lambda *. t) in
    terminal_growth +. (initial_growth -. terminal_growth) *. decay
  )

(** Helper: Calculate present value with terminal value *)
let calculate_pv ~cash_flows ~discount_rate ~terminal_growth_rate =
  let h = Array.length cash_flows in
  if h = 0 || discount_rate <= terminal_growth_rate then
    None
  else
    (* PV of explicit forecast period *)
    let pv_explicit = Array.fold_left (fun (acc, t) cf ->
      let pv = cf /. ((1.0 +. discount_rate) ** float_of_int t) in
      (acc +. pv, t + 1)
    ) (0.0, 1) cash_flows |> fst in

    (* Terminal value *)
    let final_cf = cash_flows.(h - 1) in
    let tv = final_cf *. (1.0 +. terminal_growth_rate) /. (discount_rate -. terminal_growth_rate) in
    let pv_terminal = tv /. ((1.0 +. discount_rate) ** float_of_int h) in

    Some (pv_explicit +. pv_terminal)

(** Run one FCFE simulation *)
let simulate_fcfe_once ~market_data ~time_series ~cost_of_capital ~(config : simulation_config) ~roe_prior ~retention_prior =
  (* Sample stochastic discount rates if enabled *)
  let ce =
    if config.use_stochastic_discount_rates then
      if config.use_regime_switching then
        (* BEST: Regime-switching with correlation (captures fat tails) *)
        match config.regime_config with
        | Some regime_cfg ->
            let (rfr, erp, beta, _is_crisis) = Sampling.sample_discount_rates_regime_switching
              ~base_rfr:cost_of_capital.risk_free_rate
              ~base_erp:cost_of_capital.equity_risk_premium
              ~base_beta:cost_of_capital.leveraged_beta
              ~regime_config:regime_cfg
            in
            rfr +. (beta *. erp)
        | None ->
            (* Fallback if regime_config missing *)
            cost_of_capital.ce
      else if config.use_correlated_discount_rates then
        (* RECOMMENDED: Sample with correlation *)
        let (rfr, erp, beta) = Sampling.sample_discount_rates_correlated
          ~base_rfr:cost_of_capital.risk_free_rate
          ~base_erp:cost_of_capital.equity_risk_premium
          ~base_beta:cost_of_capital.leveraged_beta
          ~rfr_vol:config.rfr_volatility
          ~erp_vol:config.erp_volatility
          ~beta_vol:config.beta_volatility
          ~correlation:config.discount_rate_correlation
        in
        rfr +. (beta *. erp)
      else
        (* LEGACY: Independent sampling (inferior) *)
        let rfr = Sampling.sample_risk_free_rate
          ~base_rfr:cost_of_capital.risk_free_rate
          ~volatility:config.rfr_volatility in
        let beta = Sampling.sample_beta
          ~base_beta:cost_of_capital.leveraged_beta
          ~volatility:config.beta_volatility in
        let erp = Sampling.sample_equity_risk_premium
          ~base_erp:cost_of_capital.equity_risk_premium
          ~volatility:config.erp_volatility in
        rfr +. (beta *. erp)
    else
      cost_of_capital.ce
  in

  (* Sample initial growth rate *)
  let initial_growth_fcfe = Sampling.sample_growth_rate_fcfe
    ~time_series ~roe_prior ~retention_prior ~config
  in

  (* Sample financial metrics - copula or independent *)
  let (ni_raw, _ebit, capex, depreciation, ca, cl) =
    if config.use_copula_financials then
      (* RECOMMENDED: Copula-based correlated sampling *)
      Copula.sample_correlated_financials
        ~time_series
        ~correlation:config.financials_correlation
    else
      (* LEGACY: Independent sampling (ignores correlations) *)
      let ni = Sampling.sample_financial_metric
        ~time_series:time_series.net_income
        ~cap:(Some (market_data.mve *. 0.3))
      in
      let ebit = Sampling.sample_from_time_series time_series.ebit in
      let capex = abs_float (Sampling.sample_from_time_series time_series.capex) in
      let depreciation = Sampling.sample_from_time_series time_series.depreciation in
      let ca = Sampling.sample_from_time_series time_series.current_assets in
      let cl = Sampling.sample_from_time_series time_series.current_liabilities in
      (ni, ebit, capex, depreciation, ca, cl)
  in

  (* Apply cap to NI for FCFE *)
  let ni = min ni_raw (market_data.mve *. 0.3) in
  let ca_prior = if Array.length time_series.current_assets > 1 then
      time_series.current_assets.(Array.length time_series.current_assets - 2)
    else ca in
  let cl_prior = if Array.length time_series.current_liabilities > 1 then
      time_series.current_liabilities.(Array.length time_series.current_liabilities - 2)
    else cl in
  let delta_wc = (ca -. cl) -. (ca_prior -. cl_prior) in

  (* Calculate initial FCFE *)
  let total_value = market_data.mve +. market_data.mvb in
  let tdr = if total_value = 0.0 then 0.0 else market_data.mvb /. total_value in
  let reinvestment = capex +. delta_wc -. depreciation in
  let net_borrowing = tdr *. reinvestment in
  let fcfe_0 = ni +. depreciation -. reinvestment +. net_borrowing in

  (* Project FCFE with time-varying or constant growth *)
  let fcfe, growth_rate_fcfe =
    if config.use_time_varying_growth then
      let growth_path = generate_growth_path
        ~initial_growth:initial_growth_fcfe
        ~terminal_growth:config.terminal_growth_rate
        ~years:config.projection_years
        ~lambda:config.growth_mean_reversion_speed in
      let cfs = project_cash_flows_varying ~cf_0:fcfe_0 ~growth_rates:growth_path in
      (cfs, growth_path.(0))  (* Return first year growth as representative *)
    else
      let cfs = project_cash_flows
        ~cf_0:fcfe_0
        ~growth_rate:initial_growth_fcfe
        ~years:config.projection_years in
      (cfs, initial_growth_fcfe)
  in

  (* Calculate present value with sampled discount rate *)
  let pve = match calculate_pv
    ~cash_flows:fcfe
    ~discount_rate:ce
    ~terminal_growth_rate:config.terminal_growth_rate with
    | Some v -> v
    | None -> 0.0
  in

  (* Intrinsic value per share *)
  let ivps_fcfe = if market_data.shares_outstanding = 0.0 then 0.0
    else pve /. market_data.shares_outstanding in

  (* Debug NaN generation *)
  if classify_float ivps_fcfe = FP_nan && Random.float 1.0 < 0.01 then begin  (* Log 1% of NaN cases *)
    Printf.eprintf "[FCFE NaN Debug] fcfe_0=%.2f, ce=%.4f, growth=%.4f, pve=%.2f, shares=%.2f\n"
      fcfe_0 ce growth_rate_fcfe pve market_data.shares_outstanding;
    if Array.length fcfe > 0 then
      Printf.eprintf "  fcfe[0]=%.2f, fcfe[last]=%.2f\n" fcfe.(0) fcfe.(Array.length fcfe - 1)
  end;

  {
    fcfe;
    fcff = [||];  (* Not used in FCFE simulation *)
    growth_rate_fcfe;
    growth_rate_fcff = 0.0;
    pve;
    pvf = 0.0;
    ivps_fcfe;
    ivps_fcff = 0.0;
  }

(** Run one FCFF simulation *)
let simulate_fcff_once ~market_data ~time_series ~cost_of_capital ~(config : simulation_config) ~roic_prior ~tax_rate =
  (* Sample stochastic discount rates if enabled *)
  let wacc =
    if config.use_stochastic_discount_rates then
      let ce =
        if config.use_regime_switching then
          (* BEST: Regime-switching with correlation (captures fat tails) *)
          match config.regime_config with
          | Some regime_cfg ->
              let (rfr, erp, beta, _is_crisis) = Sampling.sample_discount_rates_regime_switching
                ~base_rfr:cost_of_capital.risk_free_rate
                ~base_erp:cost_of_capital.equity_risk_premium
                ~base_beta:cost_of_capital.leveraged_beta
                ~regime_config:regime_cfg
              in
              rfr +. (beta *. erp)
          | None ->
              (* Fallback if regime_config missing *)
              cost_of_capital.ce
        else if config.use_correlated_discount_rates then
          (* RECOMMENDED: Sample with correlation *)
          let (rfr, erp, beta) = Sampling.sample_discount_rates_correlated
            ~base_rfr:cost_of_capital.risk_free_rate
            ~base_erp:cost_of_capital.equity_risk_premium
            ~base_beta:cost_of_capital.leveraged_beta
            ~rfr_vol:config.rfr_volatility
            ~erp_vol:config.erp_volatility
            ~beta_vol:config.beta_volatility
            ~correlation:config.discount_rate_correlation
          in
          rfr +. (beta *. erp)
        else
          (* LEGACY: Independent sampling (inferior) *)
          let rfr = Sampling.sample_risk_free_rate
            ~base_rfr:cost_of_capital.risk_free_rate
            ~volatility:config.rfr_volatility in
          let beta = Sampling.sample_beta
            ~base_beta:cost_of_capital.leveraged_beta
            ~volatility:config.beta_volatility in
          let erp = Sampling.sample_equity_risk_premium
            ~base_erp:cost_of_capital.equity_risk_premium
            ~volatility:config.erp_volatility in
          rfr +. (beta *. erp)
      in
      (* Recompute WACC with sampled components *)
      let total_value = market_data.mve +. market_data.mvb in
      if total_value = 0.0 then ce
      else
        let equity_weight = market_data.mve /. total_value in
        let debt_weight = market_data.mvb /. total_value in
        (equity_weight *. ce) +. (debt_weight *. cost_of_capital.cb *. (1.0 -. tax_rate))
    else
      cost_of_capital.wacc
  in

  (* Sample initial growth rate *)
  let initial_growth_fcff = Sampling.sample_growth_rate_fcff
    ~time_series ~roic_prior ~config
  in

  (* Sample financial metrics - copula or independent *)
  let (_ni, ebit_raw, capex, depreciation, ca, cl) =
    if config.use_copula_financials then
      (* RECOMMENDED: Copula-based correlated sampling *)
      Copula.sample_correlated_financials
        ~time_series
        ~correlation:config.financials_correlation
    else
      (* LEGACY: Independent sampling (ignores correlations) *)
      let ni = Sampling.sample_from_time_series time_series.net_income in
      let ebit = Sampling.sample_financial_metric
        ~time_series:time_series.ebit
        ~cap:(Some (market_data.mve *. 0.5))
      in
      let capex = abs_float (Sampling.sample_from_time_series time_series.capex) in
      let depreciation = Sampling.sample_from_time_series time_series.depreciation in
      let ca = Sampling.sample_from_time_series time_series.current_assets in
      let cl = Sampling.sample_from_time_series time_series.current_liabilities in
      (ni, ebit, capex, depreciation, ca, cl)
  in

  (* Apply cap to EBIT for FCFF *)
  let ebit = min ebit_raw (market_data.mve *. 0.5) in
  let ca_prior = if Array.length time_series.current_assets > 1 then
      time_series.current_assets.(Array.length time_series.current_assets - 2)
    else ca in
  let cl_prior = if Array.length time_series.current_liabilities > 1 then
      time_series.current_liabilities.(Array.length time_series.current_liabilities - 2)
    else cl in
  let delta_wc = (ca -. cl) -. (ca_prior -. cl_prior) in

  (* Calculate initial FCFF *)
  let nopat = ebit *. (1.0 -. tax_rate) in
  let fcff_0 = nopat +. depreciation -. capex -. delta_wc in

  (* Project FCFF with time-varying or constant growth *)
  let fcff, growth_rate_fcff =
    if config.use_time_varying_growth then
      let growth_path = generate_growth_path
        ~initial_growth:initial_growth_fcff
        ~terminal_growth:config.terminal_growth_rate
        ~years:config.projection_years
        ~lambda:config.growth_mean_reversion_speed in
      let cfs = project_cash_flows_varying ~cf_0:fcff_0 ~growth_rates:growth_path in
      (cfs, growth_path.(0))  (* Return first year growth as representative *)
    else
      let cfs = project_cash_flows
        ~cf_0:fcff_0
        ~growth_rate:initial_growth_fcff
        ~years:config.projection_years in
      (cfs, initial_growth_fcff)
  in

  (* Calculate present value with sampled discount rate *)
  let pvf = match calculate_pv
    ~cash_flows:fcff
    ~discount_rate:wacc
    ~terminal_growth_rate:config.terminal_growth_rate with
    | Some v -> v
    | None -> 0.0
  in

  (* Intrinsic value per share (firm value minus debt) *)
  let pvf_minus_debt = pvf -. market_data.mvb in
  let ivps_fcff = if market_data.shares_outstanding = 0.0 then 0.0
    else pvf_minus_debt /. market_data.shares_outstanding in

  (* Debug NaN generation *)
  if classify_float ivps_fcff = FP_nan && Random.float 1.0 < 0.01 then begin  (* Log 1% of NaN cases *)
    Printf.eprintf "[FCFF NaN Debug] fcff_0=%.2f, wacc=%.4f, growth=%.4f, pvf=%.2f, mvb=%.2f, shares=%.2f\n"
      fcff_0 wacc growth_rate_fcff pvf market_data.mvb market_data.shares_outstanding;
    if Array.length fcff > 0 then
      Printf.eprintf "  fcff[0]=%.2f, fcff[last]=%.2f\n" fcff.(0) fcff.(Array.length fcff - 1)
  end;

  {
    fcfe = [||];
    fcff;
    growth_rate_fcfe = 0.0;
    growth_rate_fcff;
    pve = 0.0;
    pvf;
    ivps_fcfe = 0.0;
    ivps_fcff;
  }

(** Run FCFE simulations *)
let run_fcfe_simulations ~market_data ~time_series ~cost_of_capital ~(config : simulation_config) ~roe_prior ~retention_prior =
  let nan_count = ref 0 in
  let results = Array.init config.num_simulations (fun i ->
    let sample = simulate_fcfe_once
      ~market_data ~time_series ~cost_of_capital ~config ~roe_prior ~retention_prior
    in
    (* Detect NaN and log *)
    if classify_float sample.ivps_fcfe = FP_nan then begin
      incr nan_count;
      if !nan_count <= 5 then  (* Log first 5 NaN occurrences *)
        Printf.eprintf "[FCFE NaN #%d at iteration %d] pve=%.2f, shares=%.2f, growth_rate=%.4f\n"
          !nan_count i sample.pve market_data.shares_outstanding sample.growth_rate_fcfe
    end;
    sample.ivps_fcfe
  ) in
  if !nan_count > 0 then
    Printf.eprintf "Total FCFE NaN count: %d / %d (%.1f%%)\n" !nan_count config.num_simulations
      (float_of_int !nan_count *. 100.0 /. float_of_int config.num_simulations);
  results

(** Run FCFF simulations *)
let run_fcff_simulations ~market_data ~time_series ~cost_of_capital ~(config : simulation_config) ~roic_prior ~tax_rate =
  let nan_count = ref 0 in
  let results = Array.init config.num_simulations (fun i ->
    let sample = simulate_fcff_once
      ~market_data ~time_series ~cost_of_capital ~config ~roic_prior ~tax_rate
    in
    (* Detect NaN and log *)
    if classify_float sample.ivps_fcff = FP_nan then begin
      incr nan_count;
      if !nan_count <= 5 then  (* Log first 5 NaN occurrences *)
        Printf.eprintf "[FCFF NaN #%d at iteration %d] pvf=%.2f, mvb=%.2f, shares=%.2f, growth_rate=%.4f\n"
          !nan_count i sample.pvf market_data.mvb market_data.shares_outstanding sample.growth_rate_fcff
    end;
    sample.ivps_fcff
  ) in
  if !nan_count > 0 then
    Printf.eprintf "Total FCFF NaN count: %d / %d (%.1f%%)\n" !nan_count config.num_simulations
      (float_of_int !nan_count *. 100.0 /. float_of_int config.num_simulations);
  results

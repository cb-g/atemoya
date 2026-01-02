(** Stress testing module for scenario analysis *)

open Types

(** Helper: Calculate FCFE under stress conditions (deterministic, single valuation) *)
let calculate_fcfe_stress
    ~market_data ~time_series ~ce_stress ~roe_prior:_ ~retention_prior:_
    ~terminal_growth ~projection_years ~growth_shock =

  (* Calculate historical growth rates *)
  let ni_ts = time_series.net_income in
  let growth_rates = Sampling.compute_growth_rates ni_ts in
  let cleaned_growth = Sampling.clean_array growth_rates in

  (* Apply growth shock to mean growth *)
  let mean_growth = if Array.length cleaned_growth > 0 then
      Sampling.mean cleaned_growth
    else 0.05 in
  let stressed_growth = Sampling.clamp
    ~value:(mean_growth +. growth_shock)
    ~lower:(-0.3) ~upper:0.5 in

  (* Sample financial metrics (use most recent values, not stochastic) *)
  let ni = if Array.length ni_ts > 0 then
      ni_ts.(Array.length ni_ts - 1)
    else 0.0 in

  let capex = if Array.length time_series.capex > 0 then
      abs_float time_series.capex.(Array.length time_series.capex - 1)
    else 0.0 in

  let depreciation = if Array.length time_series.depreciation > 0 then
      time_series.depreciation.(Array.length time_series.depreciation - 1)
    else 0.0 in

  (* Working capital change *)
  let ca = if Array.length time_series.current_assets > 0 then
      time_series.current_assets.(Array.length time_series.current_assets - 1)
    else 0.0 in
  let cl = if Array.length time_series.current_liabilities > 0 then
      time_series.current_liabilities.(Array.length time_series.current_liabilities - 1)
    else 0.0 in
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

  (* Project FCFE with stressed growth *)
  let fcfe = Array.init projection_years (fun i ->
    let t = float_of_int (i + 1) in
    fcfe_0 *. ((1.0 +. stressed_growth) ** t)
  ) in

  (* Calculate PV with stressed discount rate *)
  if ce_stress <= terminal_growth then
    0.0  (* Invalid scenario *)
  else
    (* PV of explicit forecast period *)
    let pv_explicit = Array.fold_left (fun (acc, t) cf ->
      let pv = cf /. ((1.0 +. ce_stress) ** float_of_int t) in
      (acc +. pv, t + 1)
    ) (0.0, 1) fcfe |> fst in

    (* Terminal value *)
    let final_cf = fcfe.(projection_years - 1) in
    let tv = final_cf *. (1.0 +. terminal_growth) /. (ce_stress -. terminal_growth) in
    let pv_terminal = tv /. ((1.0 +. ce_stress) ** float_of_int projection_years) in

    (* Intrinsic value per share *)
    let pve = pv_explicit +. pv_terminal in
    if market_data.shares_outstanding = 0.0 then 0.0
    else pve /. market_data.shares_outstanding

(** Helper: Calculate FCFF under stress conditions (deterministic, single valuation) *)
let calculate_fcff_stress
    ~market_data ~time_series ~wacc_stress ~roic_prior:_ ~tax_rate
    ~terminal_growth ~projection_years ~growth_shock =

  (* Calculate historical growth rates *)
  let ebit_ts = time_series.ebit in
  let growth_rates = Sampling.compute_growth_rates ebit_ts in
  let cleaned_growth = Sampling.clean_array growth_rates in

  (* Apply growth shock to mean growth *)
  let mean_growth = if Array.length cleaned_growth > 0 then
      Sampling.mean cleaned_growth
    else 0.05 in
  let stressed_growth = Sampling.clamp
    ~value:(mean_growth +. growth_shock)
    ~lower:(-0.3) ~upper:0.5 in

  (* Sample financial metrics (use most recent values, not stochastic) *)
  let ebit = if Array.length ebit_ts > 0 then
      ebit_ts.(Array.length ebit_ts - 1)
    else 0.0 in

  let capex = if Array.length time_series.capex > 0 then
      abs_float time_series.capex.(Array.length time_series.capex - 1)
    else 0.0 in

  let depreciation = if Array.length time_series.depreciation > 0 then
      time_series.depreciation.(Array.length time_series.depreciation - 1)
    else 0.0 in

  (* Working capital change *)
  let ca = if Array.length time_series.current_assets > 0 then
      time_series.current_assets.(Array.length time_series.current_assets - 1)
    else 0.0 in
  let cl = if Array.length time_series.current_liabilities > 0 then
      time_series.current_liabilities.(Array.length time_series.current_liabilities - 1)
    else 0.0 in
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

  (* Project FCFF with stressed growth *)
  let fcff = Array.init projection_years (fun i ->
    let t = float_of_int (i + 1) in
    fcff_0 *. ((1.0 +. stressed_growth) ** t)
  ) in

  (* Calculate PV with stressed discount rate *)
  if wacc_stress <= terminal_growth then
    0.0  (* Invalid scenario *)
  else
    (* PV of explicit forecast period *)
    let pv_explicit = Array.fold_left (fun (acc, t) cf ->
      let pv = cf /. ((1.0 +. wacc_stress) ** float_of_int t) in
      (acc +. pv, t + 1)
    ) (0.0, 1) fcff |> fst in

    (* Terminal value *)
    let final_cf = fcff.(projection_years - 1) in
    let tv = final_cf *. (1.0 +. terminal_growth) /. (wacc_stress -. terminal_growth) in
    let pv_terminal = tv /. ((1.0 +. wacc_stress) ** float_of_int projection_years) in

    (* Intrinsic value per share (firm value minus debt) *)
    let pvf = pv_explicit +. pv_terminal in
    let pvf_minus_debt = pvf -. market_data.mvb in
    if market_data.shares_outstanding = 0.0 then 0.0
    else pvf_minus_debt /. market_data.shares_outstanding

(** Generate all predefined stress scenarios *)
let generate_stress_scenarios
    ~market_data ~time_series ~cost_of_capital ~config
    ~roe_prior ~retention_prior ~roic_prior ~tax_rate =

  let terminal_growth = config.terminal_growth_rate in
  let projection_years = config.projection_years in

  (* Define stress scenarios with {name, description, rfr, erp, beta_mult, growth_shock} *)
  let scenarios = [
    (* 2008 Financial Crisis: Near-zero rates, sky-high ERP, elevated beta, negative growth *)
    ("2008 Financial Crisis",
     "RFR=0.25%, ERP=10%, Beta×1.5, Growth -10%",
     0.0025, 0.10, 1.5, -0.10);

    (* Volcker High Rates (1980): Very high rates, moderate ERP, growth slowdown *)
    ("Volcker High Rates (1980)",
     "RFR=15%, ERP=8%, Beta unchanged, Growth -5%",
     0.15, 0.08, 1.0, -0.05);

    (* 2020 COVID Crash: Low rates, high ERP, elevated beta, severe growth shock *)
    ("2020 COVID Crash",
     "RFR=0.5%, ERP=8%, Beta×1.2, Growth -15%",
     0.005, 0.08, 1.2, -0.15);

    (* Tech Bubble Burst (2000): Moderate rates, moderate ERP, beta increase, growth decline *)
    ("Tech Bubble Burst (2000)",
     "RFR=6%, ERP=7%, Beta×1.3, Growth -8%",
     0.06, 0.07, 1.3, -0.08);
  ] in

  List.map (fun (name, description, rfr_stress, erp_stress, beta_mult, growth_shock) ->
    (* Calculate stressed discount rates *)
    let beta_stress = cost_of_capital.leveraged_beta *. beta_mult in
    let ce_stress = rfr_stress +. (beta_stress *. erp_stress) in

    (* Calculate stressed WACC *)
    let total_value = market_data.mve +. market_data.mvb in
    let wacc_stress = if total_value = 0.0 then ce_stress
      else
        let equity_weight = market_data.mve /. total_value in
        let debt_weight = market_data.mvb /. total_value in
        (equity_weight *. ce_stress) +. (debt_weight *. cost_of_capital.cb *. (1.0 -. tax_rate))
    in

    (* Run stress valuations *)
    let ivps_fcfe = calculate_fcfe_stress
      ~market_data ~time_series ~ce_stress ~roe_prior ~retention_prior
      ~terminal_growth ~projection_years ~growth_shock
    in

    let ivps_fcff = calculate_fcff_stress
      ~market_data ~time_series ~wacc_stress ~roic_prior ~tax_rate
      ~terminal_growth ~projection_years ~growth_shock
    in

    {
      name;
      description;
      ivps_fcfe;
      ivps_fcff;
      discount_rate_ce = ce_stress;
      discount_rate_wacc = wacc_stress;
    }
  ) scenarios

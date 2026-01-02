(** Growth rate estimation and clamping *)

let clamp_growth_rate ~rate ~lower_bound ~upper_bound =
  if rate < lower_bound then
    (lower_bound, true)
  else if rate > upper_bound then
    (upper_bound, true)
  else
    (rate, false)

let calculate_roe ~net_income ~book_value_equity =
  if book_value_equity = 0.0 then
    0.0
  else
    net_income /. book_value_equity

let calculate_roic ~nopat ~invested_capital =
  if invested_capital = 0.0 then
    0.0
  else
    nopat /. invested_capital

let calculate_fcfe_growth_rate ~financial_data ~fcfe ~params =
  let open Types in

  (* Calculate ROE *)
  let roe = calculate_roe
    ~net_income:financial_data.net_income
    ~book_value_equity:financial_data.book_value_equity
  in

  (* Calculate retention ratio = 1 - payout ratio
     Payout ratio = FCFE / NI (if NI > 0) *)
  let retention_ratio =
    if financial_data.net_income <= 0.0 then
      0.0  (* Negative earnings, no retention *)
    else
      1.0 -. (fcfe /. financial_data.net_income)
  in

  (* Ensure retention ratio is in [0, 1] *)
  let retention_ratio = max 0.0 (min 1.0 retention_ratio) in

  (* Growth rate = ROE × Retention Ratio *)
  let growth_rate = roe *. retention_ratio in

  (* Clamp to configured bounds *)
  clamp_growth_rate
    ~rate:growth_rate
    ~lower_bound:params.growth_clamp_lower
    ~upper_bound:params.growth_clamp_upper

let calculate_fcff_growth_rate ~financial_data ~tax_rate ~params =
  let open Types in

  (* Calculate NOPAT *)
  let nopat = Cash_flow.calculate_nopat
    ~ebit:financial_data.ebit
    ~tax_rate
  in

  (* Calculate ROIC *)
  let roic = calculate_roic
    ~nopat
    ~invested_capital:financial_data.invested_capital
  in

  (* Calculate reinvestment = CapEx + ΔWC - Depreciation *)
  let reinvestment =
    financial_data.capex +. financial_data.delta_wc -. financial_data.depreciation
  in

  (* Calculate reinvestment rate = Reinvestment / NOPAT *)
  let reinvestment_rate =
    if nopat = 0.0 then
      0.0
    else
      reinvestment /. nopat
  in

  (* Ensure reinvestment rate is non-negative *)
  let reinvestment_rate = max 0.0 reinvestment_rate in

  (* Growth rate = ROIC × Reinvestment Rate *)
  let growth_rate = roic *. reinvestment_rate in

  (* Clamp to configured bounds *)
  clamp_growth_rate
    ~rate:growth_rate
    ~lower_bound:params.growth_clamp_lower
    ~upper_bound:params.growth_clamp_upper

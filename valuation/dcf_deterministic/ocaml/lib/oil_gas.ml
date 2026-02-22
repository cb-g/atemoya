(** Oil & Gas E&P Valuation using NAV Model

    O&G E&P companies are valued based on:
    1. Proven reserves (1P) - highest certainty
    2. Probable reserves (2P) - includes probable
    3. Possible reserves (3P) - includes possible

    The NAV (Net Asset Value) Model values E&P companies as:
    Fair Value = PV of Reserves + Cash - Debt

    where PV of Reserves is calculated by projecting:
    - Production over reserve life
    - Revenue at assumed commodity prices
    - Operating costs (lifting costs)
    - Taxes

    The PV-10 is the SEC standard using 10% discount rate.

    Key metrics:
    - EV/EBITDAX - Enterprise Value / (EBITDA + Exploration)
    - EV/BOE - Enterprise Value / Proven Reserves
    - Reserve Life - Proven Reserves / Annual Production
    - Recycle Ratio - Netback / Finding Cost
*)

open Types

(** Current oil and gas prices (WTI and Henry Hub)
    These should ideally be fetched live *)
let _default_oil_price = 75.0   (* USD per barrel - WTI *)
let _default_gas_price = 3.0    (* USD per MMBtu - Henry Hub *)

(** Standard BOE conversion: 6 MCF = 1 BOE *)
let mcf_per_boe = 6.0

(** Calculate O&G specific metrics from financial data *)
let calculate_oil_gas_metrics ~(financial : financial_data)
    ~(market : market_data) ~oil_price ~gas_price : oil_gas_metrics =

  (* Annual production in BOE *)
  let annual_production = financial.production_boe_day *. 365.0 in

  (* Reserve life = Proven Reserves / Annual Production *)
  let reserve_life =
    if annual_production > 0.0 then
      (financial.proven_reserves *. 1_000_000.0) /. annual_production
    else 0.0
  in

  (* EBITDAX = EBITDA + Exploration Expense *)
  let ebitdax =
    if financial.ebitdax > 0.0 then financial.ebitdax
    else financial.ebit +. financial.depreciation +. financial.exploration_expense
  in

  (* EBITDAX margin *)
  let revenue =
    if annual_production > 0.0 then
      (* Estimate revenue from production and prices *)
      let oil_rev = annual_production *. financial.oil_pct *. oil_price in
      let gas_rev = annual_production *. (1.0 -. financial.oil_pct) *. gas_price *. mcf_per_boe in
      oil_rev +. gas_rev
    else 0.0
  in
  let ebitdax_margin = if revenue > 0.0 then ebitdax /. revenue else 0.0 in

  (* EBITDAX per BOE *)
  let ebitdax_per_boe =
    if annual_production > 0.0 then ebitdax /. annual_production
    else 0.0
  in

  (* Enterprise Value *)
  let ev = market.mve +. market.mvb in

  (* EV per BOE (reserves) *)
  let ev_per_boe =
    if financial.proven_reserves > 0.0 then
      ev /. (financial.proven_reserves *. 1_000_000.0)
    else 0.0
  in

  (* EV/EBITDAX multiple *)
  let ev_to_ebitdax = if ebitdax > 0.0 then ev /. ebitdax else 0.0 in

  (* Netback = Revenue per BOE - Lifting Cost *)
  let revenue_per_boe =
    financial.oil_pct *. oil_price +.
    (1.0 -. financial.oil_pct) *. gas_price *. mcf_per_boe
  in
  let netback = revenue_per_boe -. financial.lifting_cost in

  (* Recycle ratio = Netback / Finding Cost *)
  let recycle_ratio =
    if financial.finding_cost > 0.0 then netback /. financial.finding_cost
    else 0.0
  in

  (* Debt/EBITDAX *)
  let debt_to_ebitdax = if ebitdax > 0.0 then market.mvb /. ebitdax else 0.0 in

  (* ROE *)
  let roe =
    if financial.book_value_equity > 0.0 then
      financial.net_income /. financial.book_value_equity
    else 0.0
  in

  {
    reserve_life;
    production_growth = 0.0;  (* Would need historical data *)
    ebitdax_margin;
    ebitdax_per_boe;
    ev_per_boe;
    ev_to_ebitdax;
    netback;
    recycle_ratio;
    debt_to_ebitdax;
    roe;
  }

(** Calculate cost of capital for O&G E&P using CAPM with commodity beta adjustment *)
let calculate_oil_gas_cost_of_capital ~risk_free_rate ~equity_risk_premium
    ~(market : market_data) ~oil_price : float =
  (* O&G betas vary by company type:
     - Integrated majors: ~0.9-1.1
     - Large E&P: ~1.1-1.3
     - Small E&P: ~1.3-1.6
     - High leverage increases beta *)
  let base_beta =
    if market.mve > 100_000_000_000.0 then 1.0    (* Majors *)
    else if market.mve > 10_000_000_000.0 then 1.2 (* Large cap *)
    else 1.4  (* Mid/Small cap *)
  in

  (* Adjust beta for oil price environment
     Higher prices = lower beta (more stable cash flows)
     Lower prices = higher beta (more risk) *)
  let price_adj =
    if oil_price > 80.0 then 0.95
    else if oil_price < 50.0 then 1.10
    else 1.0
  in
  let adjusted_beta = base_beta *. price_adj in

  risk_free_rate +. (adjusted_beta *. equity_risk_premium)

(** Calculate PV of proven reserves using decline curve

    Projects production over reserve life with exponential decline,
    calculates after-tax cash flows and discounts them.
*)
let calculate_reserve_value ~proven_reserves ~production_boe_day ~oil_pct
    ~lifting_cost ~oil_price ~gas_price ~discount_rate ~tax_rate : float =

  if proven_reserves <= 0.0 || production_boe_day <= 0.0 then 0.0
  else if discount_rate <= 0.0 then 0.0
  else
    let reserves_boe = proven_reserves *. 1_000_000.0 in
    let initial_annual_production = production_boe_day *. 365.0 in

    (* Estimate reserve life *)
    let reserve_life = reserves_boe /. initial_annual_production in
    let projection_years = int_of_float (min reserve_life 30.0) in

    (* Decline rate (typical: 5-15% for conventional, 30-50% for shale) *)
    let decline_rate = 0.08 in  (* 8% annual decline - moderate *)

    (* Revenue per BOE *)
    let revenue_per_boe =
      oil_pct *. oil_price +. (1.0 -. oil_pct) *. gas_price *. mcf_per_boe
    in

    (* Project cash flows with decline *)
    let rec project_pv acc year remaining_reserves production =
      if year > projection_years || remaining_reserves <= 0.0 then acc
      else
        let actual_production = min production remaining_reserves in
        let revenue = actual_production *. revenue_per_boe in
        let operating_cost = actual_production *. lifting_cost in
        let operating_profit = revenue -. operating_cost in
        let after_tax_cf = operating_profit *. (1.0 -. tax_rate) in

        let discount_factor = (1.0 +. discount_rate) ** float_of_int year in
        let pv = after_tax_cf /. discount_factor in

        (* Next year: production declines, reserves depleted *)
        let next_production = production *. (1.0 -. decline_rate) in
        let next_reserves = remaining_reserves -. actual_production in

        project_pv (acc +. pv) (year + 1) next_reserves next_production
    in

    project_pv 0.0 1 reserves_boe initial_annual_production

(** Calculate PV-10 (SEC standard valuation)
    Uses 10% discount rate and trailing 12-month average prices *)
let calculate_pv10 ~proven_reserves ~production_boe_day ~oil_pct
    ~lifting_cost ~oil_price ~gas_price ~tax_rate : float =
  calculate_reserve_value
    ~proven_reserves ~production_boe_day ~oil_pct
    ~lifting_cost ~oil_price ~gas_price
    ~discount_rate:0.10 ~tax_rate

(** Solve for implied oil price given market price *)
let solve_implied_oil_price ~market_price ~shares_outstanding ~debt
    ~proven_reserves ~production_boe_day ~oil_pct ~lifting_cost
    ~gas_price ~discount_rate ~tax_rate : float option =

  let target_equity_value = market_price *. shares_outstanding in

  (* Binary search for implied oil price *)
  let rec search low high iterations =
    if iterations > 50 then None
    else
      let mid = (low +. high) /. 2.0 in

      let reserve_value = calculate_reserve_value
        ~proven_reserves ~production_boe_day ~oil_pct
        ~lifting_cost ~oil_price:mid ~gas_price
        ~discount_rate ~tax_rate
      in

      let nav = reserve_value -. debt in
      let diff = nav -. target_equity_value in

      if abs_float diff < target_equity_value *. 0.01 then Some mid
      else if diff > 0.0 then search low mid (iterations + 1)
      else search mid high (iterations + 1)
  in

  (* Oil price typically ranges from $30 to $150 *)
  search 30.0 150.0 0

(** Generate investment signal for O&G E&P *)
let classify_oil_gas_signal ~nav_per_share ~market_price
    ~(metrics : oil_gas_metrics) ~debt_to_ebitdax : investment_signal =
  let margin = (nav_per_share -. market_price) /. market_price in

  (* Strong Buy: >40% undervalued + healthy metrics *)
  if margin > 0.40 && debt_to_ebitdax < 2.0 && metrics.recycle_ratio > 2.0 then
    StrongBuy
  (* Buy: 20-40% undervalued with acceptable leverage *)
  else if margin > 0.20 && debt_to_ebitdax < 3.0 then
    Buy
  (* Hold: Near fair value *)
  else if margin > -0.15 && margin < 0.15 then
    Hold
  (* Caution: High leverage *)
  else if debt_to_ebitdax > 4.0 then
    CautionLeverage
  (* Speculative: High leverage but potential upside *)
  else if debt_to_ebitdax > 3.0 && margin > 0.20 then
    SpeculativeHighLeverage
  (* Avoid: Significantly overvalued *)
  else if margin < -0.25 then
    Avoid
  else
    Hold

(** Full O&G E&P valuation using NAV model *)
let value_oil_gas ~(financial : financial_data) ~(market : market_data)
    ~risk_free_rate ~equity_risk_premium ~tax_rate
    ~oil_price ~gas_price : oil_gas_valuation_result =

  let shares = market.shares_outstanding in

  (* Calculate O&G metrics *)
  let metrics = calculate_oil_gas_metrics ~financial ~market ~oil_price ~gas_price in

  (* Calculate cost of capital *)
  let cost_of_capital = calculate_oil_gas_cost_of_capital
    ~risk_free_rate ~equity_risk_premium ~market ~oil_price
  in

  (* Calculate reserve value *)
  let reserve_value_total = calculate_reserve_value
    ~proven_reserves:financial.proven_reserves
    ~production_boe_day:financial.production_boe_day
    ~oil_pct:financial.oil_pct
    ~lifting_cost:financial.lifting_cost
    ~oil_price ~gas_price
    ~discount_rate:cost_of_capital
    ~tax_rate
  in

  (* Calculate PV-10 *)
  let pv10_total = calculate_pv10
    ~proven_reserves:financial.proven_reserves
    ~production_boe_day:financial.production_boe_day
    ~oil_pct:financial.oil_pct
    ~lifting_cost:financial.lifting_cost
    ~oil_price ~gas_price
    ~tax_rate
  in

  (* NAV = Reserve Value - Debt *)
  let nav = reserve_value_total -. market.mvb in
  let nav_per_share = if shares > 0.0 then nav /. shares else 0.0 in

  let reserve_value_per_share =
    if shares > 0.0 then reserve_value_total /. shares else 0.0
  in

  let pv10_per_share = if shares > 0.0 then (pv10_total -. market.mvb) /. shares else 0.0 in

  (* Blend NAV and PV-10 for fair value estimate *)
  let fair_value_per_share = (nav_per_share +. pv10_per_share) /. 2.0 in

  let margin_of_safety =
    if market.price > 0.0 then
      (fair_value_per_share -. market.price) /. market.price
    else 0.0
  in

  (* Solve for implied oil price *)
  let implied_oil_price = solve_implied_oil_price
    ~market_price:market.price
    ~shares_outstanding:shares
    ~debt:market.mvb
    ~proven_reserves:financial.proven_reserves
    ~production_boe_day:financial.production_boe_day
    ~oil_pct:financial.oil_pct
    ~lifting_cost:financial.lifting_cost
    ~gas_price
    ~discount_rate:cost_of_capital
    ~tax_rate
  in

  let signal = classify_oil_gas_signal
    ~nav_per_share:fair_value_per_share
    ~market_price:market.price
    ~metrics
    ~debt_to_ebitdax:metrics.debt_to_ebitdax
  in

  {
    ticker = market.ticker;
    price = market.price;
    nav_per_share;
    reserve_value = reserve_value_per_share;
    pv10_value = pv10_per_share;
    fair_value_per_share;
    margin_of_safety;
    implied_oil_price;
    signal;
    cost_of_capital;
    oil_gas_metrics = metrics;
  }

(** Insurance valuation using Float-Based Model

    Insurance companies are special because:
    1. They collect premiums upfront and pay claims later (float)
    2. Float is essentially free leverage if underwriting is profitable
    3. Combined ratio (loss + expense) determines underwriting profitability
    4. Investment income on float is a major earnings source

    The Float-Based Model values insurers as:
    Fair Value = Book Value + PV of Underwriting Profits + Value of Float

    where:
    - Underwriting Profit = Premiums × (1 - Combined Ratio)
    - Float Value = Float × (Investment Yield - Cost of Float)
    - Cost of Float ≈ 0 if combined ratio < 100%, otherwise = (CR - 100%) × Premiums / Float

    This captures the economic value of:
    1. Sustainable underwriting profits (if combined ratio < 100%)
    2. The ability to invest policyholder funds at no cost
*)

open Types

(** Calculate insurance-specific metrics from financial data *)
let calculate_insurance_metrics ~(financial : financial_data)
    ~(market : market_data) : insurance_metrics =

  (* ROE = Net Income / Book Value of Equity *)
  let roe =
    if financial.book_value_equity > 0.0 then
      financial.net_income /. financial.book_value_equity
    else 0.0
  in

  (* Use provided ratios or calculate from data *)
  let loss_ratio =
    if financial.loss_ratio > 0.0 then financial.loss_ratio
    else if financial.premiums_earned > 0.0 then
      financial.losses_incurred /. financial.premiums_earned
    else 0.0
  in

  let expense_ratio =
    if financial.expense_ratio > 0.0 then financial.expense_ratio
    else if financial.premiums_earned > 0.0 then
      financial.underwriting_expenses /. financial.premiums_earned
    else 0.0
  in

  let combined_ratio =
    if financial.combined_ratio > 0.0 then financial.combined_ratio
    else loss_ratio +. expense_ratio
  in

  (* Underwriting margin = 1 - Combined Ratio
     Positive means underwriting profit *)
  let underwriting_margin = 1.0 -. combined_ratio in

  (* Investment yield = Investment Income / Float *)
  let investment_yield =
    if financial.float_amount > 0.0 then
      financial.investment_income /. financial.float_amount
    else 0.0
  in

  (* Float to Equity ratio - leverage measure *)
  let float_to_equity =
    if financial.book_value_equity > 0.0 then
      financial.float_amount /. financial.book_value_equity
    else 0.0
  in

  (* Price to Book *)
  let price_to_book =
    if financial.book_value_equity > 0.0 then
      market.mve /. financial.book_value_equity
    else 0.0
  in

  (* Premium to Equity - underwriting capacity measure *)
  let premium_to_equity =
    if financial.book_value_equity > 0.0 then
      financial.premiums_earned /. financial.book_value_equity
    else 0.0
  in

  {
    roe;
    combined_ratio;
    loss_ratio;
    expense_ratio;
    underwriting_margin;
    investment_yield;
    float_to_equity;
    price_to_book;
    premium_to_equity;
  }

(** Calculate cost of equity for an insurer using CAPM *)
let calculate_insurance_cost_of_equity ~risk_free_rate ~equity_risk_premium
    ~(market : market_data) : float =
  (* Insurance betas vary by type:
     - P&C: ~0.8-1.0 (cyclical, catastrophe exposure)
     - Life: ~1.0-1.2 (interest rate sensitive)
     - Reinsurance: ~0.9-1.1 *)
  let insurance_beta =
    if market.mve > 50_000_000_000.0 then 0.85   (* Large diversified *)
    else if market.mve > 10_000_000_000.0 then 0.95  (* Mid-size *)
    else 1.05  (* Smaller, less diversified *)
  in
  risk_free_rate +. (insurance_beta *. equity_risk_premium)

(** Calculate present value of underwriting profits

    If combined ratio < 100%, insurer makes underwriting profit.
    We project this profit stream with gradual mean reversion toward 100%.
*)
let calculate_underwriting_value ~premiums ~combined_ratio ~cost_of_equity
    ~growth_rate ~projection_years ~terminal_growth : float =

  if cost_of_equity <= terminal_growth then 0.0
  else if combined_ratio >= 1.0 then
    (* No underwriting profit - this component is zero or negative *)
    0.0
  else
    (* Mean reversion: combined ratio gradually moves toward industry average (~98%) *)
    let target_cr = 0.98 in
    let lambda = 0.10 in  (* Slow reversion - good underwriters maintain edge *)

    let rec project_value acc year prem current_cr =
      if year > projection_years then acc
      else
        let underwriting_profit = prem *. (1.0 -. current_cr) in
        let discount_factor = (1.0 +. cost_of_equity) ** float_of_int year in
        let pv = underwriting_profit /. discount_factor in

        (* Grow premiums *)
        let next_prem = prem *. (1.0 +. growth_rate) in
        (* CR mean reverts toward target *)
        let next_cr = current_cr +. lambda *. (target_cr -. current_cr) in

        project_value (acc +. pv) (year + 1) next_prem next_cr
    in

    let explicit_pv = project_value 0.0 1 premiums combined_ratio in

    (* Terminal value: assume sustainable CR advantage *)
    let terminal_cr = min combined_ratio target_cr in
    let terminal_premium =
      premiums *. ((1.0 +. growth_rate) ** float_of_int projection_years)
    in
    let terminal_profit = terminal_premium *. (1.0 -. terminal_cr) in
    let terminal_value = terminal_profit /. (cost_of_equity -. terminal_growth) in
    let terminal_pv =
      terminal_value /. ((1.0 +. cost_of_equity) ** float_of_int projection_years)
    in

    explicit_pv +. terminal_pv

(** Calculate value of float

    Float is the money held between premium collection and claims payment.
    It's like an interest-free loan from policyholders.

    Float Value = Float × Investment Yield × Present Value Factor

    If underwriting is profitable (CR < 100%), cost of float is negative
    (i.e., policyholders are paying the insurer to hold their money).
*)
let calculate_float_value ~float_amount ~investment_yield ~combined_ratio
    ~cost_of_equity ~projection_years:_ ~terminal_growth : float =

  if cost_of_equity <= terminal_growth || float_amount <= 0.0 then 0.0
  else
    (* Cost of float: if CR > 100%, the underwriting loss is the "cost" *)
    let cost_of_float =
      if combined_ratio > 1.0 then combined_ratio -. 1.0
      else 0.0  (* Free float if underwriting profitable *)
    in

    (* Net benefit from float = investment yield - cost of float *)
    let float_benefit_rate = investment_yield -. cost_of_float in

    if float_benefit_rate <= 0.0 then 0.0
    else
      (* Value as perpetuity of float benefits *)
      let annual_float_benefit = float_amount *. float_benefit_rate in
      annual_float_benefit /. (cost_of_equity -. terminal_growth)

(** Solve for implied combined ratio given market price *)
let solve_implied_combined_ratio ~market_price ~book_value ~float_amount
    ~premiums ~investment_yield ~cost_of_equity ~shares_outstanding
    ~growth_rate ~projection_years ~terminal_growth : float option =

  let target_fv = market_price *. shares_outstanding in

  (* Binary search for implied combined ratio *)
  let rec search low high iterations =
    if iterations > 50 then None
    else
      let mid = (low +. high) /. 2.0 in

      let uw_value = calculate_underwriting_value
        ~premiums ~combined_ratio:mid ~cost_of_equity
        ~growth_rate ~projection_years ~terminal_growth
      in
      let float_val = calculate_float_value
        ~float_amount ~investment_yield ~combined_ratio:mid
        ~cost_of_equity ~projection_years ~terminal_growth
      in

      let fv = book_value +. uw_value +. float_val in
      let diff = fv -. target_fv in

      if abs_float diff < target_fv *. 0.001 then Some mid
      else if diff > 0.0 then search mid high (iterations + 1)
      else search low mid (iterations + 1)
  in

  (* Combined ratio typically ranges from 70% to 120% *)
  search 0.70 1.20 0

(** Generate investment signal for insurer *)
let classify_insurance_signal ~ivps ~market_price ~(metrics : insurance_metrics)
    ~cost_of_equity : investment_signal =
  let margin = (ivps -. market_price) /. market_price in

  (* Strong Buy: >30% undervalued + profitable underwriting + good ROE *)
  if margin > 0.30 && metrics.combined_ratio < 0.95 && metrics.roe > cost_of_equity then
    StrongBuy
  (* Buy: 15-30% undervalued with reasonable underwriting *)
  else if margin > 0.15 && metrics.combined_ratio < 1.0 then
    Buy
  (* Hold: Near fair value *)
  else if margin > -0.10 && margin < 0.10 then
    Hold
  (* Caution: Poor underwriting (combined ratio > 100%) *)
  else if metrics.combined_ratio > 1.05 then
    CautionLeverage
  (* Avoid: Significantly overvalued *)
  else if margin < -0.20 then
    Avoid
  else
    Hold

(** Full insurance valuation *)
let value_insurance ~(financial : financial_data) ~(market : market_data)
    ~risk_free_rate ~equity_risk_premium ~terminal_growth_rate
    ~projection_years : insurance_valuation_result =

  let shares = market.shares_outstanding in

  (* Calculate insurance metrics *)
  let metrics = calculate_insurance_metrics ~financial ~market in

  (* Calculate cost of equity *)
  let cost_of_equity = calculate_insurance_cost_of_equity
    ~risk_free_rate
    ~equity_risk_premium
    ~market
  in

  (* Calculate underwriting value *)
  let underwriting_value = calculate_underwriting_value
    ~premiums:financial.premiums_earned
    ~combined_ratio:metrics.combined_ratio
    ~cost_of_equity
    ~growth_rate:0.03  (* Assume 3% premium growth *)
    ~projection_years
    ~terminal_growth:terminal_growth_rate
  in

  (* Calculate float value *)
  let float_value = calculate_float_value
    ~float_amount:financial.float_amount
    ~investment_yield:metrics.investment_yield
    ~combined_ratio:metrics.combined_ratio
    ~cost_of_equity
    ~projection_years
    ~terminal_growth:terminal_growth_rate
  in

  (* Fair value = Book Value + Underwriting Value + Float Value *)
  let fair_value = financial.book_value_equity +. underwriting_value +. float_value in
  let fair_value_per_share =
    if shares > 0.0 then fair_value /. shares else 0.0
  in

  let book_value_per_share =
    if shares > 0.0 then financial.book_value_equity /. shares else 0.0
  in

  let margin_of_safety =
    if market.price > 0.0 then
      (fair_value_per_share -. market.price) /. market.price
    else 0.0
  in

  (* Solve for implied combined ratio *)
  let implied_combined_ratio = solve_implied_combined_ratio
    ~market_price:market.price
    ~book_value:financial.book_value_equity
    ~float_amount:financial.float_amount
    ~premiums:financial.premiums_earned
    ~investment_yield:metrics.investment_yield
    ~cost_of_equity
    ~shares_outstanding:shares
    ~growth_rate:0.03
    ~projection_years
    ~terminal_growth:terminal_growth_rate
  in

  let signal = classify_insurance_signal
    ~ivps:fair_value_per_share
    ~market_price:market.price
    ~metrics
    ~cost_of_equity
  in

  {
    ticker = market.ticker;
    price = market.price;
    book_value_per_share;
    underwriting_value = underwriting_value /. shares;
    float_value = float_value /. shares;
    fair_value_per_share;
    margin_of_safety;
    implied_combined_ratio;
    signal;
    cost_of_equity;
    insurance_metrics = metrics;
  }

(** Insurance valuation using Float-Based Model

    Insurers are valued as:
    Fair Value = Book Value + PV of Underwriting Profits + Value of Float

    This model captures the economic value of:
    - Sustainable underwriting profits (if combined ratio < 100%)
    - The ability to invest policyholder funds at low/no cost (float)
*)

(** Calculate insurance-specific metrics from financial data *)
val calculate_insurance_metrics :
  financial:Types.financial_data ->
  market:Types.market_data ->
  Types.insurance_metrics

(** Calculate cost of equity for an insurer using CAPM *)
val calculate_insurance_cost_of_equity :
  risk_free_rate:float ->
  equity_risk_premium:float ->
  market:Types.market_data ->
  float

(** Calculate present value of underwriting profits *)
val calculate_underwriting_value :
  premiums:float ->
  combined_ratio:float ->
  cost_of_equity:float ->
  growth_rate:float ->
  projection_years:int ->
  terminal_growth:float ->
  float

(** Calculate value of investable float *)
val calculate_float_value :
  float_amount:float ->
  investment_yield:float ->
  combined_ratio:float ->
  cost_of_equity:float ->
  projection_years:int ->
  terminal_growth:float ->
  float

(** Solve for implied combined ratio given market price *)
val solve_implied_combined_ratio :
  market_price:float ->
  book_value:float ->
  float_amount:float ->
  premiums:float ->
  investment_yield:float ->
  cost_of_equity:float ->
  shares_outstanding:float ->
  growth_rate:float ->
  projection_years:int ->
  terminal_growth:float ->
  float option

(** Generate investment signal for insurer *)
val classify_insurance_signal :
  ivps:float ->
  market_price:float ->
  metrics:Types.insurance_metrics ->
  cost_of_equity:float ->
  Types.investment_signal

(** Full insurance valuation using float-based model *)
val value_insurance :
  financial:Types.financial_data ->
  market:Types.market_data ->
  risk_free_rate:float ->
  equity_risk_premium:float ->
  terminal_growth_rate:float ->
  projection_years:int ->
  Types.insurance_valuation_result

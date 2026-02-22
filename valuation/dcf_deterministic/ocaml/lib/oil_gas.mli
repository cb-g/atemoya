(** Oil & Gas E&P Valuation using NAV Model

    E&P companies are valued as:
    Fair Value = PV of Reserves - Debt

    This model captures the economic value of:
    - Proven reserves at current commodity prices
    - Production capability and decline rates
    - Operating costs (lifting costs)
*)

(** Calculate O&G specific metrics from financial data *)
val calculate_oil_gas_metrics :
  financial:Types.financial_data ->
  market:Types.market_data ->
  oil_price:float ->
  gas_price:float ->
  Types.oil_gas_metrics

(** Calculate cost of capital for O&G E&P using CAPM *)
val calculate_oil_gas_cost_of_capital :
  risk_free_rate:float ->
  equity_risk_premium:float ->
  market:Types.market_data ->
  oil_price:float ->
  float

(** Calculate PV of proven reserves using decline curve *)
val calculate_reserve_value :
  proven_reserves:float ->
  production_boe_day:float ->
  oil_pct:float ->
  lifting_cost:float ->
  oil_price:float ->
  gas_price:float ->
  discount_rate:float ->
  tax_rate:float ->
  float

(** Calculate PV-10 (SEC standard valuation at 10% discount) *)
val calculate_pv10 :
  proven_reserves:float ->
  production_boe_day:float ->
  oil_pct:float ->
  lifting_cost:float ->
  oil_price:float ->
  gas_price:float ->
  tax_rate:float ->
  float

(** Solve for implied oil price given market price *)
val solve_implied_oil_price :
  market_price:float ->
  shares_outstanding:float ->
  debt:float ->
  proven_reserves:float ->
  production_boe_day:float ->
  oil_pct:float ->
  lifting_cost:float ->
  gas_price:float ->
  discount_rate:float ->
  tax_rate:float ->
  float option

(** Generate investment signal for O&G E&P *)
val classify_oil_gas_signal :
  nav_per_share:float ->
  market_price:float ->
  metrics:Types.oil_gas_metrics ->
  debt_to_ebitdax:float ->
  Types.investment_signal

(** Full O&G E&P valuation using NAV model *)
val value_oil_gas :
  financial:Types.financial_data ->
  market:Types.market_data ->
  risk_free_rate:float ->
  equity_risk_premium:float ->
  tax_rate:float ->
  oil_price:float ->
  gas_price:float ->
  Types.oil_gas_valuation_result

(** Capital structure and cost of capital calculations *)

(** Calculate leveraged beta using Hamada formula:
    β_L = β_U × [1 + (1 - tax_rate) × (debt / equity)] *)
val calculate_leveraged_beta :
  unlevered_beta:float ->
  tax_rate:float ->
  debt:float ->
  equity:float ->
  float

(** Calculate cost of equity using CAPM:
    CE = RFR + β_L × ERP *)
val calculate_cost_of_equity :
  risk_free_rate:float ->
  leveraged_beta:float ->
  equity_risk_premium:float ->
  float

(** Calculate cost of borrowing:
    CB = interest_expense / total_debt *)
val calculate_cost_of_borrowing :
  interest_expense:float ->
  total_debt:float ->
  float

(** Calculate WACC:
    WACC = (E/(E+D)) × CE + (D/(E+D)) × CB × (1 - tax_rate) *)
val calculate_wacc :
  equity:float ->
  debt:float ->
  cost_of_equity:float ->
  cost_of_borrowing:float ->
  tax_rate:float ->
  float

(** Calculate all cost of capital components *)
val calculate_cost_of_capital :
  market_data:Types.market_data ->
  financial_data:Types.financial_data ->
  unlevered_beta:float ->
  risk_free_rate:float ->
  equity_risk_premium:float ->
  tax_rate:float ->
  Types.cost_of_capital

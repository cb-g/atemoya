(** Growth rate estimation and clamping *)

(** Clamp a growth rate to specified bounds *)
val clamp_growth_rate :
  rate:float ->
  lower_bound:float ->
  upper_bound:float ->
  float * bool  (** Returns (clamped_rate, was_clamped) *)

(** Calculate ROE (Return on Equity):
    ROE = Net_Income / Book_Value_Equity *)
val calculate_roe :
  net_income:float ->
  book_value_equity:float ->
  float

(** Calculate ROIC (Return on Invested Capital):
    ROIC = NOPAT / Invested_Capital *)
val calculate_roic :
  nopat:float ->
  invested_capital:float ->
  float

(** Calculate FCFE growth rate using ROE-based formula:
    g_FCFE = ROE × Retention_Ratio
    where Retention_Ratio = 1 - (FCFE / NI) *)
val calculate_fcfe_growth_rate :
  financial_data:Types.financial_data ->
  fcfe:float ->
  params:Types.valuation_params ->
  float * bool  (** Returns (growth_rate, was_clamped) *)

(** Calculate FCFF growth rate using ROIC-based formula:
    g_FCFF = ROIC × Reinvestment_Rate
    where Reinvestment_Rate = (CapEx + ΔWC - D) / NOPAT *)
val calculate_fcff_growth_rate :
  financial_data:Types.financial_data ->
  tax_rate:float ->
  params:Types.valuation_params ->
  float * bool  (** Returns (growth_rate, was_clamped) *)

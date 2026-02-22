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

(** Fama-French size factor loading *)
val calculate_smb_loading :
  market_cap:float ->
  small_cap_threshold:float ->
  float

(** Fama-French value factor loading *)
val calculate_hml_loading :
  book_to_market:float ->
  value_btm_threshold:float ->
  float

(** Cost of equity with Fama-French 3-factor model *)
val calculate_cost_of_equity_fama_french :
  risk_free_rate:float ->
  leveraged_beta:float ->
  equity_risk_premium:float ->
  smb_loading:float ->
  hml_loading:float ->
  smb_premium:float ->
  hml_premium:float ->
  float

(** Default Fama-French configuration (disabled) *)
val default_fama_french_config : unit -> Types.fama_french_config

(** Default ERP configuration (static Damodaran mode) *)
val default_erp_config : base_erp:float -> Types.erp_config

(** Calculate all cost of capital components with optional configurations

    Args:
      erp_config: Optional ERP configuration for dynamic VIX adjustment
      fama_french_config: Optional Fama-French 3-factor configuration
      market_data: Company market data
      financial_data: Financial statement data
      unlevered_beta: Industry unlevered beta
      risk_free_rate: Risk-free rate
      equity_risk_premium: Base ERP (Damodaran)
      tax_rate: Corporate tax rate
*)
val calculate_cost_of_capital :
  ?erp_config:Types.erp_config ->
  ?fama_french_config:Types.fama_french_config ->
  market_data:Types.market_data ->
  financial_data:Types.financial_data ->
  unlevered_beta:float ->
  risk_free_rate:float ->
  equity_risk_premium:float ->
  tax_rate:float ->
  unit ->
  Types.cost_of_capital

(** Legacy wrapper using pure CAPM with static ERP *)
val calculate_cost_of_capital_capm :
  market_data:Types.market_data ->
  financial_data:Types.financial_data ->
  unlevered_beta:float ->
  risk_free_rate:float ->
  equity_risk_premium:float ->
  tax_rate:float ->
  Types.cost_of_capital

(** Calculate cost of capital with dynamic VIX-adjusted ERP

    Adjusts base ERP using current VIX relative to historical mean:
    ERP_dynamic = ERP_base × (VIX / VIX_mean)^sensitivity

    This captures time-varying risk aversion - when VIX spikes,
    investors demand higher compensation for equity risk.
*)
val calculate_cost_of_capital_dynamic :
  current_vix:float ->
  ?vix_mean:float ->
  ?vix_sensitivity:float ->
  ?fama_french_config:Types.fama_french_config ->
  market_data:Types.market_data ->
  financial_data:Types.financial_data ->
  unlevered_beta:float ->
  risk_free_rate:float ->
  base_equity_risk_premium:float ->
  tax_rate:float ->
  unit ->
  Types.cost_of_capital

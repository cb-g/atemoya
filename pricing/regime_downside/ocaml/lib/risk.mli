(** Risk measure calculations for downside optimization *)

open Types

(** Calculate Lower Partial Moment of order 1 *)
val lpm1 : threshold:float -> active_returns:active_returns -> float

(** Calculate Conditional Value at Risk at 95% *)
val cvar_95 : active_returns:active_returns -> float

(** Calculate portfolio beta from weights and asset betas *)
val portfolio_beta : weights:weights -> asset_betas:asset_betas -> float

(** Calculate all risk metrics *)
val calculate_risk_metrics :
  threshold:float ->
  active_returns:active_returns ->
  weights:weights ->
  asset_betas:asset_betas ->
  risk_metrics

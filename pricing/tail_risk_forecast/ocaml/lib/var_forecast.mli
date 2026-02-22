(** Value-at-Risk and Expected Shortfall forecasting

    Computes VaR and ES using the HAR-RV volatility forecast.
    Supports both normal and t-distribution assumptions.
*)

open Types

(** Distribution assumption for tail risk *)
type distribution =
  | Normal
  | StudentT of float  (** degrees of freedom *)

(** Compute VaR at given confidence level.
    VaR_α = z_α * σ (assuming zero mean daily return) *)
val compute_var : distribution -> float -> float -> float

(** Compute Expected Shortfall at given confidence level.
    ES_α = E[X | X < -VaR_α] *)
val compute_es : distribution -> float -> float -> float

(** Generate full tail risk forecast for next day *)
val forecast_tail_risk :
  ?distribution:distribution ->
  ?jump_premium:float ->
  har_coefficients ->
  daily_rv array ->
  jump_indicator array ->
  tail_risk_forecast

(** Standard normal quantiles *)
val z_95 : float
val z_99 : float

(** Student-t quantiles for common degrees of freedom *)
val t_quantile : float -> float -> float

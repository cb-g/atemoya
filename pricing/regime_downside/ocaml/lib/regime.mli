(** Regime detection based on rolling volatility *)

open Types

(** Calculate annualized realized volatility *)
val realized_volatility : returns:float array -> window_days:int -> float

(** Calculate percentile from historical values *)
val percentile : values:float array -> p:float -> float

(** Calculate stress regime weight [0,1] with smooth transition *)
val stress_weight : current_vol:float -> lower_pct:float -> upper_pct:float -> float

(** Detect current regime state from benchmark returns *)
val detect_regime :
  benchmark_returns:float array ->
  lookback_years:int ->
  vol_window_days:int ->
  lower_percentile:float ->
  upper_percentile:float ->
  regime

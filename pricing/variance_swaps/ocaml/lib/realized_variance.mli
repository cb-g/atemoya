(* Interface for realized variance calculations *)

(** Compute realized variance from log-returns

    RV = (252/N) Σ r²ᵢ
    where rᵢ = log(Sᵢ/Sᵢ₋₁)
*)
val compute_realized_variance :
  prices:float array ->
  annualization_factor:float ->
  float

(** Compute Parkinson high-low estimator

    RV_parkinson = (252/N) Σ [(ln(Hᵢ/Lᵢ))² / (4·ln(2))]
*)
val parkinson_estimator :
  highs:float array ->
  lows:float array ->
  annualization_factor:float ->
  float

(** Compute Garman-Klass OHLC estimator

    More efficient than close-to-close, uses high/low/open/close
*)
val garman_klass_estimator :
  opens:float array ->
  highs:float array ->
  lows:float array ->
  closes:float array ->
  annualization_factor:float ->
  float

(** Compute Rogers-Satchell estimator (drift-independent) *)
val rogers_satchell_estimator :
  opens:float array ->
  highs:float array ->
  lows:float array ->
  closes:float array ->
  annualization_factor:float ->
  float

(** Compute Yang-Zhang estimator (combines overnight and intraday) *)
val yang_zhang_estimator :
  opens:float array ->
  highs:float array ->
  lows:float array ->
  closes:float array ->
  annualization_factor:float ->
  float

(** Compute realized variance for rolling windows
    Returns array of (date, realized_var) pairs
*)
val rolling_realized_variance :
  prices:float array ->
  window_days:int ->
  annualization_factor:float ->
  float array

(** Forecast future realized variance using exponential weighted moving average

    EWMA: σ²ₜ = λ·σ²ₜ₋₁ + (1-λ)·r²ₜ
*)
val forecast_ewma :
  returns:float array ->
  lambda:float ->
  annualization_factor:float ->
  float

(** Forecast using GARCH(1,1) parameters

    σ²ₜ = ω + α·r²ₜ₋₁ + β·σ²ₜ₋₁
*)
val forecast_garch :
  returns:float array ->
  omega:float ->
  alpha:float ->
  beta:float ->
  annualization_factor:float ->
  float

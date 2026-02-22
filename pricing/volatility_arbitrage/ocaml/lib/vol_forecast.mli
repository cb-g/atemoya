(* Interface for volatility forecasting *)

open Types

(** GARCH(1,1) forecast using pre-estimated parameters
    Multi-step ahead forecast: σ²_{t+h} = ω·(1-β^h)/(1-β) + (α+β)^h·σ²_t *)
val garch_forecast :
  params:garch_params ->
  current_variance:float ->
  horizon_days:int ->
  vol_forecast

(** Estimate GARCH parameters from return series
    Uses method of moments for initial guess, then quasi-MLE *)
val estimate_garch_params :
  returns:float array ->
  garch_params

(** EWMA (Exponentially Weighted Moving Average) forecast
    σ²_t = λ·σ²_{t-1} + (1-λ)·r²_{t-1}
    Typically λ = 0.94 (RiskMetrics) *)
val ewma_forecast :
  returns:float array ->
  lambda:float ->
  horizon_days:int ->
  vol_forecast

(** Compute current EWMA variance from return series *)
val ewma_variance :
  returns:float array ->
  lambda:float ->
  float

(** HAR (Heterogeneous Autoregressive) forecast
    RV_t = β₀ + β_d·RV_{t-1,d} + β_w·RV_{t-1,w} + β_m·RV_{t-1,m} *)
val har_forecast :
  realized_vols:realized_vol array ->
  horizon_days:int ->
  vol_forecast

(** Estimate HAR parameters via OLS regression *)
val estimate_har_params :
  realized_vols:realized_vol array ->
  (float * float * float * float)  (* (β₀, β_d, β_w, β_m) *)

(** Historical average forecast *)
val historical_forecast :
  realized_vols:realized_vol array ->
  window_days:int ->
  vol_forecast

(** Ensemble forecast combining multiple methods *)
val ensemble_forecast :
  forecasts:vol_forecast array ->
  weights:float array ->
  vol_forecast

(** Compute forecast error (RMSE) *)
val forecast_rmse :
  forecasts:vol_forecast array ->
  realized:realized_vol array ->
  float

(** Compute 95% confidence interval for GARCH forecast *)
val garch_confidence_interval :
  params:garch_params ->
  current_variance:float ->
  horizon_days:int ->
  (float * float)

(** Helper: annualize variance *)
val annualize_variance : float -> float

(** Helper: variance to volatility *)
val variance_to_vol : float -> float

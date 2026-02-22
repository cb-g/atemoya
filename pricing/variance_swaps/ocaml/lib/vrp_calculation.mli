(* Interface for Variance Risk Premium (VRP) calculation and signal generation *)

open Types

(** Compute VRP observation from implied and forecast realized variance

    VRP = IV² - E[RV²]
    VRP% = (IV² - E[RV²]) / IV² × 100
*)
val compute_vrp :
  ticker:string ->
  horizon_days:int ->
  implied_var:float ->
  forecast_realized_var:float ->
  vrp_observation

(** Generate trading signal based on VRP observation and config *)
val generate_signal :
  vrp_observation ->
  variance_swap_config ->
  vrp_trading_signal

(** Compute time series of VRP observations

    For each date in historical data, compute implied and realized variance
*)
val compute_vrp_time_series :
  ticker:string ->
  vol_surface_data:(float * float array * float array) array ->  (* (date, strikes, IVs) *)
  price_data:(float * float) array ->  (* (date, price) *)
  horizon_days:int ->
  variance_swap_config ->
  vrp_observation array

(** Backtest VRP strategy on historical data

    Returns array of strategy P&L over time
*)
val backtest_vrp_strategy :
  vrp_observations:vrp_observation array ->
  realized_variances:float array ->
  config:variance_swap_config ->
  variance_strategy_pnl array

(** Compute VRP statistics (mean, std, Sharpe) from historical observations *)
val vrp_statistics :
  vrp_observation array ->
  (float * float * float)  (* (mean_vrp, std_vrp, sharpe_ratio) *)

(** Check if VRP is significant (t-test against zero) *)
val is_vrp_significant :
  vrp_observation array ->
  confidence_level:float ->
  bool

(** Non-parametric Wilcoxon signed-rank test for VRP significance.
    More robust than t-test for fat-tailed VRP distributions.
    Returns (is_significant, z_statistic, w_plus_rank_sum). *)
val wilcoxon_signed_rank_test :
  vrp_observation array ->
  confidence_level:float ->
  (bool * float * float)

(** Compute optimal position size based on Kelly criterion

    Kelly fraction: f = (μ/σ²) where μ = expected VRP, σ² = variance of VRP
*)
val kelly_position_size :
  vrp_observation array ->
  target_notional:float ->
  max_leverage:float ->
  float

(** Detect regime changes in VRP using rolling statistics *)
val detect_vrp_regime_change :
  vrp_observation array ->
  window_size:int ->
  threshold_zscore:float ->
  bool array  (* True at indices where regime change detected *)

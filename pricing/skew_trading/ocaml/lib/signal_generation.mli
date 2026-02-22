(* Interface for skew trading signal generation *)

open Types

(** Generate mean reversion signal based on historical z-score

    Logic:
    - If RR25 z-score > +2: Skew is cheap (less negative) → Long skew
    - If RR25 z-score < -2: Skew is rich (more negative) → Short skew
    - Otherwise: Neutral
*)
val mean_reversion_signal :
  skew_observation array ->
  current_observation:skew_observation ->
  config:skew_config ->
  skew_signal

(** Generate regime-based signal using market conditions

    Considers:
    - Current market regime (bull/bear/neutral)
    - Historical skew behavior in similar regimes
    - VIX level and trend
*)
val regime_based_signal :
  skew_observation array ->
  spot_returns:float array ->
  current_observation:skew_observation ->
  config:skew_config ->
  skew_signal

(** Generate cross-sectional signal comparing skew across strikes

    Identifies relative value opportunities
*)
val cross_sectional_signal :
  vol_surface ->
  underlying_data ->
  rate:float ->
  expiry:float ->
  config:skew_config ->
  skew_signal

(** Backtest signals on historical data

    Simulates strategy P&L from historical skew observations
*)
val backtest_strategy :
  skew_observations:skew_observation array ->
  spot_prices:float array ->
  vol_surfaces:(float * vol_surface) array ->
  config:skew_config ->
  strategy_pnl array

(** Recommend strategy based on signal *)
val recommend_strategy :
  signal_type ->
  skew_observation ->
  vol_surface ->
  underlying_data ->
  rate:float ->
  config:skew_config ->
  strategy_type option

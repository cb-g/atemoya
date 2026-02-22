(* Interface for spread modeling *)

open Types

(** Spread statistics **)

val zscore :
  spread:float ->
  mean:float ->
  std:float ->
  float

val calculate_half_life :
  float array ->
  float option

val calculate_spread_stats :
  float array ->
  spread_stats

(** Signal generation **)

val generate_signal :
  zscore:float ->
  entry_threshold:float ->
  exit_threshold:float ->
  current_position:position option ->
  signal_type

val generate_signals :
  spread_series:float array ->
  entry_threshold:float ->
  exit_threshold:float ->
  trading_signal array

(** Position management **)

val position_sizes :
  hedge_ratio:float ->
  capital:float ->
  price1:float ->
  price2:float ->
  float * float

val create_position :
  entry_time:float ->
  entry_zscore:float ->
  entry_spread:float ->
  position_type:signal_type ->
  hedge_ratio:float ->
  capital:float ->
  price1:float ->
  price2:float ->
  position

val position_pnl :
  position:position ->
  current_price1:float ->
  current_price2:float ->
  entry_price1:float ->
  entry_price2:float ->
  float

(** Dynamic half-life monitoring **)

val rolling_half_life :
  spread_series:float array ->
  window:int ->
  float option array

val monitor_half_life :
  spread_series:float array ->
  window:int ->
  half_life_monitor option

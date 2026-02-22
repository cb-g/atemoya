(* Interface for hedging strategies *)

open Types

(** Hedging decision functions **)

(* Check if hedging is required based on delta threshold *)
val should_hedge_threshold :
  current_delta:float ->
  threshold:float ->
  bool

(* Check if hedging is required based on time interval *)
val should_hedge_time :
  current_time:float ->
  last_hedge_time:float ->
  interval_minutes:int ->
  bool

(* Check if hedging is required based on hybrid strategy (threshold OR time) *)
val should_hedge_hybrid :
  current_delta:float ->
  threshold:float ->
  current_time:float ->
  last_hedge_time:float ->
  interval_minutes:int ->
  bool

(* Check if hedging is required based on realized vol adaptive strategy *)
val should_hedge_vol_adaptive :
  current_delta:float ->
  current_time:float ->
  last_hedge_time:float ->
  recent_returns:float array ->
  low_threshold:float ->
  high_threshold:float ->
  bool

(* Generic hedging decision based on strategy type *)
val should_hedge :
  strategy:hedging_strategy ->
  current_delta:float ->
  current_time:float ->
  last_hedge_time:float ->
  recent_returns:float array option ->
  bool

(** Hedging execution **)

(* Execute a hedge trade and create hedge event *)
val execute_hedge :
  timestamp:float ->
  spot_price:float ->
  current_delta:float ->
  transaction_cost_bps:float ->
  hedge_event

(** Realized volatility calculation **)

(* Calculate realized volatility from returns *)
val realized_volatility :
  returns:float array ->
  annualization_factor:float ->
  float

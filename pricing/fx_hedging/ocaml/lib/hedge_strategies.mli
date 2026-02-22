(* Interface for hedge strategies *)

open Types

(** Static hedging **)

(* Build static futures hedge *)
val static_futures_hedge :
  exposure_usd:float ->
  hedge_ratio:float ->
  futures:futures_contract ->
  entry_date:float ->
  hedge_position

(* Build static options hedge *)
val static_options_hedge :
  exposure_usd:float ->
  hedge_ratio:float ->
  option:futures_option ->
  entry_date:float ->
  hedge_position

(** Dynamic hedging **)

(* Check if rebalancing is needed for dynamic strategy *)
val should_rebalance :
  strategy:hedge_strategy ->
  current_delta:float ->
  target_delta:float ->
  last_rebalance_date:float ->
  current_date:float ->
  bool

(* Calculate rebalancing trade size *)
val rebalance_size :
  current_position:int ->
  current_delta:float ->
  target_delta:float ->
  exposure_usd:float ->
  futures_price:float ->
  contract_size:float ->
  int  (* Additional contracts to trade *)

(** Hedge evaluation **)

(* Calculate current delta of hedge position *)
val hedge_delta :
  hedge:hedge_position ->
  current_futures_price:float ->
  current_rate:float ->
  float

(* Calculate hedge effectiveness

   Effectiveness = 1 - Var(hedged) / Var(unhedged)
*)
val hedge_effectiveness :
  unhedged_returns:float array ->
  hedged_returns:float array ->
  float

(* Calculate hedge P&L *)
val hedge_pnl :
  hedge:hedge_position ->
  current_futures_price:float ->
  current_rate:float ->
  float

(** Roll management **)

(* Determine if futures contract should be rolled *)
val should_roll :
  futures:futures_contract ->
  current_date:float ->
  days_before_expiry:int ->
  bool

(* Execute roll to next contract *)
val roll_futures :
  current_position:hedge_position ->
  new_futures:futures_contract ->
  current_date:float ->
  (hedge_position * roll_event)

(** Portfolio hedging **)

(* Build multi-currency hedge *)
val build_multi_currency_hedge :
  exposures:fx_exposure array ->
  hedge_strategy:hedge_strategy ->
  futures_contracts:futures_contract array ->
  entry_date:float ->
  hedge_position array

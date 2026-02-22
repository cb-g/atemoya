(* Interface for arbitrage detection *)

open Types

(** Detect butterfly spread arbitrage violations
    Condition: C(K1) + C(K3) >= 2·C(K2) for K1 < K2 < K3 with equal spacing *)
val detect_butterfly_arbitrage :
  vol_surface ->
  spot:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  arbitrage_signal array

(** Detect calendar spread arbitrage violations
    Condition: C(K, T2) >= C(K, T1) for T1 < T2 *)
val detect_calendar_arbitrage :
  vol_surface ->
  spot:float ->
  strike:float ->
  rate:float ->
  dividend:float ->
  arbitrage_signal array

(** Detect put-call parity violations
    Condition: |C - P - (S·e^(-qT) - K·e^(-rT))| > tolerance *)
val detect_put_call_parity_violation :
  call_price:float ->
  put_price:float ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  ticker:string ->
  arbitrage_signal option

(** Detect vertical spread arbitrage
    Condition: For K1 < K2, C(K1) >= C(K2) and P(K1) <= P(K2) *)
val detect_vertical_arbitrage :
  vol_surface ->
  spot:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  arbitrage_signal array

(** Detect strike arbitrage from market quotes (bid-ask crossover) *)
val detect_strike_arbitrage :
  iv_observation array ->
  arbitrage_signal array

(** Scan for all types of arbitrage *)
val scan_for_arbitrage :
  vol_surface ->
  iv_observations:iv_observation array ->
  underlying:underlying_data ->
  rate:float ->
  config:vol_arb_config ->
  arbitrage_signal array

(** Filter arbitrage signals by minimum profit *)
val filter_by_profit :
  arbitrage_signal array ->
  min_profit:float ->
  arbitrage_signal array

(** Sort arbitrage signals by expected profit *)
val sort_by_profit :
  arbitrage_signal array ->
  arbitrage_signal array

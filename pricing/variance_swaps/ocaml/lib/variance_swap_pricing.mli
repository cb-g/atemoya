(* Interface for variance swap pricing *)

open Types

(** Get implied volatility from vol surface for given strike and expiry *)
val get_iv_from_surface :
  vol_surface ->
  strike:float ->
  expiry:float ->
  spot:float ->
  float

(** Price European option using Black-Scholes formula *)
val bs_price :
  option_type:option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  float

(** Price variance swap using Carr-Madan replication formula

    K_var = (2/T)·e^(rT)·[∫₀^F (P(K)/K²)dK + ∫_F^∞ (C(K)/K²)dK]
*)
val price_variance_swap :
  vol_surface ->
  spot:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  strike_grid:float array ->
  ticker:string ->
  notional:float ->
  variance_swap

(** Compute fair variance strike from discrete strikes using Carr-Madan *)
val carr_madan_discrete :
  option_prices:(float * float * float) array ->  (* (strike, put_price, call_price) *)
  spot:float ->
  forward:float ->
  expiry:float ->
  rate:float ->
  float  (* Variance strike *)

(** Compute variance swap vega notional
    Vega_notional = Notional / (2·√K_var)
*)
val compute_vega_notional :
  notional:float ->
  variance_strike:float ->
  float

(** Variance swap payoff at maturity
    Payoff = Notional × (Realized_Var - K_var)
*)
val variance_swap_payoff :
  variance_swap ->
  realized_variance:float ->
  float

(** Mark-to-market variance swap
    MTM = Notional × (Current_Var_Strike - Entry_Var_Strike) × (T_remaining / T_total)
*)
val variance_swap_mtm :
  variance_swap ->
  current_var_strike:float ->
  days_to_expiry:int ->
  float

(** Generate strike grid for Carr-Madan integration *)
val generate_strike_grid :
  spot:float ->
  num_strikes:int ->
  log_moneyness_range:(float * float) ->
  float array

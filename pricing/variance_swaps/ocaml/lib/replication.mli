(* Interface for variance swap replication using option portfolios *)

open Types

(** Build replication portfolio for variance swap using Carr-Madan formula

    Portfolio consists of:
    - OTM puts (K < F): weights = 2·ΔK / K²
    - OTM calls (K ≥ F): weights = 2·ΔK / K²

    where F = forward price, ΔK = strike spacing
*)
val build_replication_portfolio :
  vol_surface ->
  underlying_data ->
  rate:float ->
  expiry:float ->
  target_variance_notional:float ->
  strike_grid:float array ->
  replication_portfolio

(** Compute Greeks for replication portfolio *)
val portfolio_greeks :
  replication_portfolio ->
  vol_surface:vol_surface ->
  spot:float ->
  rate:float ->
  dividend:float ->
  greeks

(** Check if portfolio is delta-neutral (within tolerance) *)
val is_delta_neutral :
  replication_portfolio ->
  tolerance:float ->
  bool

(** Rebalance portfolio (adjust weights to maintain variance exposure) *)
val rebalance_portfolio :
  replication_portfolio ->
  current_spot:float ->
  vol_surface:vol_surface ->
  rate:float ->
  replication_portfolio

(** Compute variance vega (sensitivity to variance per unit variance) *)
val variance_vega :
  replication_portfolio ->
  float

(** Estimate transaction costs for establishing portfolio *)
val estimate_transaction_costs :
  replication_portfolio ->
  bid_ask_spread_bps:float ->
  float

(** Optimize strike grid (minimize cost while matching target variance exposure) *)
val optimize_strike_grid :
  vol_surface ->
  underlying_data ->
  rate:float ->
  expiry:float ->
  target_variance_notional:float ->
  num_strikes:int ->
  float array  (* Optimal strikes *)

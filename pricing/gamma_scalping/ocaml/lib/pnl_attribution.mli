(* Interface for P&L attribution *)

open Types

(** P&L component calculations **)

(* Calculate gamma P&L from a spot move

   Formula: Gamma P&L ≈ ½ × Γ × (ΔS)²

   This is ALWAYS positive when long gamma (long options)
*)
val compute_gamma_pnl :
  gamma:float ->
  spot_change:float ->
  float

(* Calculate theta P&L from time decay

   Formula: Theta P&L = Θ × Δt

   where Θ is per-day and Δt is in days
   This is ALWAYS negative when long options
*)
val compute_theta_pnl :
  theta:float ->
  time_step_days:float ->
  float

(* Calculate vega P&L from IV change

   Formula: Vega P&L = ν × ΔIV

   where ν is vega per 1% vol change and ΔIV is in percentage points
*)
val compute_vega_pnl :
  vega:float ->
  iv_change:float ->
  float

(** P&L snapshot updates **)

(* Update P&L snapshot with new market data and Greeks

   Takes previous snapshot and current state, returns new snapshot with:
   - Incremental gamma/theta/vega P&L
   - Updated cumulative P&L
   - Current option value
*)
val update_pnl_snapshot :
  previous:pnl_snapshot ->
  current_greeks:greeks ->
  spot_current:float ->
  spot_previous:float ->
  time_step_days:float ->
  iv_current:float ->
  iv_previous:float ->
  option_value_current:float ->
  entry_premium:float ->
  hedge_cost:float ->
  hedge_pnl_current:float ->
  pnl_snapshot

(* Create initial P&L snapshot at t=0 *)
val initial_pnl_snapshot :
  timestamp:float ->
  spot_price:float ->
  entry_premium:float ->
  pnl_snapshot

(** Portfolio metrics **)

(* Calculate Sharpe ratio from P&L timeseries

   Formula: Sharpe = mean(returns) / std(returns) × √252

   Returns None if insufficient data
*)
val calculate_sharpe_ratio :
  pnl_timeseries:pnl_snapshot array ->
  float option

(* Calculate maximum drawdown from P&L timeseries

   Formula: Max DD = max(peak - trough) / peak

   Returns maximum percentage drawdown
*)
val calculate_max_drawdown :
  pnl_timeseries:pnl_snapshot array ->
  float

(* Calculate win rate (percentage of profitable timesteps) *)
val calculate_win_rate :
  pnl_timeseries:pnl_snapshot array ->
  float

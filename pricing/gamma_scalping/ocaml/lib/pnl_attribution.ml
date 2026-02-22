(* P&L attribution for gamma scalping *)

open Types

(** P&L component calculations **)

(* Gamma P&L from spot movement

   Theory: When you're long gamma, you profit from the curvature of your position.
   The second-order Taylor expansion gives:

   dV ≈ Δ·dS + ½·Γ·(dS)²

   When delta-hedged (Δ = 0), only gamma term remains:
   Gamma P&L ≈ ½ × Γ × (ΔS)²

   This is ALWAYS POSITIVE when long options (Γ > 0), regardless of direction.
*)
let compute_gamma_pnl ~gamma ~spot_change =
  0.5 *. gamma *. spot_change *. spot_change

(* Theta P&L from time decay

   Theta measures the time decay per day.
   For a time step Δt (in days):

   Theta P&L = Θ × Δt

   This is ALWAYS NEGATIVE when long options (Θ < 0).
   Theta is the "rent" you pay for holding gamma.
*)
let compute_theta_pnl ~theta ~time_step_days =
  theta *. time_step_days

(* Vega P&L from IV change

   Vega measures sensitivity to implied volatility.
   For an IV change ΔIV (in percentage points):

   Vega P&L = ν × ΔIV

   where ν is vega per 1% vol change.

   Example: If vega = 0.25 and IV goes from 20% to 22% (ΔIV = 2),
           Vega P&L = 0.25 × 2 = 0.50
*)
let compute_vega_pnl ~vega ~iv_change =
  vega *. iv_change

(** P&L snapshot management **)

(* Create initial P&L snapshot at entry *)
let initial_pnl_snapshot ~timestamp ~spot_price ~entry_premium =
  {
    timestamp;
    spot_price;
    option_value = entry_premium;
    option_pnl = 0.0;
    gamma_pnl = 0.0;
    theta_pnl = 0.0;
    vega_pnl = 0.0;
    hedge_pnl = 0.0;
    transaction_costs = 0.0;
    total_pnl = 0.0;
    cumulative_pnl = 0.0;
  }

(* Update P&L snapshot with new market data

   This function:
   1. Computes incremental gamma/theta/vega P&L
   2. Updates option value and option P&L
   3. Accumulates transaction costs
   4. Calculates total and cumulative P&L
*)
let update_pnl_snapshot
    ~previous
    ~current_greeks
    ~spot_current
    ~spot_previous
    ~time_step_days
    ~iv_current
    ~iv_previous
    ~option_value_current
    ~entry_premium
    ~hedge_cost
    ~hedge_pnl_current =

  (* Compute incremental P&L components *)
  let spot_change = spot_current -. spot_previous in
  let iv_change = iv_current -. iv_previous in

  let gamma_pnl_incr = compute_gamma_pnl ~gamma:current_greeks.gamma ~spot_change in
  let theta_pnl_incr = compute_theta_pnl ~theta:current_greeks.theta ~time_step_days in
  let vega_pnl_incr = compute_vega_pnl ~vega:current_greeks.vega ~iv_change in

  (* Accumulate P&L components *)
  let gamma_pnl_total = previous.gamma_pnl +. gamma_pnl_incr in
  let theta_pnl_total = previous.theta_pnl +. theta_pnl_incr in
  let vega_pnl_total = previous.vega_pnl +. vega_pnl_incr in

  (* Option P&L: current value - entry premium *)
  let option_pnl = option_value_current -. entry_premium in

  (* Hedge P&L: mark-to-market of cumulative stock hedge position *)
  let hedge_pnl = hedge_pnl_current in

  (* Accumulate transaction costs *)
  let transaction_costs_total = previous.transaction_costs +. hedge_cost in

  (* Total P&L = Option P&L + Hedge P&L - Transaction Costs

     Alternative view:
     Total P&L ≈ Gamma P&L + Theta P&L + Vega P&L - Transaction Costs
  *)
  let total_pnl = option_pnl +. hedge_pnl -. transaction_costs_total in

  {
    timestamp = previous.timestamp +. time_step_days;
    spot_price = spot_current;
    option_value = option_value_current;
    option_pnl;
    gamma_pnl = gamma_pnl_total;
    theta_pnl = theta_pnl_total;
    vega_pnl = vega_pnl_total;
    hedge_pnl;
    transaction_costs = transaction_costs_total;
    total_pnl;
    cumulative_pnl = total_pnl;  (* Same as total_pnl for single position *)
  }

(** Portfolio metrics **)

(* Calculate Sharpe ratio from P&L timeseries

   Sharpe Ratio = mean(daily returns) / std(daily returns) × √252

   Returns None if insufficient data (< 2 observations)
*)
let calculate_sharpe_ratio ~pnl_timeseries =
  let n = Array.length pnl_timeseries in
  if n < 2 then
    None
  else
    (* Calculate daily P&L changes *)
    let daily_pnl = Array.init (n - 1) (fun i ->
      pnl_timeseries.(i + 1).total_pnl -. pnl_timeseries.(i).total_pnl
    ) in

    (* Mean *)
    let sum = Array.fold_left (+.) 0.0 daily_pnl in
    let mean = sum /. float_of_int (n - 1) in

    (* Standard deviation *)
    let sum_sq_dev = Array.fold_left (fun acc pnl ->
      let dev = pnl -. mean in
      acc +. dev *. dev
    ) 0.0 daily_pnl in
    let variance = sum_sq_dev /. float_of_int (n - 1) in
    let std_dev = sqrt variance in

    if std_dev = 0.0 then
      None
    else
      (* Annualize assuming 252 trading days *)
      Some (mean /. std_dev *. sqrt 252.0)

(* Calculate maximum drawdown

   Max DD = max(peak - trough) / peak over all time

   Returns percentage drawdown (e.g., 0.25 = 25% drawdown)
*)
let calculate_max_drawdown ~pnl_timeseries =
  let n = Array.length pnl_timeseries in
  if n = 0 then
    0.0
  else
    let max_dd = ref 0.0 in
    let peak = ref pnl_timeseries.(0).cumulative_pnl in

    Array.iter (fun snapshot ->
      let current_pnl = snapshot.cumulative_pnl in

      (* Update peak if we hit a new high *)
      if current_pnl > !peak then
        peak := current_pnl;

      (* Calculate drawdown from peak *)
      if !peak > 0.0 then begin
        let drawdown = (!peak -. current_pnl) /. !peak in
        if drawdown > !max_dd then
          max_dd := drawdown
      end
    ) pnl_timeseries;

    !max_dd

(* Calculate win rate (percentage of profitable timesteps)

   Win Rate = (# of timesteps with positive P&L) / (total timesteps)
*)
let calculate_win_rate ~pnl_timeseries =
  let n = Array.length pnl_timeseries in
  if n = 0 then
    0.0
  else
    let profitable_count = Array.fold_left (fun acc snapshot ->
      if snapshot.total_pnl > 0.0 then acc + 1 else acc
    ) 0 pnl_timeseries in

    float_of_int profitable_count /. float_of_int n

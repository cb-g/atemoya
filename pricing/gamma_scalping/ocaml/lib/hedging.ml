(* Hedging strategies for gamma scalping *)

open Types

(** Realized volatility calculation **)

(* Calculate realized volatility from returns

   Formula: σ_realized = sqrt(Σ(r_i²) / N) × √annualization_factor

   where:
   - r_i = log returns
   - N = number of observations
   - annualization_factor = # periods per year (e.g., 252 for daily, 252*390 for minutes)
*)
let realized_volatility ~returns ~annualization_factor =
  let n = Array.length returns in
  if n = 0 then
    0.0
  else
    let sum_squared = Array.fold_left (fun acc r -> acc +. r *. r) 0.0 returns in
    let variance = sum_squared /. float_of_int n in
    sqrt variance *. sqrt annualization_factor

(** Hedging decision functions **)

(* Strategy 1: Delta Threshold Rebalancing

   Rule: Rehedge when |Δ_position| exceeds threshold τ

   Example: τ = 0.10 means rehedge when delta drifts ±10 deltas

   Pros: Adapts to market movement
   Cons: Can over-trade in choppy markets
*)
let should_hedge_threshold ~current_delta ~threshold =
  abs_float current_delta >= threshold

(* Strategy 2: Time-Based Rebalancing

   Rule: Rehedge at fixed time intervals (e.g., every 60 min, every 240 min)

   Pros: Predictable transaction costs
   Cons: May miss optimal hedging opportunities
*)
let should_hedge_time ~current_time ~last_hedge_time ~interval_minutes =
  let time_diff_minutes = (current_time -. last_hedge_time) *. (24.0 *. 60.0) in
  time_diff_minutes >= float_of_int interval_minutes

(* Strategy 3: Hybrid (Threshold + Time)

   Rule: Rehedge if delta threshold breached OR fixed time interval

   Best practice: threshold = 0.10, interval = 240 minutes (4 hours)
*)
let should_hedge_hybrid ~current_delta ~threshold ~current_time ~last_hedge_time ~interval_minutes =
  should_hedge_threshold ~current_delta ~threshold
  || should_hedge_time ~current_time ~last_hedge_time ~interval_minutes

(* Strategy 4: Realized Vol-Adaptive

   Rule: Increase hedging frequency when realized vol is high

   Algorithm:
   1. Compute realized vol from recent returns (e.g., last 20 observations)
   2. If realized_vol > high_threshold: hedge frequently (e.g., |delta| > 0.05 or every 1hr)
   3. If realized_vol > low_threshold: hedge moderately (e.g., |delta| > 0.10 or every 4hr)
   4. Else: hedge infrequently (e.g., |delta| > 0.15 or every 8hr)

   Rationale: Hedge more when gamma opportunities are ripe
*)
let should_hedge_vol_adaptive ~current_delta ~current_time ~last_hedge_time ~recent_returns ~low_threshold ~high_threshold =
  let n = Array.length recent_returns in
  if n < 5 then
    (* Not enough data - default to moderate hedging *)
    should_hedge_hybrid ~current_delta ~threshold:0.10 ~current_time ~last_hedge_time ~interval_minutes:240
  else
    (* Calculate realized vol (annualized, assuming intraday minute data) *)
    let realized_vol = realized_volatility ~returns:recent_returns ~annualization_factor:(252.0 *. 390.0) in

    (* Adaptive thresholds based on realized vol *)
    let (delta_threshold, time_interval) =
      if realized_vol > high_threshold then
        (0.05, 60)    (* High vol: tight threshold, hedge hourly *)
      else if realized_vol > low_threshold then
        (0.10, 240)   (* Medium vol: moderate threshold, hedge every 4 hours *)
      else
        (0.15, 480)   (* Low vol: loose threshold, hedge every 8 hours *)
    in

    should_hedge_hybrid ~current_delta ~threshold:delta_threshold
                        ~current_time ~last_hedge_time ~interval_minutes:time_interval

(* Generic hedging decision based on strategy type *)
let should_hedge ~strategy ~current_delta ~current_time ~last_hedge_time ~recent_returns =
  match strategy with
  | DeltaThreshold { threshold } ->
      should_hedge_threshold ~current_delta ~threshold

  | TimeBased { interval_minutes } ->
      should_hedge_time ~current_time ~last_hedge_time ~interval_minutes

  | Hybrid { threshold; interval_minutes } ->
      should_hedge_hybrid ~current_delta ~threshold ~current_time ~last_hedge_time ~interval_minutes

  | VolAdaptive { low_threshold; high_threshold } ->
      let returns = match recent_returns with
        | Some r -> r
        | None -> [||]  (* No recent returns - will default to moderate hedging *)
      in
      should_hedge_vol_adaptive ~current_delta ~current_time ~last_hedge_time ~recent_returns:returns ~low_threshold ~high_threshold

(** Hedging execution **)

(* Execute a hedge trade

   When you're long gamma (long options), delta changes as spot moves:
   - If spot rises: delta increases (more positive for calls, less negative for puts)
     → Need to SELL stock to neutralize delta
   - If spot falls: delta decreases (less positive for calls, more negative for puts)
     → Need to BUY stock to neutralize delta

   Hedge quantity = -current_delta (opposite sign to neutralize)

   Transaction cost = |hedge_quantity| × spot_price × (cost_bps / 10000)
*)
let execute_hedge ~timestamp ~spot_price ~current_delta ~transaction_cost_bps =
  (* Hedge quantity is opposite sign of current delta *)
  let hedge_quantity = -. current_delta in

  (* Transaction cost in basis points *)
  let hedge_cost = abs_float hedge_quantity *. spot_price *. (transaction_cost_bps /. 10000.0) in

  {
    timestamp;
    spot_price;
    delta_before = current_delta;
    hedge_quantity;
    hedge_cost;
  }

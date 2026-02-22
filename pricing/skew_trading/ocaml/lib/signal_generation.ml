(* Signal generation for skew trading *)

open Types
open Skew_measurement

(* ========================================================================== *)
(* Mean Reversion Signal *)
(* ========================================================================== *)

let mean_reversion_signal observations ~current_observation ~config =
  (*
    Mean reversion strategy:
    - Compute historical mean and std of RR25
    - Calculate z-score of current RR25
    - Generate signal if |z-score| > threshold

    Typical behavior (equity indices):
    - RR25 mean ~ -4% (negative, put skew)
    - When RR25 = -2% (less negative): Skew is cheap → Long skew
    - When RR25 = -6% (more negative): Skew is rich → Short skew
  *)
  let (mean_rr25, std_rr25, _, _) = skew_statistics observations ~metric:"rr25" in

  let current_rr25 = current_observation.rr25 in
  let z_score = if std_rr25 > 0.0 then
    (current_rr25 -. mean_rr25) /. std_rr25
  else 0.0 in

  (* Generate signal *)
  let signal_type =
    if abs_float z_score > config.rr25_mean_reversion_threshold then
      if z_score > 0.0 then
        (* RR25 is high (less negative than usual) → Skew is cheap → Go long skew *)
        LongSkew {
          reason = Printf.sprintf "RR25 %.2f%% (z-score %.2f) above mean %.2f%% - skew is cheap"
            (current_rr25 *. 100.0) z_score (mean_rr25 *. 100.0);
          current_rr25;
          historical_mean = mean_rr25;
          z_score;
        }
      else
        (* RR25 is low (more negative than usual) → Skew is rich → Go short skew *)
        ShortSkew {
          reason = Printf.sprintf "RR25 %.2f%% (z-score %.2f) below mean %.2f%% - skew is rich"
            (current_rr25 *. 100.0) z_score (mean_rr25 *. 100.0);
          current_rr25;
          historical_mean = mean_rr25;
          z_score;
        }
    else
      Neutral {
        reason = Printf.sprintf "RR25 %.2f%% (z-score %.2f) within normal range [%.2f, %.2f]"
          (current_rr25 *. 100.0) z_score
          (-.config.rr25_mean_reversion_threshold) config.rr25_mean_reversion_threshold;
      }
  in

  (* Confidence based on z-score magnitude *)
  let confidence = min 1.0 (abs_float z_score /. 3.0) in

  (* Recommended strategy *)
  let recommended_strategy = match signal_type with
    | LongSkew _ ->
        (* Long skew: buy call, sell put *)
        Some (RiskReversal {
          buy_strike = current_observation.call_25d_strike;
          sell_strike = current_observation.put_25d_strike;
          ratio = 1.0;
        })
    | ShortSkew _ ->
        (* Short skew: sell call, buy put *)
        Some (RiskReversal {
          buy_strike = current_observation.put_25d_strike;
          sell_strike = current_observation.call_25d_strike;
          ratio = 1.0;
        })
    | Neutral _ -> None
  in

  (* Position size based on confidence *)
  let position_size = if confidence >= config.min_confidence then
    confidence *. config.target_vega_notional
  else 0.0 in

  {
    timestamp = current_observation.timestamp;
    ticker = current_observation.ticker;
    signal_type;
    confidence;
    recommended_strategy;
    position_size;
  }

(* ========================================================================== *)
(* Regime-Based Signal *)
(* ========================================================================== *)

let regime_based_signal observations ~spot_returns ~current_observation ~config =
  (*
    Adjust signal based on market regime:
    - Bull market: Skew tends to flatten → Favor short skew
    - Bear market: Skew steepens → Favor long skew (or avoid)
    - High VIX: Skew rich → Short skew (if brave)
  *)

  (* Determine regime from recent returns *)
  let recent_returns = Array.sub spot_returns
    (max 0 (Array.length spot_returns - 20))
    (min 20 (Array.length spot_returns))
  in

  let avg_return = Array.fold_left (+.) 0.0 recent_returns /. float_of_int (Array.length recent_returns) in

  let regime = if avg_return > 0.001 then "bull"
    else if avg_return < -0.001 then "bear"
    else "neutral"
  in

  (* Compute mean reversion signal first *)
  let base_signal = mean_reversion_signal observations ~current_observation ~config in

  (* Adjust confidence based on regime *)
  let adjusted_confidence = match (base_signal.signal_type, regime) with
    | (ShortSkew _, "bull") -> base_signal.confidence *. 1.2  (* Favorable *)
    | (ShortSkew _, "bear") -> base_signal.confidence *. 0.5  (* Risky *)
    | (LongSkew _, "bear") -> base_signal.confidence *. 1.1   (* Favorable *)
    | _ -> base_signal.confidence
  in

  { base_signal with confidence = min 1.0 adjusted_confidence }

(* ========================================================================== *)
(* Cross-Sectional Signal *)
(* ========================================================================== *)

let cross_sectional_signal vol_surface underlying_data ~rate ~expiry ~config =
  (*
    Look at entire smile shape to find relative value

    Example: If BF25 is very high → Smile is expensive → Short butterfly
  *)
  let spot = underlying_data.spot_price in
  let dividend = underlying_data.dividend_yield in

  let rr25 = compute_rr25 vol_surface ~spot ~expiry ~rate ~dividend in
  let bf25 = compute_bf25 vol_surface ~spot ~expiry ~rate ~dividend in

  (* Simple heuristic: if BF25 > 0.03 (3%), butterfly is expensive *)
  let signal_type = if bf25 > 0.03 then
    ShortSkew {
      reason = Printf.sprintf "BF25 %.2f%% indicates expensive smile - short butterfly"
        (bf25 *. 100.0);
      current_rr25 = rr25;
      historical_mean = rr25;
      z_score = 0.0;
    }
  else
    Neutral { reason = "No cross-sectional signal" }
  in

  let confidence = min 1.0 (abs_float bf25 /. 0.05) in

  {
    timestamp = Unix.time ();
    ticker = underlying_data.ticker;
    signal_type;
    confidence;
    recommended_strategy = None;
    position_size = if confidence >= config.min_confidence then
      confidence *. config.target_vega_notional
    else 0.0;
  }

(* ========================================================================== *)
(* Backtesting *)
(* ========================================================================== *)

let backtest_strategy ~skew_observations:(skew_observations : skew_observation array) ~spot_prices ~vol_surfaces ~config =
  (*
    Simulate P&L from trading skew signals

    For each observation:
    1. Generate signal
    2. Enter position if signal is strong enough
    3. Hold until next rebalance or signal flip
    4. Compute P&L from skew change
  *)
  let n = Array.length skew_observations in
  if n = 0 || Array.length spot_prices <> n || Array.length vol_surfaces <> n then [||]
  else begin
    let cumulative_pnl = ref 0.0 in
    let peak_pnl = ref 0.0 in
    let pnl_history = ref [] in
    let prev_signal_type = ref `None in  (* Track position changes for txn costs *)

    (* Pre-compute signals for each day to avoid look-ahead bias.
       Signal from day i determines position for day i+1. *)
    let signals = Array.init n (fun i ->
      if i < config.lookback_days then None
      else begin
        (* Rolling window: use only the last lookback_days observations.
           This makes the estimated mean shift with market conditions,
           creating more signal transitions and realistic P&L dynamics. *)
        let start = max 0 (i - config.lookback_days) in
        let hist_obs : skew_observation array = Array.sub skew_observations start (i - start) in
        Some (mean_reversion_signal hist_obs ~current_observation:skew_observations.(i) ~config)
      end
    ) in

    (* Helper to classify signal direction *)
    let signal_direction = function
      | Some s -> begin match s.signal_type with
          | LongSkew _ -> `Long
          | ShortSkew _ -> `Short
          | Neutral _ -> `Flat
        end
      | None -> `None
    in

    Array.init n (fun i ->
      if i < config.lookback_days + 1 then
        (* Not enough history, or no prior signal *)
        {
          timestamp = skew_observations.(i).timestamp;
          position = None;
          mark_to_market = 0.0;
          realized_pnl = 0.0;
          cumulative_pnl = 0.0;
          sharpe_ratio = None;
          max_drawdown = None;
          sortino_ratio = None;
          return_skewness = None;
        }
      else begin
        (* Use PREVIOUS day's signal to determine today's position.
           P&L comes from today's RR25 change. This removes look-ahead bias. *)
        let prev_signal = signals.(i - 1) in

        (* Transaction cost: charged when position direction changes *)
        let cur_dir = signal_direction prev_signal in
        let txn_cost = if cur_dir <> !prev_signal_type && cur_dir <> `Flat && cur_dir <> `None then
          (* Charge transaction cost as fraction of position notional *)
          let pos_size = match prev_signal with Some s -> s.position_size | None -> 0.0 in
          pos_size *. config.transaction_cost_bps /. 10000.0 *. 1000.0
        else 0.0 in
        prev_signal_type := cur_dir;

        (* Compute P&L from RR25 change using yesterday's signal.
           Mean reversion: when z > 0 (RR25 above mean), go LongSkew
           = long put skew = profit when RR25 decreases back to mean. *)
        let rr25_change = skew_observations.(i).rr25 -. skew_observations.(i-1).rr25 in
        let mtm_pnl = match prev_signal with
          | Some s -> begin match s.signal_type with
              | LongSkew _ ->
                  (* Long skew: profit if RR25 decreases (mean reverts down) *)
                  -.s.position_size *. rr25_change *. 1000.0 -. txn_cost
              | ShortSkew _ ->
                  (* Short skew: profit if RR25 increases (mean reverts up) *)
                  s.position_size *. rr25_change *. 1000.0 -. txn_cost
              | Neutral _ -> 0.0
            end
          | None -> 0.0
        in

        cumulative_pnl := !cumulative_pnl +. mtm_pnl;
        pnl_history := mtm_pnl :: !pnl_history;

        (* Track peak for max drawdown *)
        if !cumulative_pnl > !peak_pnl then peak_pnl := !cumulative_pnl;
        let max_drawdown = Some (!cumulative_pnl -. !peak_pnl) in

        (* Rolling 60-day metrics *)
        let sharpe_ratio, sortino_ratio, return_skewness =
          if i >= 60 then
            let recent_pnls = Array.of_list (List.rev (List.filteri (fun idx _ -> idx < 60) !pnl_history)) in
            let len = float_of_int (Array.length recent_pnls) in
            let mean_pnl = Array.fold_left (+.) 0.0 recent_pnls /. len in

            (* Variance and downside variance *)
            let var_pnl = ref 0.0 in
            let downside_var = ref 0.0 in
            Array.iter (fun pnl ->
              let dev = pnl -. mean_pnl in
              var_pnl := !var_pnl +. dev *. dev;
              if pnl < 0.0 then
                downside_var := !downside_var +. pnl *. pnl
            ) recent_pnls;
            let std_pnl = sqrt (!var_pnl /. len) in
            let downside_std = sqrt (!downside_var /. len) in

            (* Sharpe ratio *)
            let sharpe = if std_pnl > 0.0 then
              Some ((mean_pnl *. sqrt 252.0) /. std_pnl)
            else None in

            (* Sortino ratio: penalizes only downside volatility *)
            let sortino = if downside_std > 0.0 then
              Some ((mean_pnl *. sqrt 252.0) /. downside_std)
            else if mean_pnl > 0.0 then
              Some (mean_pnl *. sqrt 252.0 /. std_pnl *. 10.0)  (* Cap: 10x Sharpe when no downside *)
            else None in

            (* Return skewness: third standardized moment *)
            let skewness = if std_pnl > 0.0 then begin
              let m3 = ref 0.0 in
              Array.iter (fun pnl ->
                let dev = pnl -. mean_pnl in
                m3 := !m3 +. dev *. dev *. dev
              ) recent_pnls;
              Some ((!m3 /. len) /. (std_pnl *. std_pnl *. std_pnl))
            end else None in

            (sharpe, sortino, skewness)
          else
            (None, None, None)
        in

        {
          timestamp = skew_observations.(i).timestamp;
          position = None;  (* Simplified - not tracking full positions *)
          mark_to_market = mtm_pnl;
          realized_pnl = mtm_pnl;
          cumulative_pnl = !cumulative_pnl;
          sharpe_ratio;
          max_drawdown;
          sortino_ratio;
          return_skewness;
        }
      end
    )
  end

(* ========================================================================== *)
(* Strategy Recommendation *)
(* ========================================================================== *)

let recommend_strategy signal_type skew_obs _vol_surface _underlying_data ~rate:_ ~config:_ =
  match signal_type with
  | LongSkew _ ->
      (* Long skew: buy call, sell put (risk reversal) *)
      Some (RiskReversal {
        buy_strike = skew_obs.call_25d_strike;
        sell_strike = skew_obs.put_25d_strike;
        ratio = 1.0;
      })
  | ShortSkew _ ->
      (* Short skew: sell call, buy put (reverse risk reversal) *)
      Some (RiskReversal {
        buy_strike = skew_obs.put_25d_strike;
        sell_strike = skew_obs.call_25d_strike;
        ratio = 1.0;
      })
  | Neutral _ -> None

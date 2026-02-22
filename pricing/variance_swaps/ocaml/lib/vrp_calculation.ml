(* Variance Risk Premium calculation and signal generation *)

open Types

(* ========================================================================== *)
(* VRP Computation *)
(* ========================================================================== *)

let compute_vrp ~ticker ~horizon_days ~implied_var ~forecast_realized_var =
  let vrp = implied_var -. forecast_realized_var in
  let vrp_percent = if implied_var > 0.0 then (vrp /. implied_var) *. 100.0 else 0.0 in

  {
    timestamp = Unix.time ();
    ticker;
    horizon_days;
    implied_var;
    forecast_realized_var;
    vrp;
    vrp_percent;
  }

(* ========================================================================== *)
(* Signal Generation *)
(* ========================================================================== *)

let generate_signal vrp_obs config =
  (*
    Trading rules:
    1. VRP > min_threshold (e.g., +2%) → Short variance (IV > RV, overpriced)
    2. VRP < max_threshold (e.g., -1%) → Long variance (IV < RV, underpriced)
    3. Otherwise → Neutral

    Position sizing: scale by VRP magnitude and confidence
  *)
  let signal_type =
    if vrp_obs.vrp_percent >= config.min_vrp_threshold then
      (* Short variance: IV is too high relative to forecast *)
      ShortVariance {
        reason = Printf.sprintf "VRP = %.2f%% exceeds threshold %.2f%%"
          vrp_obs.vrp_percent config.min_vrp_threshold;
        implied_var = vrp_obs.implied_var;
        forecast_var = vrp_obs.forecast_realized_var;
        vrp_pct = vrp_obs.vrp_percent;
      }
    else if vrp_obs.vrp_percent <= config.max_vrp_threshold then
      (* Long variance: IV is too low *)
      LongVariance {
        reason = Printf.sprintf "VRP = %.2f%% below threshold %.2f%%"
          vrp_obs.vrp_percent config.max_vrp_threshold;
        implied_var = vrp_obs.implied_var;
        forecast_var = vrp_obs.forecast_realized_var;
        vrp_pct = vrp_obs.vrp_percent;
      }
    else
      Neutral {
        reason = Printf.sprintf "VRP = %.2f%% within neutral zone [%.2f%%, %.2f%%]"
          vrp_obs.vrp_percent config.max_vrp_threshold config.min_vrp_threshold;
      }
  in

  (* Confidence based on VRP magnitude *)
  let confidence = match signal_type with
    | ShortVariance { vrp_pct; _ } ->
        min 1.0 (abs_float vrp_pct /. 10.0)  (* Scale 0-10% VRP to 0-1 confidence *)
    | LongVariance { vrp_pct; _ } ->
        min 1.0 (abs_float vrp_pct /. 5.0)   (* Long signals rarer, scale faster *)
    | Neutral _ -> 0.0
  in

  (* Position size: scale by confidence and target vega notional *)
  let position_size = match signal_type with
    | ShortVariance _ | LongVariance _ ->
        confidence *. config.target_vega_notional
    | Neutral _ -> 0.0
  in

  (* Expected Sharpe (simplified, based on historical VRP Sharpe ~1.5-2.0) *)
  let expected_sharpe = match signal_type with
    | ShortVariance _ -> Some 1.5
    | LongVariance _ -> Some 1.0  (* Long variance harder to profit from *)
    | Neutral _ -> None
  in

  {
    timestamp = vrp_obs.timestamp;
    ticker = vrp_obs.ticker;
    signal_type;
    confidence;
    position_size;
    expected_sharpe;
  }

(* ========================================================================== *)
(* VRP Time Series *)
(* ========================================================================== *)

let compute_vrp_time_series ~ticker ~vol_surface_data ~price_data ~horizon_days _config =
  (*
    For each date:
    1. Extract implied variance from vol surface
    2. Compute forecast realized variance from historical prices
    3. Calculate VRP
  *)
  let n = Array.length vol_surface_data in
  if n = 0 then [||]
  else begin
    Array.init n (fun i ->
      let (date, _strikes, ivs) = vol_surface_data.(i) in

      (* Implied variance: ATM IV squared *)
      let atm_iv = if Array.length ivs > 0 then
        ivs.(Array.length ivs / 2)  (* Middle strike as proxy for ATM *)
      else 0.20 in
      let implied_var = atm_iv *. atm_iv in

      (* Forecast realized variance from trailing returns *)
      let lookback = min (horizon_days * 2) (Array.length price_data) in
      let historical_prices = Array.sub price_data (max 0 (i - lookback)) lookback in
      let prices_only = Array.map snd historical_prices in

      let forecast_realized_var = Realized_variance.compute_realized_variance
        ~prices:prices_only
        ~annualization_factor:252.0
      in

      let vrp = implied_var -. forecast_realized_var in
      let vrp_percent = if implied_var > 0.0 then (vrp /. implied_var) *. 100.0 else 0.0 in

      {
        timestamp = date;
        ticker;
        horizon_days;
        implied_var;
        forecast_realized_var;
        vrp;
        vrp_percent;
      }
    )
  end

(* ========================================================================== *)
(* Backtesting *)
(* ========================================================================== *)

let backtest_vrp_strategy ~vrp_observations ~realized_variances ~config =
  (*
    Simulate P&L from trading VRP signals:
    1. Generate signal at each timestep
    2. Enter variance swap position
    3. Compute P&L when realized variance is known
  *)
  let n = Array.length vrp_observations in
  if n = 0 || Array.length realized_variances <> n then [||]
  else begin
    let cumulative_pnl = ref 0.0 in
    let pnl_history = ref [] in

    Array.init n (fun i ->
      let obs = vrp_observations.(i) in
      let signal = generate_signal obs config in

      let position = match signal.signal_type with
        | ShortVariance _ | LongVariance _ ->
            (* Create variance swap position *)
            Some {
              ticker = obs.ticker;
              notional = signal.position_size;
              strike_var = obs.implied_var;
              expiry = float_of_int obs.horizon_days /. 365.0;
              vega_notional = signal.position_size /. (2.0 *. sqrt obs.implied_var);
              entry_date = obs.timestamp;
              entry_spot = 100.0;  (* Normalized *)
            }
        | Neutral _ -> None
      in

      (* Compute P&L: Notional × (Realized - Strike) *)
      let realized_var = realized_variances.(i) in
      let mtm_pnl = match position with
        | Some swap ->
            let payoff = swap.notional *. (realized_var -. swap.strike_var) in
            (* Short variance: we sold at strike, profit if realized < strike *)
            begin match signal.signal_type with
              | ShortVariance _ -> -.payoff  (* We're short, so negative payoff *)
              | LongVariance _ -> payoff
              | Neutral _ -> 0.0
            end
        | None -> 0.0
      in

      cumulative_pnl := !cumulative_pnl +. mtm_pnl;
      pnl_history := mtm_pnl :: !pnl_history;

      (* Compute Sharpe ratio (rolling) *)
      let sharpe_ratio = if i >= 20 then
        let recent_pnls = Array.of_list (List.rev (List.filteri (fun idx _ -> idx < 20) !pnl_history)) in
        let mean_pnl = Array.fold_left (+.) 0.0 recent_pnls /. float_of_int (Array.length recent_pnls) in
        let var_pnl = ref 0.0 in
        Array.iter (fun pnl ->
          let dev = pnl -. mean_pnl in
          var_pnl := !var_pnl +. dev *. dev
        ) recent_pnls;
        let std_pnl = sqrt (!var_pnl /. float_of_int (Array.length recent_pnls)) in
        if std_pnl > 0.0 then
          Some ((mean_pnl *. sqrt 252.0) /. std_pnl)  (* Annualized Sharpe *)
        else None
      else None in

      {
        timestamp = obs.timestamp;
        position;
        realized_var_to_date = realized_var;
        mark_to_market_pnl = mtm_pnl;
        cumulative_pnl = !cumulative_pnl;
        sharpe_ratio;
      }
    )
  end

(* ========================================================================== *)
(* VRP Statistics *)
(* ========================================================================== *)

let vrp_statistics vrp_observations =
  let n = Array.length vrp_observations in
  if n < 2 then (0.0, 0.0, 0.0)
  else begin
    (* Mean VRP *)
    let sum_vrp = Array.fold_left (fun acc obs -> acc +. obs.vrp) 0.0 vrp_observations in
    let mean_vrp = sum_vrp /. float_of_int n in

    (* Standard deviation *)
    let sum_sq_dev = Array.fold_left (fun acc obs ->
      let dev = obs.vrp -. mean_vrp in
      acc +. dev *. dev
    ) 0.0 vrp_observations in
    let std_vrp = sqrt (sum_sq_dev /. float_of_int (n - 1)) in

    (* Sharpe ratio (assuming VRP is the return) *)
    let sharpe_ratio = if std_vrp > 0.0 then
      (mean_vrp *. sqrt 252.0) /. std_vrp  (* Annualized *)
    else 0.0 in

    (mean_vrp, std_vrp, sharpe_ratio)
  end

(* ========================================================================== *)
(* Statistical Significance *)
(* ========================================================================== *)

let is_vrp_significant vrp_observations ~confidence_level =
  (*
    T-test: H0: mean VRP = 0
    t-statistic = mean / (std / √n)
  *)
  let n = Array.length vrp_observations in
  if n < 3 then false
  else begin
    let (mean_vrp, std_vrp, _) = vrp_statistics vrp_observations in

    let t_stat = abs_float (mean_vrp /. (std_vrp /. sqrt (float_of_int n))) in

    (* Critical values for common confidence levels (two-tailed) *)
    let critical_value = match confidence_level with
      | cl when cl >= 0.99 -> 2.576  (* 99% confidence *)
      | cl when cl >= 0.95 -> 1.960  (* 95% confidence *)
      | cl when cl >= 0.90 -> 1.645  (* 90% confidence *)
      | _ -> 1.282                   (* 80% confidence *)
    in

    t_stat > critical_value
  end

(* ========================================================================== *)
(* Wilcoxon Signed-Rank Test *)
(* ========================================================================== *)

let wilcoxon_signed_rank_test vrp_observations ~confidence_level =
  (*
    Non-parametric test: H0: median VRP = 0
    More robust than t-test when VRP has fat tails (crash events).

    Steps:
    1. Remove zero observations
    2. Rank absolute VRP values
    3. Sum ranks of positive observations (W+)
    4. Compare to expected distribution under H0
  *)
  let n = Array.length vrp_observations in
  if n < 10 then (false, 0.0, 0.0)
  else begin
    (* Extract non-zero VRP values *)
    let vrps = Array.to_list (Array.map (fun obs -> obs.vrp) vrp_observations) in
    let non_zero = List.filter (fun v -> abs_float v > 1e-12) vrps in
    let nr = List.length non_zero in
    if nr < 10 then (false, 0.0, 0.0)
    else begin
      (* Sort by absolute value and assign ranks *)
      let with_abs = List.map (fun v -> (abs_float v, v)) non_zero in
      let sorted = List.sort (fun (a, _) (b, _) -> compare a b) with_abs in
      let ranked = List.mapi (fun i (_, v) -> (float_of_int (i + 1), v)) sorted in

      (* Handle ties: average ranks for tied absolute values *)
      (* Simplified: assign sequential ranks (sufficient for typical VRP data) *)

      (* W+ = sum of ranks where VRP > 0 *)
      let w_plus = List.fold_left (fun acc (rank, v) ->
        if v > 0.0 then acc +. rank else acc
      ) 0.0 ranked in

      (* Under H0: E[W+] = n(n+1)/4, Var[W+] = n(n+1)(2n+1)/24 *)
      let nf = float_of_int nr in
      let expected_w = nf *. (nf +. 1.0) /. 4.0 in
      let var_w = nf *. (nf +. 1.0) *. (2.0 *. nf +. 1.0) /. 24.0 in
      let std_w = sqrt var_w in

      (* Z-statistic (normal approximation, valid for n >= 10) *)
      let z_stat = if std_w > 0.0 then (w_plus -. expected_w) /. std_w else 0.0 in

      let critical_value = match confidence_level with
        | cl when cl >= 0.99 -> 2.576
        | cl when cl >= 0.95 -> 1.960
        | cl when cl >= 0.90 -> 1.645
        | _ -> 1.282
      in

      (abs_float z_stat > critical_value, z_stat, w_plus)
    end
  end

(* ========================================================================== *)
(* Kelly Criterion Position Sizing *)
(* ========================================================================== *)

let kelly_position_size vrp_observations ~target_notional ~max_leverage =
  (*
    Kelly fraction: f* = μ / σ²

    where:
      μ = expected VRP (mean historical)
      σ² = variance of VRP

    For variance swaps:
      Position = Kelly fraction × Target notional
      Capped at max_leverage
  *)
  let (mean_vrp, std_vrp, _) = vrp_statistics vrp_observations in

  if std_vrp <= 0.0 then target_notional
  else begin
    let variance_vrp = std_vrp *. std_vrp in
    let kelly_fraction = mean_vrp /. variance_vrp in

    (* Cap at max leverage and ensure positive *)
    let capped_kelly = max 0.0 (min max_leverage kelly_fraction) in

    (* Apply half-Kelly for conservatism *)
    let half_kelly = capped_kelly /. 2.0 in

    half_kelly *. target_notional
  end

(* ========================================================================== *)
(* Regime Change Detection *)
(* ========================================================================== *)

let detect_vrp_regime_change vrp_observations ~window_size ~threshold_zscore =
  (*
    Detect regime shifts using rolling z-score:

    z = (VRP_current - VRP_rolling_mean) / VRP_rolling_std

    Regime change if |z| > threshold
  *)
  let n = Array.length vrp_observations in
  if n < window_size + 1 then Array.make n false
  else begin
    Array.init n (fun i ->
      if i < window_size then false
      else begin
        (* Compute rolling statistics *)
        let window = Array.sub vrp_observations (i - window_size) window_size in

        let sum = Array.fold_left (fun acc obs -> acc +. obs.vrp) 0.0 window in
        let mean = sum /. float_of_int window_size in

        let sum_sq_dev = Array.fold_left (fun acc obs ->
          let dev = obs.vrp -. mean in
          acc +. dev *. dev
        ) 0.0 window in
        let std = sqrt (sum_sq_dev /. float_of_int window_size) in

        (* Current VRP z-score *)
        let current_vrp = vrp_observations.(i).vrp in
        let z_score = if std > 0.0 then abs_float ((current_vrp -. mean) /. std) else 0.0 in

        z_score > threshold_zscore
      end
    )
  end

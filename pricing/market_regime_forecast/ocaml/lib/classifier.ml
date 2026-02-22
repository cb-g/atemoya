(** Combined Regime Classifier

    Combines GARCH (volatility) and HMM (trend) to produce
    a complete market regime classification *)

open Types

(** Calculate cumulative return over last n days (not annualized) *)
let calc_period_return ~returns ~days =
  let n = Array.length returns in
  let actual_days = min days n in
  let start_idx = n - actual_days in
  let cum_return = ref 0.0 in
  for i = start_idx to n - 1 do
    cum_return := !cum_return +. returns.(i)
  done;
  (* Return actual period return, not annualized *)
  !cum_return

(** Classify volatility regime based on GARCH forecast and historical percentile *)
let classify_vol_regime ~vol_forecast:_ ~vol_percentile ~config =
  if vol_percentile >= config.vol_high_percentile then HighVol
  else if vol_percentile <= config.vol_low_percentile then LowVol
  else NormalVol

(** Classify trend regime from HMM state probabilities
    Returns the most likely regime *)
let classify_trend_regime ~trend_probs =
  let max_idx = ref 0 in
  for i = 1 to Array.length trend_probs - 1 do
    if trend_probs.(i) > trend_probs.(!max_idx) then max_idx := i
  done;
  trend_regime_of_int !max_idx

(** Compute confidence from probability distribution *)
let compute_confidence ~probs =
  let max_prob = Array.fold_left max 0.0 probs in
  (* Normalize to 0-1 where 0.33 (uniform) -> 0 and 1.0 -> 1 *)
  let n = float_of_int (Array.length probs) in
  let uniform = 1.0 /. n in
  if max_prob <= uniform then 0.0
  else (max_prob -. uniform) /. (1.0 -. uniform)

(** Full regime classification *)
let classify ~returns ~config =
  let n = Array.length returns in
  if n < 252 then failwith "Need at least 1 year of data for regime classification";

  (* Fit GARCH model *)
  let garch_result = Garch.fit ~returns ~config in

  (* Get volatility metrics *)
  let vol_forecast = Garch.forecast_vol ~result:garch_result ~returns in
  let current_vol = Garch.current_vol ~result:garch_result ~returns in
  let vol_percentile =
    Garch.vol_percentile ~returns ~current_vol ~lookback_years:config.vol_lookback_years
  in

  (* Classify volatility regime *)
  let vol_regime = classify_vol_regime ~vol_forecast ~vol_percentile ~config in

  (* Fit HMM model *)
  let hmm_result = Hmm.fit ~returns ~config in

  (* Get trend probabilities and states *)
  let trend_probs = Hmm.current_state_probs ~params:hmm_result.params ~returns in
  let trend_regime = classify_trend_regime ~trend_probs in

  (* Get state sequence for regime age *)
  let states = Hmm.viterbi ~params:hmm_result.params ~returns in
  let regime_age = Hmm.regime_age ~states in

  (* Compute confidence *)
  let confidence = compute_confidence ~probs:trend_probs in

  (* Calculate actual recent returns for sanity check *)
  let return_1m = calc_period_return ~returns ~days:21 in
  let return_3m = calc_period_return ~returns ~days:63 in
  let return_6m = calc_period_return ~returns ~days:126 in

  (* Next period predictions *)
  let next_trend_probs = Hmm.next_state_probs
    ~params:hmm_result.params
    ~current_probs:trend_probs
  in

  (* Convert state sequence to trend regimes *)
  let regime_history = Array.map trend_regime_of_int states in

  let current_state = {
    trend = trend_regime;
    volatility = vol_regime;
    trend_probs;
    vol_forecast;
    vol_percentile;
    confidence;
    regime_age;
    return_1m;
    return_3m;
    return_6m;
  } in

  {
    as_of_date = "";  (* Set by caller *)
    current_state;
    garch_fit = garch_result;
    hmm_fit = hmm_result;
    regime_history;
    next_trend_probs;
  }

(** Quick regime check without full model fitting
    Uses pre-fitted parameters for faster inference *)
let quick_classify ~garch_params ~hmm_params ~returns ~config =
  let n = Array.length returns in
  if n < 20 then failwith "Need at least 20 days of data";

  (* GARCH volatility *)
  let garch_result = {
    params = garch_params;
    log_likelihood = 0.0;
    persistence = garch_params.alpha +. garch_params.beta;
    unconditional_vol = 0.0;
    aic = 0.0;
    bic = 0.0;
  } in

  let vol_forecast = Garch.forecast_vol ~result:garch_result ~returns in
  let current_vol = Garch.current_vol ~result:garch_result ~returns in
  let vol_percentile =
    Garch.vol_percentile ~returns ~current_vol ~lookback_years:config.vol_lookback_years
  in
  let vol_regime = classify_vol_regime ~vol_forecast ~vol_percentile ~config in

  (* HMM state *)
  let trend_probs = Hmm.current_state_probs ~params:hmm_params ~returns in
  let trend_regime = classify_trend_regime ~trend_probs in
  let confidence = compute_confidence ~probs:trend_probs in

  {
    trend = trend_regime;
    volatility = vol_regime;
    trend_probs;
    vol_forecast;
    vol_percentile;
    confidence;
    regime_age = 0;  (* Not computed in quick mode *)
    return_1m = calc_period_return ~returns ~days:21;
    return_3m = calc_period_return ~returns ~days:63;
    return_6m = calc_period_return ~returns ~days:126;
  }

(** Summarize regime for display *)
let summarize_regime state =
  let trend_str = string_of_trend_regime state.trend in
  let vol_str = string_of_vol_regime state.volatility in
  Printf.sprintf "%s market, %s (confidence: %.0f%%)"
    trend_str vol_str (state.confidence *. 100.0)

(** Get regime suitability for covered call strategies *)
let covered_call_suitability state =
  match state.trend, state.volatility with
  | Sideways, HighVol -> 5    (* Optimal *)
  | Sideways, NormalVol -> 4
  | Bear, HighVol -> 4        (* Good premium, some downside protection *)
  | Bull, HighVol -> 3        (* Good premium but opportunity cost *)
  | Sideways, LowVol -> 3     (* OK but low premium *)
  | Bear, NormalVol -> 3
  | Bull, NormalVol -> 2      (* Opportunity cost *)
  | Bear, LowVol -> 2
  | Bull, LowVol -> 1         (* Worst: low premium + opportunity cost *)

(** Get recommended income ETF strategy based on regime *)
let recommend_strategy state =
  match state.trend, state.volatility with
  | Sideways, HighVol ->
      "Optimal for covered call ETFs. High premium income, low directional risk."
  | Sideways, NormalVol ->
      "Good for covered call ETFs. Decent premiums in range-bound market."
  | Bear, HighVol ->
      "Covered calls provide downside cushion. Consider collar strategies."
  | Bull, HighVol ->
      "High premiums but opportunity cost from caps. Consider lower coverage."
  | Sideways, LowVol ->
      "Compressed premiums reduce income potential. May need longer DTE."
  | Bear, NormalVol ->
      "Moderate premium cushion. Watch for NAV erosion risk."
  | Bull, NormalVol ->
      "Opportunity cost likely. Consider reducing covered call exposure."
  | Bear, LowVol ->
      "Low premiums with downside risk. Consider protective strategies."
  | Bull, LowVol ->
      "Unfavorable: Low premiums and capped upside. Avoid or minimize."


(* ============================================================ *)
(* MS-GARCH Classification - Alternative unified model          *)
(* ============================================================ *)

(** MS-GARCH classification result *)
type ms_garch_classification = {
  current_state: regime_state;
  ms_result: Ms_garch.ms_garch_result;
  regime_history: vol_regime array;  (** Historical vol regimes from MS-GARCH *)
  next_vol_probs: float array;       (** Forecast regime probabilities *)
}

(** Infer trend from MS-GARCH regime means and recent returns *)
let infer_trend_from_ms_garch ~ms_result ~returns =
  let probs = Ms_garch.current_regime_probs ms_result in
  let params = ms_result.Ms_garch.params in

  (* Weighted average of regime means *)
  let weighted_mu = ref 0.0 in
  for k = 0 to params.n_regimes - 1 do
    weighted_mu := !weighted_mu +. probs.(k) *. params.mus.(k)
  done;

  (* Also look at recent actual returns for sanity *)
  let return_1m = calc_period_return ~returns ~days:21 in
  let return_3m = calc_period_return ~returns ~days:63 in

  (* Combine model-implied mean with actual returns *)
  let annualized_mu = !weighted_mu *. 252.0 in
  let annualized_3m = return_3m *. 4.0 in

  (* Classification thresholds *)
  let bull_threshold = 0.10 in   (* 10% annualized *)
  let bear_threshold = -0.05 in  (* -5% annualized *)

  let avg_signal = (annualized_mu +. annualized_3m) /. 2.0 in

  let trend =
    if avg_signal > bull_threshold then Bull
    else if avg_signal < bear_threshold then Bear
    else Sideways
  in

  (* Trend probabilities based on return distribution *)
  let bull_prob = if avg_signal > 0.0 then min 1.0 (avg_signal /. 0.20) else 0.0 in
  let bear_prob = if avg_signal < 0.0 then min 1.0 (-.avg_signal /. 0.20) else 0.0 in
  let side_prob = 1.0 -. bull_prob -. bear_prob in
  let trend_probs = [| bull_prob; bear_prob; max 0.0 side_prob |] in

  (* Normalize *)
  let total = Array.fold_left (+.) 0.0 trend_probs in
  if total > 0.0 then
    Array.iteri (fun i p -> trend_probs.(i) <- p /. total) trend_probs;

  (trend, trend_probs, return_1m, return_3m)

(** Full MS-GARCH regime classification *)
let classify_ms_garch ~returns ~config =
  let n = Array.length returns in
  if n < 252 then failwith "Need at least 1 year of data for regime classification";

  (* Fit MS-GARCH model *)
  let ms_result_raw = Ms_garch.fit ~returns ~config in

  (* Relabel regimes by volatility (0=low, 1=normal, 2=high) *)
  let ms_result = Ms_garch.relabel_by_volatility ms_result_raw in

  (* Get current volatility regime *)
  let vol_probs = Ms_garch.current_regime_probs ms_result in
  let vol_idx = Ms_garch.current_regime ms_result in
  let vol_regime = Ms_garch.regime_to_vol_regime ~n_regimes:ms_result.params.n_regimes vol_idx in

  (* Get volatility forecast from regime-weighted unconditional vols *)
  let regime_vols = Ms_garch.regime_volatilities ms_result in
  let vol_forecast = ref 0.0 in
  for k = 0 to ms_result.params.n_regimes - 1 do
    vol_forecast := !vol_forecast +. vol_probs.(k) *. regime_vols.(k)
  done;

  (* Vol percentile based on regime *)
  let vol_percentile = match vol_idx with
    | 0 -> 0.2  (* Low vol regime *)
    | 1 -> 0.5  (* Normal vol regime *)
    | _ -> 0.8  (* High vol regime *)
  in

  (* Infer trend from regime means and returns *)
  let (trend, trend_probs, return_1m, return_3m) =
    infer_trend_from_ms_garch ~ms_result ~returns
  in
  let return_6m = calc_period_return ~returns ~days:126 in

  (* Compute confidence from volatility regime probability *)
  let confidence = vol_probs.(vol_idx) in

  (* Get regime age from smoothed probabilities *)
  let smoothed = ms_result.smoothed_probs in
  let regime_age = ref 1 in
  let t = ref (n - 2) in
  while !t >= 0 && Ms_garch.current_regime { ms_result with smoothed_probs = [| smoothed.(!t) |] } = vol_idx do
    incr regime_age;
    decr t
  done;

  (* Get regime age properly *)
  let regime_age =
    let age = ref 1 in
    for t = n - 2 downto 0 do
      let max_idx = ref 0 in
      for i = 1 to ms_result.params.n_regimes - 1 do
        if smoothed.(t).(i) > smoothed.(t).(!max_idx) then max_idx := i
      done;
      if !max_idx = vol_idx then incr age
      else age := 1  (* Reset if different regime *)
    done;
    !age
  in

  (* Next period forecast *)
  let next_vol_probs = Ms_garch.forecast_regime_probs ms_result in

  (* Historical regimes *)
  let regime_history = Array.init n (fun t ->
    let max_idx = ref 0 in
    for i = 1 to ms_result.params.n_regimes - 1 do
      if smoothed.(t).(i) > smoothed.(t).(!max_idx) then max_idx := i
    done;
    Ms_garch.regime_to_vol_regime ~n_regimes:ms_result.params.n_regimes !max_idx
  ) in

  let current_state = {
    trend;
    volatility = vol_regime;
    trend_probs;
    vol_forecast = !vol_forecast;
    vol_percentile;
    confidence;
    regime_age;
    return_1m;
    return_3m;
    return_6m;
  } in

  {
    current_state;
    ms_result;
    regime_history;
    next_vol_probs;
  }

(** Predictive signals based on liquidity/volume *)

open Types

let array_mean arr =
  let n = Array.length arr in
  if n = 0 then 0.0
  else Array.fold_left ( +. ) 0.0 arr /. float_of_int n

let array_tail arr n =
  let len = Array.length arr in
  if n >= len then arr
  else Array.sub arr (len - n) n

(** Linear regression slope *)
let linear_slope arr =
  let n = Array.length arr in
  if n < 2 then 0.0
  else
    let x_mean = float_of_int (n - 1) /. 2.0 in
    let y_mean = array_mean arr in
    let num = ref 0.0 in
    let den = ref 0.0 in
    for i = 0 to n - 1 do
      let xi = float_of_int i in
      num := !num +. ((xi -. x_mean) *. (arr.(i) -. y_mean));
      den := !den +. ((xi -. x_mean) ** 2.0)
    done;
    if !den = 0.0 then 0.0 else !num /. !den

(** Correlation coefficient *)
let correlation arr1 arr2 =
  let n = min (Array.length arr1) (Array.length arr2) in
  if n < 2 then 0.0
  else
    let a1 = array_tail arr1 n in
    let a2 = array_tail arr2 n in
    let m1 = array_mean a1 in
    let m2 = array_mean a2 in
    let num = ref 0.0 in
    let d1 = ref 0.0 in
    let d2 = ref 0.0 in
    for i = 0 to n - 1 do
      let x = a1.(i) -. m1 in
      let y = a2.(i) -. m2 in
      num := !num +. (x *. y);
      d1 := !d1 +. (x *. x);
      d2 := !d2 +. (y *. y)
    done;
    let den = sqrt (!d1 *. !d2) in
    if den = 0.0 then 0.0 else !num /. den

(** On-Balance Volume: cumulative signed volume *)
let obv close volume =
  let n = Array.length close in
  if n < 2 then [||]
  else begin
    let result = Array.make n 0.0 in
    result.(0) <- 0.0;
    for i = 1 to n - 1 do
      let sign =
        if close.(i) > close.(i - 1) then 1.0
        else if close.(i) < close.(i - 1) then -1.0
        else 0.0
      in
      result.(i) <- result.(i - 1) +. (sign *. volume.(i))
    done;
    result
  end

(** OBV signal with divergence detection *)
let obv_signal close volume ~window =
  let obv_arr = obv close volume in
  let n = Array.length close in
  if n < window then (0.0, "Insufficient Data")
  else
    let price_tail = array_tail close window in
    let obv_tail = array_tail obv_arr window in
    let price_slope = linear_slope price_tail in
    let obv_slope = linear_slope obv_tail in
    let avg_vol = array_mean (array_tail volume window) in
    let strength = if avg_vol > 0.0 then min 100.0 (abs_float obv_slope /. avg_vol *. 100.0) else 0.0 in

    let price_dir = if price_slope > 0.0 then 1 else -1 in
    let obv_dir = if obv_slope > 0.0 then 1 else -1 in

    if price_dir = obv_dir then
      if price_dir > 0 then (strength, "Bullish Confirmation")
      else (-.strength, "Bearish Confirmation")
    else
      if price_dir > 0 then (-.strength *. 0.7, "Bearish Divergence")
      else (strength *. 0.7, "Bullish Divergence")

(** Volume surge detection *)
let volume_surge volume ~window ~threshold =
  let n = Array.length volume in
  if n < window + 1 then (false, 0.0)
  else
    let prev = Array.sub volume (n - window - 1) window in
    let avg = array_mean prev in
    if avg <= 0.0 then (false, 0.0)
    else
      let magnitude = volume.(n - 1) /. avg in
      (magnitude >= threshold, magnitude)

(** Volume trend analysis *)
let volume_trend volume ~window =
  let recent = array_tail volume window in
  let slope = linear_slope recent in
  let avg = array_mean recent in
  let slope_pct = if avg > 0.0 then slope /. avg *. 100.0 else 0.0 in
  let trend =
    if slope_pct > 5.0 then "Increasing"
    else if slope_pct < -5.0 then "Decreasing"
    else "Stable"
  in
  (slope_pct, trend)

(** Volume-price confirmation *)
let volume_price_confirmation close volume ~window =
  let n = Array.length close in
  if n < window + 1 then (0.0, "Insufficient Data")
  else
    (* Calculate returns and volume changes *)
    let price_changes = Array.init (n - 1) (fun i ->
      if close.(i) = 0.0 then 0.0 else (close.(i + 1) -. close.(i)) /. close.(i)) in
    let vol_changes = Array.init (n - 1) (fun i ->
      if volume.(i) = 0.0 then 0.0 else (volume.(i + 1) -. volume.(i)) /. volume.(i)) in

    (* Use absolute price changes *)
    let abs_price = Array.map abs_float price_changes in
    let corr = correlation (array_tail abs_price window) (array_tail vol_changes window) in

    let confirm =
      if Float.is_nan corr then "Insufficient Data"
      else if corr > 0.5 then "Strong Confirmation"
      else if corr > 0.2 then "Moderate Confirmation"
      else if corr < -0.3 then "Divergence Warning"
      else "Neutral"
    in
    (corr, confirm)

(** Smart money flow estimation *)
let smart_money_flow close volume ~window =
  let n = Array.length close in
  if n < window + 1 then (0.0, "Insufficient Data")
  else
    let returns = Array.init (n - 1) (fun i ->
      if close.(i) = 0.0 then 0.0 else (close.(i + 1) -. close.(i)) /. close.(i)) in
    let recent_ret = array_tail returns window in
    let recent_vol = array_tail volume window in
    let total_vol = Array.fold_left ( +. ) 0.0 recent_vol in
    if total_vol = 0.0 then (0.0, "Neutral")
    else begin
      let weighted_sum = ref 0.0 in
      for i = 0 to Array.length recent_ret - 1 do
        weighted_sum := !weighted_sum +. (recent_ret.(i) *. recent_vol.(i) /. total_vol)
      done;
      let flow = !weighted_sum *. 100.0 in
      let signal =
        if flow > 1.0 then "Accumulation"
        else if flow < -1.0 then "Distribution"
        else "Neutral"
      in
      (flow, signal)
    end

(** Compute composite signal score *)
let composite_signal_score ~obv_str ~surge_mag ~vol_slope ~vp_corr ~sm_flow =
  let score =
    obv_str *. 0.3 +.
    (surge_mag -. 1.0) *. 20.0 *. 0.2 +.
    vol_slope *. 0.2 +.
    vp_corr *. 30.0 *. 0.15 +.
    sm_flow *. 5.0 *. 0.15
  in
  let signal =
    if score > 30.0 then "Strong Bullish"
    else if score > 10.0 then "Bullish"
    else if score < -30.0 then "Strong Bearish"
    else if score < -10.0 then "Bearish"
    else "Neutral"
  in
  (score, signal)

(** Compute all signal metrics *)
let compute_signals (data : ticker_data) ~window : signal_metrics =
  let ohlcv = data.ohlcv in
  let (obv_str, obv_sig) = obv_signal ohlcv.close ohlcv.volume ~window in
  let (surge, surge_mag) = volume_surge ohlcv.volume ~window ~threshold:2.0 in
  let (vol_slope, vol_trend) = volume_trend ohlcv.volume ~window:10 in
  let (vp_corr, vp_conf) = volume_price_confirmation ohlcv.close ohlcv.volume ~window:10 in
  let (sm_flow, sm_sig) = smart_money_flow ohlcv.close ohlcv.volume ~window in
  let (sig_score, comp_sig) = composite_signal_score
    ~obv_str ~surge_mag ~vol_slope ~vp_corr ~sm_flow in
  {
    obv_strength = obv_str;
    obv_signal = obv_sig;
    volume_surge = surge;
    surge_magnitude = surge_mag;
    volume_trend = vol_trend;
    volume_trend_slope = vol_slope;
    vp_correlation = vp_corr;
    vp_confirmation = vp_conf;
    smart_money_flow = sm_flow;
    smart_money_signal = sm_sig;
    signal_score = sig_score;
    composite_signal = comp_sig;
  }

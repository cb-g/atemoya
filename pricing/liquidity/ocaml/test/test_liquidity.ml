open Liquidity

let float_eq ~eps = Alcotest.testable
  (fun fmt f -> Format.fprintf fmt "%.6f" f)
  (fun a b -> Float.abs (a -. b) < eps)

(* ── Scoring Tests ── *)

let test_amihud_liquid () =
  (* High dollar volume → low amihud ratio *)
  let close = [| 100.0; 101.0; 100.5; 102.0; 101.5; 103.0 |] in
  let volume = [| 1e7; 1e7; 1e7; 1e7; 1e7; 1e7 |] in
  let ratio = Scoring.amihud_ratio close volume ~window:3 in
  Alcotest.(check bool) "low amihud" true (ratio < 1.0);
  Alcotest.(check bool) "positive" true (ratio > 0.0)

let test_amihud_illiquid () =
  (* Low dollar volume → high amihud ratio *)
  let close = [| 10.0; 11.0; 9.0; 12.0; 8.0; 13.0 |] in
  let volume = [| 100.0; 100.0; 100.0; 100.0; 100.0; 100.0 |] in
  let ratio = Scoring.amihud_ratio close volume ~window:3 in
  Alcotest.(check bool) "high amihud" true (ratio > 1.0)

let test_amihud_insufficient () =
  let close = [| 100.0; 101.0 |] in
  let volume = [| 1e6; 1e6 |] in
  let ratio = Scoring.amihud_ratio close volume ~window:10 in
  Alcotest.(check bool) "infinity" true (Float.is_infinite ratio)

let test_turnover () =
  let volume = [| 5e6; 6e6; 7e6; 5e6; 6e6 |] in
  let shares = 1e9 in
  let t = Scoring.turnover_ratio volume shares ~window:3 in
  (* avg of last 3: (7e6 + 5e6 + 6e6) / 3 = 6e6, turnover = 6e6 / 1e9 = 0.006 *)
  Alcotest.(check (float_eq ~eps:0.001)) "turnover" 0.006 t

let test_turnover_zero_shares () =
  let volume = [| 1e6; 1e6 |] in
  let t = Scoring.turnover_ratio volume 0.0 ~window:2 in
  Alcotest.(check (float_eq ~eps:0.001)) "zero shares = 0" 0.0 t

let test_relative_volume () =
  (* Last = 2e6, prev 3 avg = (1e6 + 1e6 + 1e6) / 3 = 1e6 → relative = 2.0 *)
  let volume = [| 1e6; 1e6; 1e6; 2e6 |] in
  let rv = Scoring.relative_volume volume ~window:3 in
  Alcotest.(check (float_eq ~eps:0.01)) "2x relative" 2.0 rv

let test_relative_volume_insufficient () =
  let volume = [| 1e6; 2e6 |] in
  let rv = Scoring.relative_volume volume ~window:5 in
  Alcotest.(check (float_eq ~eps:0.001)) "insufficient = 0" 0.0 rv

let test_volume_volatility () =
  (* Constant volume → zero volatility *)
  let volume = [| 1e6; 1e6; 1e6; 1e6; 1e6 |] in
  let vv = Scoring.volume_volatility volume ~window:5 in
  Alcotest.(check (float_eq ~eps:0.001)) "constant = 0" 0.0 vv

let test_volume_volatility_high () =
  (* Highly variable volume *)
  let volume = [| 1e6; 5e6; 1e6; 5e6; 1e6 |] in
  let vv = Scoring.volume_volatility volume ~window:5 in
  Alcotest.(check bool) "positive vol" true (vv > 0.0)

let test_spread_proxy () =
  (* Consistent 1% range: high-low = 1.0 on close = 100 *)
  let high = [| 101.0; 101.0; 101.0 |] in
  let low = [| 100.0; 100.0; 100.0 |] in
  let close = [| 100.0; 100.0; 100.0 |] in
  let sp = Scoring.spread_proxy high low close ~window:3 in
  Alcotest.(check (float_eq ~eps:0.01)) "1% spread" 1.0 sp

let test_liquidity_score_excellent () =
  (* All metrics at best levels *)
  let score = Scoring.liquidity_score
    ~amihud:0.005 ~turnover:0.06 ~vol_vol:0.2 ~spread:0.3 in
  (* 50 + 15 + 15 + 10 + 10 = 100 *)
  Alcotest.(check (float_eq ~eps:0.01)) "excellent" 100.0 score

let test_liquidity_score_poor () =
  (* All metrics at worst levels *)
  let score = Scoring.liquidity_score
    ~amihud:15.0 ~turnover:0.0005 ~vol_vol:1.5 ~spread:4.0 in
  (* 50 - 15 - 10 - 10 - 10 = 5 *)
  Alcotest.(check (float_eq ~eps:0.01)) "poor" 5.0 score

let test_liquidity_score_clamped () =
  Alcotest.(check bool) "min 0" true
    (Scoring.liquidity_score ~amihud:100.0 ~turnover:0.0001 ~vol_vol:5.0 ~spread:10.0 >= 0.0);
  Alcotest.(check bool) "max 100" true
    (Scoring.liquidity_score ~amihud:0.001 ~turnover:0.10 ~vol_vol:0.1 ~spread:0.1 <= 100.0)

let test_liquidity_tier () =
  Alcotest.(check string) "excellent" "Excellent" (Scoring.liquidity_tier 90.0);
  Alcotest.(check string) "good" "Good" (Scoring.liquidity_tier 70.0);
  Alcotest.(check string) "fair" "Fair" (Scoring.liquidity_tier 55.0);
  Alcotest.(check string) "poor" "Poor" (Scoring.liquidity_tier 40.0);
  Alcotest.(check string) "very poor" "Very Poor" (Scoring.liquidity_tier 20.0)

(* ── Signals Tests ── *)

let test_obv_uptrend () =
  (* Consistently rising prices *)
  let close = [| 100.0; 101.0; 102.0; 103.0; 104.0; 105.0 |] in
  let volume = [| 1e6; 1e6; 1e6; 1e6; 1e6; 1e6 |] in
  let obv_arr = Signals.obv close volume in
  (* All positive changes → cumulative volume increases *)
  Alcotest.(check bool) "last OBV > 0" true (obv_arr.(5) > 0.0);
  Alcotest.(check bool) "monotonic" true (obv_arr.(5) > obv_arr.(4))

let test_obv_downtrend () =
  let close = [| 105.0; 104.0; 103.0; 102.0; 101.0; 100.0 |] in
  let volume = [| 1e6; 1e6; 1e6; 1e6; 1e6; 1e6 |] in
  let obv_arr = Signals.obv close volume in
  Alcotest.(check bool) "last OBV < 0" true (obv_arr.(5) < 0.0)

let test_obv_empty () =
  let obv_arr = Signals.obv [| 100.0 |] [| 1e6 |] in
  Alcotest.(check int) "single = empty" 0 (Array.length obv_arr)

let test_obv_signal_bullish () =
  let close = [| 100.0; 101.0; 102.0; 103.0; 104.0; 105.0; 106.0; 107.0; 108.0; 109.0; 110.0 |] in
  let volume = [| 1e6; 1.1e6; 1.2e6; 1.3e6; 1.4e6; 1.5e6; 1.6e6; 1.7e6; 1.8e6; 1.9e6; 2e6 |] in
  let (strength, signal) = Signals.obv_signal close volume ~window:5 in
  Alcotest.(check string) "bullish" "Bullish Confirmation" signal;
  Alcotest.(check bool) "positive strength" true (strength > 0.0)

let test_obv_signal_insufficient () =
  let close = [| 100.0; 101.0 |] in
  let volume = [| 1e6; 1e6 |] in
  let (_, signal) = Signals.obv_signal close volume ~window:10 in
  Alcotest.(check string) "insufficient" "Insufficient Data" signal

let test_volume_surge_detected () =
  (* Last volume = 3e6, prev avg = 1e6, threshold = 2.0 → surge *)
  let volume = [| 1e6; 1e6; 1e6; 1e6; 1e6; 3e6 |] in
  let (surge, mag) = Signals.volume_surge volume ~window:4 ~threshold:2.0 in
  Alcotest.(check bool) "surge detected" true surge;
  Alcotest.(check (float_eq ~eps:0.01)) "3x magnitude" 3.0 mag

let test_volume_surge_not_detected () =
  let volume = [| 1e6; 1e6; 1e6; 1e6; 1e6; 1.5e6 |] in
  let (surge, _) = Signals.volume_surge volume ~window:4 ~threshold:2.0 in
  Alcotest.(check bool) "no surge" false surge

let test_volume_trend_increasing () =
  let volume = [| 1e6; 2e6; 3e6; 4e6; 5e6 |] in
  let (slope, trend) = Signals.volume_trend volume ~window:5 in
  Alcotest.(check string) "increasing" "Increasing" trend;
  Alcotest.(check bool) "positive slope" true (slope > 5.0)

let test_volume_trend_stable () =
  let volume = [| 1e6; 1e6; 1e6; 1e6; 1e6 |] in
  let (_, trend) = Signals.volume_trend volume ~window:5 in
  Alcotest.(check string) "stable" "Stable" trend

let test_smart_money_accumulation () =
  (* Prices consistently rising with volume *)
  let close = [| 100.0; 102.0; 104.0; 106.0; 108.0; 110.0 |] in
  let volume = [| 1e6; 2e6; 2e6; 2e6; 2e6; 2e6 |] in
  let (flow, signal) = Signals.smart_money_flow close volume ~window:4 in
  Alcotest.(check bool) "positive flow" true (flow > 0.0);
  Alcotest.(check string) "accumulation" "Accumulation" signal

let test_smart_money_distribution () =
  (* Prices consistently falling with volume *)
  let close = [| 110.0; 108.0; 106.0; 104.0; 102.0; 100.0 |] in
  let volume = [| 1e6; 2e6; 2e6; 2e6; 2e6; 2e6 |] in
  let (flow, signal) = Signals.smart_money_flow close volume ~window:4 in
  Alcotest.(check bool) "negative flow" true (flow < 0.0);
  Alcotest.(check string) "distribution" "Distribution" signal

let test_smart_money_insufficient () =
  let close = [| 100.0; 101.0 |] in
  let volume = [| 1e6; 1e6 |] in
  let (_, signal) = Signals.smart_money_flow close volume ~window:10 in
  Alcotest.(check string) "insufficient" "Insufficient Data" signal

let test_composite_signal_bullish () =
  let (score, signal) = Signals.composite_signal_score
    ~obv_str:50.0 ~surge_mag:3.0 ~vol_slope:20.0 ~vp_corr:0.8 ~sm_flow:5.0 in
  Alcotest.(check string) "strong bullish" "Strong Bullish" signal;
  Alcotest.(check bool) "score > 30" true (score > 30.0)

let test_composite_signal_bearish () =
  let (score, signal) = Signals.composite_signal_score
    ~obv_str:(-80.0) ~surge_mag:0.2 ~vol_slope:(-30.0) ~vp_corr:(-0.9) ~sm_flow:(-8.0) in
  Alcotest.(check string) "strong bearish" "Strong Bearish" signal;
  Alcotest.(check bool) "score < -30" true (score < -30.0)

let test_composite_signal_neutral () =
  let (_, signal) = Signals.composite_signal_score
    ~obv_str:0.0 ~surge_mag:1.0 ~vol_slope:0.0 ~vp_corr:0.0 ~sm_flow:0.0 in
  Alcotest.(check string) "neutral" "Neutral" signal

let test_linear_slope_positive () =
  let slope = Signals.linear_slope [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  Alcotest.(check (float_eq ~eps:0.001)) "slope 1" 1.0 slope

let test_linear_slope_flat () =
  let slope = Signals.linear_slope [| 5.0; 5.0; 5.0; 5.0 |] in
  Alcotest.(check (float_eq ~eps:0.001)) "flat slope" 0.0 slope

let test_correlation_perfect () =
  let a = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let b = [| 2.0; 4.0; 6.0; 8.0; 10.0 |] in
  let r = Signals.correlation a b in
  Alcotest.(check (float_eq ~eps:0.001)) "perfect correlation" 1.0 r

let test_correlation_negative () =
  let a = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let b = [| 10.0; 8.0; 6.0; 4.0; 2.0 |] in
  let r = Signals.correlation a b in
  Alcotest.(check (float_eq ~eps:0.001)) "negative correlation" (-1.0) r

let () =
  Alcotest.run "Liquidity Tests" [
    ("scoring", [
      Alcotest.test_case "Amihud liquid" `Quick test_amihud_liquid;
      Alcotest.test_case "Amihud illiquid" `Quick test_amihud_illiquid;
      Alcotest.test_case "Amihud insufficient" `Quick test_amihud_insufficient;
      Alcotest.test_case "Turnover" `Quick test_turnover;
      Alcotest.test_case "Turnover zero shares" `Quick test_turnover_zero_shares;
      Alcotest.test_case "Relative volume" `Quick test_relative_volume;
      Alcotest.test_case "Relative volume insufficient" `Quick test_relative_volume_insufficient;
      Alcotest.test_case "Volume volatility constant" `Quick test_volume_volatility;
      Alcotest.test_case "Volume volatility high" `Quick test_volume_volatility_high;
      Alcotest.test_case "Spread proxy" `Quick test_spread_proxy;
      Alcotest.test_case "Score excellent" `Quick test_liquidity_score_excellent;
      Alcotest.test_case "Score poor" `Quick test_liquidity_score_poor;
      Alcotest.test_case "Score clamped" `Quick test_liquidity_score_clamped;
      Alcotest.test_case "Tier strings" `Quick test_liquidity_tier;
    ]);
    ("signals", [
      Alcotest.test_case "OBV uptrend" `Quick test_obv_uptrend;
      Alcotest.test_case "OBV downtrend" `Quick test_obv_downtrend;
      Alcotest.test_case "OBV empty" `Quick test_obv_empty;
      Alcotest.test_case "OBV signal bullish" `Quick test_obv_signal_bullish;
      Alcotest.test_case "OBV signal insufficient" `Quick test_obv_signal_insufficient;
      Alcotest.test_case "Volume surge detected" `Quick test_volume_surge_detected;
      Alcotest.test_case "Volume surge not detected" `Quick test_volume_surge_not_detected;
      Alcotest.test_case "Volume trend increasing" `Quick test_volume_trend_increasing;
      Alcotest.test_case "Volume trend stable" `Quick test_volume_trend_stable;
      Alcotest.test_case "Smart money accumulation" `Quick test_smart_money_accumulation;
      Alcotest.test_case "Smart money distribution" `Quick test_smart_money_distribution;
      Alcotest.test_case "Smart money insufficient" `Quick test_smart_money_insufficient;
      Alcotest.test_case "Composite bullish" `Quick test_composite_signal_bullish;
      Alcotest.test_case "Composite bearish" `Quick test_composite_signal_bearish;
      Alcotest.test_case "Composite neutral" `Quick test_composite_signal_neutral;
      Alcotest.test_case "Linear slope positive" `Quick test_linear_slope_positive;
      Alcotest.test_case "Linear slope flat" `Quick test_linear_slope_flat;
      Alcotest.test_case "Correlation perfect" `Quick test_correlation_perfect;
      Alcotest.test_case "Correlation negative" `Quick test_correlation_negative;
    ]);
  ]

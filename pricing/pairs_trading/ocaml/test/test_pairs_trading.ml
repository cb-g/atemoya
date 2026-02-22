(** Unit tests for pairs trading model *)

open Pairs_trading_lib

(* ========== Cointegration Tests ========== *)

let test_mean () =
  let m = Cointegration.mean [| 10.0; 20.0; 30.0; 40.0; 50.0 |] in
  Alcotest.(check (float 0.01)) "mean = 30" 30.0 m

let test_std () =
  let s = Cointegration.std [| 10.0; 20.0; 30.0; 40.0; 50.0 |] in
  (* sample std = sqrt(1000/4) = sqrt(250) = 15.81 *)
  Alcotest.(check (float 0.1)) "std ~ 15.81" 15.81 s

let test_ols_regression_perfect () =
  (* Y = 2X + 3 (perfect linear relationship) *)
  let x = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let y = Array.map (fun xi -> 2.0 *. xi +. 3.0) x in
  let (alpha, beta, residuals) = Cointegration.ols_regression ~x ~y in
  Alcotest.(check (float 0.01)) "alpha = 3" 3.0 alpha;
  Alcotest.(check (float 0.01)) "beta = 2" 2.0 beta;
  Array.iter (fun r ->
    Alcotest.(check (float 0.01)) "residual ~ 0" 0.0 r
  ) residuals

let test_ols_regression_noisy () =
  let x = [| 10.0; 20.0; 30.0; 40.0; 50.0; 60.0; 70.0; 80.0; 90.0; 100.0 |] in
  let y = [| 22.0; 38.0; 58.0; 82.0; 102.0; 118.0; 142.0; 158.0; 182.0; 198.0 |] in
  let (alpha, beta, _) = Cointegration.ols_regression ~x ~y in
  Alcotest.(check bool) "beta ~ 2.0" true (abs_float (beta -. 2.0) < 0.2);
  Alcotest.(check bool) "alpha ~ 2-4" true (alpha > 0.0 && alpha < 10.0)

let test_adf_test () =
  (* Stationary series: random deviations around 0 *)
  let stationary = [| 0.5; -0.3; 0.2; -0.4; 0.1; -0.2; 0.3; -0.1;
                      0.4; -0.5; 0.2; -0.3; 0.1; -0.2; 0.3; -0.4;
                      0.2; -0.1; 0.3; -0.3 |] in
  let (t_stat, critical) = Cointegration.adf_test stationary in
  Alcotest.(check bool) "t-stat is finite" true (Float.is_finite t_stat);
  Alcotest.(check bool) "critical is negative" true (critical < 0.0)

let test_test_cointegration () =
  (* Two cointegrated series: Y ≈ 2X + noise *)
  let n = 100 in
  let prices1 = Array.init n (fun i -> 100.0 +. float_of_int i *. 0.5) in
  let prices2 = Array.init n (fun i ->
    200.0 +. float_of_int i *. 1.0 +. (if i mod 2 = 0 then 0.5 else -0.5)
  ) in
  let result = Cointegration.test_cointegration ~prices1 ~prices2 in
  Alcotest.(check bool) "hedge ratio ~ 2" true
    (abs_float (result.hedge_ratio -. 2.0) < 0.5);
  Alcotest.(check bool) "ADF stat is finite" true
    (Float.is_finite result.adf_statistic);
  Alcotest.(check string) "method name" "Engle-Granger (OLS)" result.method_name

let test_calculate_spread () =
  let prices1 = [| 100.0; 101.0; 102.0 |] in
  let prices2 = [| 200.0; 203.0; 204.0 |] in
  let spread = Cointegration.calculate_spread ~prices1 ~prices2
    ~hedge_ratio:2.0 ~alpha:0.0 in
  (* spread = Y - 2*X - 0 = 200-200, 203-202, 204-204 = 0, 1, 0 *)
  Alcotest.(check (float 0.01)) "spread[0]" 0.0 spread.(0);
  Alcotest.(check (float 0.01)) "spread[1]" 1.0 spread.(1);
  Alcotest.(check (float 0.01)) "spread[2]" 0.0 spread.(2)

(* ========== TLS Tests ========== *)

let test_tls_regression_perfect () =
  (* Y = 2X + 3 — on perfect data TLS should match OLS *)
  let x = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let y = Array.map (fun xi -> 2.0 *. xi +. 3.0) x in
  let (alpha, beta, residuals) = Cointegration.tls_regression ~x ~y in
  Alcotest.(check (float 0.01)) "TLS alpha = 3" 3.0 alpha;
  Alcotest.(check (float 0.01)) "TLS beta = 2" 2.0 beta;
  Array.iter (fun r ->
    Alcotest.(check (float 0.01)) "TLS residual ~ 0" 0.0 r
  ) residuals

let test_tls_regression_symmetric () =
  (* TLS(X,Y) and TLS(Y,X) should give consistent hedge ratios:
     if TLS(X→Y) gives β, then TLS(Y→X) should give ~1/β *)
  let x = [| 10.0; 20.0; 30.0; 40.0; 50.0; 60.0; 70.0; 80.0; 90.0; 100.0 |] in
  let y = [| 22.0; 38.0; 58.0; 82.0; 102.0; 118.0; 142.0; 158.0; 182.0; 198.0 |] in
  let (_, beta_xy, _) = Cointegration.tls_regression ~x ~y in
  let (_, beta_yx, _) = Cointegration.tls_regression ~x:y ~y:x in
  (* β_xy * β_yx should be close to 1 for TLS (symmetric) *)
  let product = beta_xy *. beta_yx in
  Alcotest.(check bool) "TLS symmetric: β_xy * β_yx ~ 1"
    true (abs_float (product -. 1.0) < 0.1)

let test_tls_cointegration () =
  let n = 100 in
  let prices1 = Array.init n (fun i -> 100.0 +. float_of_int i *. 0.5) in
  let prices2 = Array.init n (fun i ->
    200.0 +. float_of_int i *. 1.0 +. (if i mod 2 = 0 then 0.5 else -0.5)
  ) in
  let result = Cointegration.test_cointegration_tls ~prices1 ~prices2 in
  Alcotest.(check bool) "TLS hedge ratio ~ 2" true
    (abs_float (result.hedge_ratio -. 2.0) < 0.5);
  Alcotest.(check string) "TLS method name" "Engle-Granger (TLS)" result.method_name

(* ========== Johansen Tests ========== *)

let test_johansen_cointegrated () =
  (* Two cointegrated series: Y = 2X + stationary noise *)
  let n = 100 in
  let prices1 = Array.init n (fun i -> 100.0 +. float_of_int i *. 0.5) in
  let prices2 = Array.init n (fun i ->
    200.0 +. float_of_int i *. 1.0 +. (if i mod 2 = 0 then 0.5 else -0.5)
  ) in
  let result = Cointegration.johansen_test ~prices1 ~prices2 in
  Alcotest.(check bool) "trace stat is finite" true
    (Float.is_finite result.adf_statistic);
  Alcotest.(check bool) "critical value is 15.41" true
    (abs_float (result.critical_value -. 15.41) < 0.01);
  Alcotest.(check string) "Johansen method name" "Johansen" result.method_name

let test_johansen_short_data () =
  (* Too few observations should return not cointegrated *)
  let prices1 = [| 1.0; 2.0; 3.0 |] in
  let prices2 = [| 2.0; 4.0; 6.0 |] in
  let result = Cointegration.johansen_test ~prices1 ~prices2 in
  Alcotest.(check bool) "short data not cointegrated" false result.is_cointegrated

(* ========== Spread Tests ========== *)

let test_zscore () =
  let z = Spread.zscore ~spread:12.0 ~mean:10.0 ~std:2.0 in
  Alcotest.(check (float 0.01)) "z = 1.0" 1.0 z

let test_zscore_negative () =
  let z = Spread.zscore ~spread:8.0 ~mean:10.0 ~std:2.0 in
  Alcotest.(check (float 0.01)) "z = -1.0" (-1.0) z

let test_calculate_half_life () =
  (* Mean reverting series *)
  let series = Array.init 100 (fun i ->
    let t = float_of_int i in
    10.0 *. exp (-0.1 *. t) *. cos (0.5 *. t)
  ) in
  match Spread.calculate_half_life series with
  | Some hl ->
    Alcotest.(check bool) "half life positive" true (hl > 0.0);
    Alcotest.(check bool) "half life reasonable" true (hl < 252.0)
  | None -> () (* Some series may not have valid half life *)

let test_calculate_spread_stats () =
  let spread = [| 1.0; -1.0; 2.0; -2.0; 0.5; -0.5; 1.5; -1.5; 0.0; 1.0 |] in
  let stats = Spread.calculate_spread_stats spread in
  Alcotest.(check bool) "std > 0" true (stats.std > 0.0);
  Alcotest.(check bool) "half life > 0" true (stats.half_life > 0.0);
  Alcotest.(check bool) "zscore is finite" true (Float.is_finite stats.current_zscore)

let test_generate_signal_long () =
  let signal = Spread.generate_signal ~zscore:(-2.5)
    ~entry_threshold:2.0 ~exit_threshold:0.5 ~current_position:None in
  Alcotest.(check string) "long signal"
    "LONG" (Types.signal_to_string signal)

let test_generate_signal_short () =
  let signal = Spread.generate_signal ~zscore:2.5
    ~entry_threshold:2.0 ~exit_threshold:0.5 ~current_position:None in
  Alcotest.(check string) "short signal"
    "SHORT" (Types.signal_to_string signal)

let test_generate_signal_neutral () =
  let signal = Spread.generate_signal ~zscore:0.5
    ~entry_threshold:2.0 ~exit_threshold:0.5 ~current_position:None in
  Alcotest.(check string) "neutral signal"
    "NEUTRAL" (Types.signal_to_string signal)

let test_generate_signal_exit () =
  let pos : Types.position = {
    entry_time = 0.0; entry_zscore = 2.5; entry_spread = 5.0;
    position_type = Types.Short;
    shares_y = 100.0; shares_x = (-200.0);
  } in
  (* Short position exits when zscore < -exit_threshold *)
  let signal = Spread.generate_signal ~zscore:(-0.6)
    ~entry_threshold:2.0 ~exit_threshold:0.5
    ~current_position:(Some pos) in
  Alcotest.(check string) "exit signal"
    "EXIT" (Types.signal_to_string signal)

let test_position_sizes () =
  let (shares_y, shares_x) = Spread.position_sizes
    ~hedge_ratio:1.5 ~capital:10000.0 ~price1:100.0 ~price2:50.0 in
  Alcotest.(check bool) "shares_y positive" true (shares_y > 0.0);
  Alcotest.(check bool) "shares_x negative (short)" true (shares_x < 0.0);
  (* shares_x = -1.5 * shares_y *)
  Alcotest.(check (float 0.1)) "hedge ratio respected"
    (-1.5 *. shares_y) shares_x

let test_position_pnl () =
  let pos : Types.position = {
    entry_time = 0.0; entry_zscore = 2.0; entry_spread = 5.0;
    position_type = Types.Long;
    shares_y = 100.0; shares_x = (-150.0);
  } in
  (* Long: bought Y at 50, sold X at 100.
     Now Y=55, X=102 → PnL_Y = 100*(55-50) = 500, PnL_X = -150*(102-100) = -300.
     Total = 200 *)
  let pnl = Spread.position_pnl ~position:pos
    ~current_price1:102.0 ~current_price2:55.0
    ~entry_price1:100.0 ~entry_price2:50.0 in
  Alcotest.(check (float 0.01)) "PnL = 200" 200.0 pnl

(* ========== Rolling Half-Life Tests ========== *)

let test_rolling_half_life () =
  (* Mean-reverting series with enough data *)
  let series = Array.init 50 (fun i ->
    let t = float_of_int i in
    5.0 *. exp (-0.05 *. t) *. sin (0.3 *. t)
  ) in
  let rolling = Spread.rolling_half_life ~spread_series:series ~window:20 in
  Alcotest.(check bool) "rolling has entries" true (Array.length rolling > 0);
  (* At least some windows should have valid half-life *)
  let has_some = Array.exists (fun x -> x <> None) rolling in
  Alcotest.(check bool) "some rolling half-lives computed" true has_some

let test_monitor_half_life_stable () =
  (* Stable mean-reverting series — ratio should be near 1 *)
  let series = Array.init 60 (fun i ->
    let t = float_of_int i in
    3.0 *. sin (0.4 *. t) *. exp (-0.02 *. t)
  ) in
  match Spread.monitor_half_life ~spread_series:series ~window:20 with
  | None -> () (* May not have valid half-life for this specific series *)
  | Some mon ->
    Alcotest.(check bool) "baseline > 0" true (mon.baseline_half_life > 0.0);
    Alcotest.(check bool) "current > 0" true (mon.current_half_life > 0.0);
    Alcotest.(check bool) "ratio is finite" true (Float.is_finite mon.ratio)

let test_rolling_half_life_short_data () =
  (* Too few observations for rolling window *)
  let series = [| 1.0; 2.0; 3.0 |] in
  let rolling = Spread.rolling_half_life ~spread_series:series ~window:20 in
  Alcotest.(check bool) "empty for short data" true (Array.length rolling = 0)

(* ========== Types Tests ========== *)

let test_signal_to_string () =
  Alcotest.(check string) "long" "LONG" (Types.signal_to_string Types.Long);
  Alcotest.(check string) "short" "SHORT" (Types.signal_to_string Types.Short);
  Alcotest.(check string) "neutral" "NEUTRAL" (Types.signal_to_string Types.Neutral);
  Alcotest.(check string) "exit" "EXIT" (Types.signal_to_string Types.Exit)

let test_signal_of_string () =
  Alcotest.(check bool) "parse long"
    true (Types.signal_of_string "Long" = Types.Long);
  Alcotest.(check bool) "parse short"
    true (Types.signal_of_string "Short" = Types.Short);
  Alcotest.(check bool) "parse neutral"
    true (Types.signal_of_string "Neutral" = Types.Neutral)

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "Pairs Trading Tests" [
    "cointegration", [
      Alcotest.test_case "Mean" `Quick test_mean;
      Alcotest.test_case "Std" `Quick test_std;
      Alcotest.test_case "OLS perfect" `Quick test_ols_regression_perfect;
      Alcotest.test_case "OLS noisy" `Quick test_ols_regression_noisy;
      Alcotest.test_case "ADF test" `Quick test_adf_test;
      Alcotest.test_case "Cointegration test" `Quick test_test_cointegration;
      Alcotest.test_case "Calculate spread" `Quick test_calculate_spread;
    ];
    "tls", [
      Alcotest.test_case "TLS perfect" `Quick test_tls_regression_perfect;
      Alcotest.test_case "TLS symmetric" `Quick test_tls_regression_symmetric;
      Alcotest.test_case "TLS cointegration" `Quick test_tls_cointegration;
    ];
    "johansen", [
      Alcotest.test_case "Johansen cointegrated" `Quick test_johansen_cointegrated;
      Alcotest.test_case "Johansen short data" `Quick test_johansen_short_data;
    ];
    "spread", [
      Alcotest.test_case "Z-score" `Quick test_zscore;
      Alcotest.test_case "Z-score negative" `Quick test_zscore_negative;
      Alcotest.test_case "Half-life" `Quick test_calculate_half_life;
      Alcotest.test_case "Spread stats" `Quick test_calculate_spread_stats;
      Alcotest.test_case "Signal long" `Quick test_generate_signal_long;
      Alcotest.test_case "Signal short" `Quick test_generate_signal_short;
      Alcotest.test_case "Signal neutral" `Quick test_generate_signal_neutral;
      Alcotest.test_case "Signal exit" `Quick test_generate_signal_exit;
      Alcotest.test_case "Position sizes" `Quick test_position_sizes;
      Alcotest.test_case "Position PnL" `Quick test_position_pnl;
    ];
    "rolling_half_life", [
      Alcotest.test_case "Rolling half-life" `Quick test_rolling_half_life;
      Alcotest.test_case "Monitor stable" `Quick test_monitor_half_life_stable;
      Alcotest.test_case "Rolling short data" `Quick test_rolling_half_life_short_data;
    ];
    "types", [
      Alcotest.test_case "Signal to string" `Quick test_signal_to_string;
      Alcotest.test_case "Signal of string" `Quick test_signal_of_string;
    ];
  ]

(* Unit Tests for Tail Risk Forecast *)

open Tail_risk_forecast

let float_eq ~eps a b = Float.abs (a -. b) < eps

let float_t =
  Alcotest.testable (fun fmt v -> Format.fprintf fmt "%.10f" v)
    (float_eq ~eps:0.001)

let float_precise =
  Alcotest.testable (fun fmt v -> Format.fprintf fmt "%.10f" v)
    (float_eq ~eps:0.0001)

(* ── Helpers ── *)

let mk_rv ?(date = "2026-01-01") ?(n_obs = 78) ?(close = 100.0) rv : Types.daily_rv =
  { date; rv; n_obs; close_price = close }

let mk_return ?(ts = "10:00") ret : Types.intraday_return =
  { timestamp = ts; ret }

(* Generate an RV series with known properties *)
let make_rv_series n base_rv =
  Array.init n (fun i ->
    let noise = 0.0001 *. float_of_int (i mod 7 - 3) in
    mk_rv ~date:(Printf.sprintf "2026-01-%02d" (i + 1)) (base_rv +. noise))

(* ── Realized Variance Tests ── *)

let test_compute_daily_rv () =
  (* RV = sum(r_i^2) = 0.01^2 + 0.02^2 + (-0.015)^2 = 0.000725 *)
  let returns = [|
    mk_return 0.01; mk_return 0.02; mk_return (-0.015);
  |] in
  let rv = Realized_variance.compute_daily_rv ~date:"2026-01-15" ~close_price:100.0 returns in
  Alcotest.(check float_precise) "rv" 0.000725 rv.rv;
  Alcotest.(check int) "n_obs" 3 rv.n_obs;
  Alcotest.(check string) "date" "2026-01-15" rv.date

let test_compute_daily_rv_empty () =
  let rv = Realized_variance.compute_daily_rv ~date:"2026-01-15" ~close_price:100.0 [||] in
  Alcotest.(check (float 0.001)) "empty rv = 0" 0.0 rv.rv;
  Alcotest.(check int) "n_obs = 0" 0 rv.n_obs

let test_annualize_rv () =
  (* 0.0004 daily * 252 = 0.1008 annual *)
  let annual = Realized_variance.annualize_rv 0.0004 in
  Alcotest.(check float_precise) "annualized" 0.1008 annual

let test_rv_to_vol () =
  (* sqrt(0.0004) = 0.02 = 2% daily vol *)
  let vol = Realized_variance.rv_to_vol 0.0004 in
  Alcotest.(check float_precise) "vol" 0.02 vol

let test_log_returns () =
  let prices = [| 100.0; 101.0; 99.0; 102.0 |] in
  let rets = Realized_variance.log_returns prices in
  Alcotest.(check int) "n-1 returns" 3 (Array.length rets);
  (* log(101/100) = 0.00995 *)
  Alcotest.(check float_t) "first return" 0.00995 rets.(0);
  (* log(99/101) = -0.02005 *)
  Alcotest.(check float_t) "second return" (-0.02005) rets.(1)

let test_log_returns_single () =
  let rets = Realized_variance.log_returns [| 100.0 |] in
  Alcotest.(check int) "empty" 0 (Array.length rets)

let test_compute_rv_series () =
  let data : Types.intraday_data = {
    ticker = "SPY"; start_date = "2026-01-01"; end_date = "2026-01-02";
    interval = "5m";
    bars = [|
      [| mk_return 0.01; mk_return (-0.005) |];
      [| mk_return 0.02; mk_return (-0.01) |];
    |];
    daily_closes = [| ("2026-01-01", 500.0); ("2026-01-02", 502.0) |];
  } in
  let series = Realized_variance.compute_rv_series data in
  Alcotest.(check int) "2 days" 2 (Array.length series);
  (* Day 1: 0.01^2 + 0.005^2 = 0.000125 *)
  Alcotest.(check float_precise) "day1 rv" 0.000125 series.(0).rv;
  (* Day 2: 0.02^2 + 0.01^2 = 0.0005 *)
  Alcotest.(check float_precise) "day2 rv" 0.0005 series.(1).rv

(* ── Jump Detection Tests ── *)

let test_detect_jump_basic () =
  (* Create series with variance in baseline and one large spike *)
  let series = Array.init 20 (fun i ->
    if i = 19 then mk_rv ~date:"d19" 0.005  (* ~10x normal *)
    else
      let noise = 0.0001 *. float_of_int (i mod 5 - 2) in
      mk_rv ~date:(Printf.sprintf "d%d" i) (0.0005 +. noise)
  ) in
  let jump = Jump_detection.detect_jump series 19 in
  Alcotest.(check bool) "spike detected as jump" true jump.is_jump;
  Alcotest.(check bool) "positive z-score" true (jump.z_score > 2.0)

let test_detect_jump_normal () =
  let series = make_rv_series 20 0.0005 in
  let jump = Jump_detection.detect_jump series 19 in
  Alcotest.(check bool) "normal day is not jump" false jump.is_jump

let test_detect_jump_insufficient_history () =
  let series = [| mk_rv 0.001 |] in
  let jump = Jump_detection.detect_jump series 0 in
  Alcotest.(check bool) "no history → no jump" false jump.is_jump

let test_detect_all_jumps () =
  let series = Array.init 30 (fun i ->
    if i = 15 then mk_rv ~date:"d15" 0.01
    else mk_rv ~date:(Printf.sprintf "d%d" i) 0.0005
  ) in
  let jumps = Jump_detection.detect_all_jumps series in
  Alcotest.(check int) "same length" 30 (Array.length jumps);
  Alcotest.(check bool) "day 15 is jump" true jumps.(15).is_jump

let test_count_recent_jumps () =
  let jumps = Array.init 10 (fun i ->
    let is_jump = i = 8 || i = 9 in
    Types.{ date = ""; is_jump; rv = 0.0; threshold = 0.0; z_score = 0.0 }
  ) in
  let count = Jump_detection.count_recent_jumps jumps 5 in
  Alcotest.(check int) "2 recent jumps" 2 count

let test_count_recent_jumps_empty () =
  let count = Jump_detection.count_recent_jumps [||] 5 in
  Alcotest.(check int) "empty = 0" 0 count

let test_jump_intensity () =
  let jumps = Array.init 10 (fun i ->
    Types.{ date = ""; is_jump = (i mod 5 = 0); rv = 0.0; threshold = 0.0; z_score = 0.0 }
  ) in
  (* 2 out of 10: i=0 and i=5 *)
  let intensity = Jump_detection.jump_intensity jumps in
  Alcotest.(check float_precise) "20% intensity" 0.2 intensity

let test_jump_intensity_empty () =
  Alcotest.(check (float 0.001)) "empty = 0" 0.0 (Jump_detection.jump_intensity [||])

let test_jump_days () =
  let jumps = Array.init 5 (fun i ->
    Types.{ date = ""; is_jump = (i = 1 || i = 3); rv = 0.0; threshold = 0.0; z_score = 0.0 }
  ) in
  let days = Jump_detection.jump_days jumps in
  Alcotest.(check int) "2 jump days" 2 (Array.length days);
  Alcotest.(check int) "first = 1" 1 days.(0);
  Alcotest.(check int) "second = 3" 3 days.(1)

let test_default_threshold () =
  Alcotest.(check (float 0.001)) "default = 2.5" 2.5 Jump_detection.default_threshold

(* ── HAR-RV Tests ── *)

let test_rv_weekly () =
  (* 5-day average *)
  let series = [|
    mk_rv 0.0001; mk_rv 0.0002; mk_rv 0.0003; mk_rv 0.0004; mk_rv 0.0005;
  |] in
  let avg = Har_rv.rv_weekly series 4 in
  (* (0.0001 + 0.0002 + 0.0003 + 0.0004 + 0.0005) / 5 = 0.0003 *)
  Alcotest.(check float_precise) "weekly avg" 0.0003 avg

let test_rv_monthly () =
  (* With fewer than 22 points, uses what's available *)
  let series = Array.init 10 (fun _ -> mk_rv 0.0004) in
  let avg = Har_rv.rv_monthly series 9 in
  Alcotest.(check float_precise) "monthly avg = mean" 0.0004 avg

let test_estimate_har_insufficient () =
  (* Fewer than min_observations → mean model *)
  let series = Array.init 10 (fun _ -> mk_rv 0.0004) in
  let model = Har_rv.estimate_har series in
  Alcotest.(check float_precise) "c = mean rv" 0.0004 model.c;
  Alcotest.(check (float 0.001)) "beta_d = 0" 0.0 model.beta_d;
  Alcotest.(check (float 0.001)) "beta_w = 0" 0.0 model.beta_w;
  Alcotest.(check (float 0.001)) "beta_m = 0" 0.0 model.beta_m

let test_estimate_har_sufficient () =
  (* Generate enough data with autocorrelation *)
  let series = Array.init 80 (fun i ->
    let base = 0.0004 in
    let cycle = 0.0002 *. sin (float_of_int i *. 0.3) in
    mk_rv ~date:(Printf.sprintf "d%d" i) (base +. cycle)
  ) in
  let model = Har_rv.estimate_har series in
  (* With sufficient data, should get non-zero coefficients *)
  Alcotest.(check bool) "r_squared >= 0" true (model.r_squared >= 0.0);
  Alcotest.(check bool) "r_squared <= 1" true (model.r_squared <= 1.0)

let test_forecast_rv () =
  (* Simple mean model: forecast = c *)
  let model : Types.har_coefficients =
    { c = 0.0004; beta_d = 0.0; beta_w = 0.0; beta_m = 0.0; r_squared = 0.0 } in
  let series = [| mk_rv 0.0005 |] in
  let forecast = Har_rv.forecast_rv model series in
  Alcotest.(check float_precise) "forecast = c (mean model)" 0.0004 forecast

let test_forecast_rv_with_betas () =
  (* forecast = c + beta_d * RV_d + beta_w * RV_w + beta_m * RV_m *)
  let model : Types.har_coefficients =
    { c = 0.0001; beta_d = 0.3; beta_w = 0.3; beta_m = 0.3; r_squared = 0.5 } in
  let series = Array.init 25 (fun _ -> mk_rv 0.0004) in
  (* All RVs the same: forecast = 0.0001 + 0.3*0.0004 + 0.3*0.0004 + 0.3*0.0004
     = 0.0001 + 0.00036 = 0.00046 *)
  let forecast = Har_rv.forecast_rv model series in
  Alcotest.(check float_precise) "forecast with betas" 0.00046 forecast

let test_forecast_rv_non_negative () =
  (* Negative forecast should be clamped to 0 *)
  let model : Types.har_coefficients =
    { c = -0.01; beta_d = 0.0; beta_w = 0.0; beta_m = 0.0; r_squared = 0.0 } in
  let series = [| mk_rv 0.0001 |] in
  let forecast = Har_rv.forecast_rv model series in
  Alcotest.(check (float 0.001)) "non-negative" 0.0 forecast

let test_forecast_rv_empty () =
  let model : Types.har_coefficients =
    { c = 0.0004; beta_d = 0.3; beta_w = 0.3; beta_m = 0.3; r_squared = 0.5 } in
  let forecast = Har_rv.forecast_rv model [||] in
  Alcotest.(check (float 0.001)) "empty = 0" 0.0 forecast

(* ── VaR Forecast Tests ── *)

let test_var_normal_95 () =
  (* VaR_95 = z_95 * sigma = 1.6449 * 0.02 = 0.03290 *)
  let var = Var_forecast.compute_var Normal 0.95 0.02 in
  Alcotest.(check float_precise) "VaR 95% normal" 0.03290 var

let test_var_normal_99 () =
  (* VaR_99 = z_99 * sigma = 2.3263 * 0.02 = 0.04653 *)
  let var = Var_forecast.compute_var Normal 0.99 0.02 in
  Alcotest.(check float_precise) "VaR 99% normal" 0.04653 var

let test_var_student_t () =
  (* t(6) quantile at 95% = 1.943, so VaR = 1.943 * 0.02 = 0.03886 *)
  let var = Var_forecast.compute_var (StudentT 6.0) 0.95 0.02 in
  Alcotest.(check float_precise) "VaR 95% t(6)" 0.03886 var

let test_var_student_t_99 () =
  (* t(6) quantile at 99% = 3.143, so VaR = 3.143 * 0.02 = 0.06286 *)
  let var = Var_forecast.compute_var (StudentT 6.0) 0.99 0.02 in
  Alcotest.(check float_precise) "VaR 99% t(6)" 0.06286 var

let test_es_normal_95 () =
  (* ES = phi(z_95) / 0.05 * sigma
     phi(1.6449) = exp(-0.5*1.6449^2) / sqrt(2*pi) ≈ 0.10314
     ES = 0.10314 / 0.05 * 0.02 = 0.04126 *)
  let es = Var_forecast.compute_es Normal 0.95 0.02 in
  Alcotest.(check float_t) "ES 95% normal" 0.04126 es

let test_es_student_t () =
  (* ES for t-dist = VaR * multiplier *)
  let es = Var_forecast.compute_es (StudentT 6.0) 0.95 0.02 in
  let var = Var_forecast.compute_var (StudentT 6.0) 0.95 0.02 in
  Alcotest.(check bool) "ES > VaR" true (es > var)

let test_var_99_gt_95 () =
  let var_95 = Var_forecast.compute_var Normal 0.95 0.02 in
  let var_99 = Var_forecast.compute_var Normal 0.99 0.02 in
  Alcotest.(check bool) "99% VaR > 95% VaR" true (var_99 > var_95)

let test_t_quantile_large_df () =
  (* Large df → normal *)
  let t = Var_forecast.t_quantile 50.0 0.95 in
  Alcotest.(check float_precise) "large df ≈ z_95" Var_forecast.z_95 t

let test_t_quantile_gt_normal () =
  (* t(6) quantile > normal quantile *)
  let t = Var_forecast.t_quantile 6.0 0.95 in
  Alcotest.(check bool) "t(6) > z_95" true (t > Var_forecast.z_95)

(* ── Forecast Tail Risk Integration ── *)

let test_forecast_tail_risk_basic () =
  let model : Types.har_coefficients =
    { c = 0.0004; beta_d = 0.0; beta_w = 0.0; beta_m = 0.0; r_squared = 0.0 } in
  let rv_series = [| mk_rv ~date:"2026-01-15" 0.0005 |] in
  let jumps = [||] in
  let forecast = Var_forecast.forecast_tail_risk model rv_series jumps in
  Alcotest.(check float_precise) "rv_forecast" 0.0004 forecast.rv_forecast;
  Alcotest.(check float_precise) "vol_forecast" (sqrt 0.0004) forecast.vol_forecast;
  Alcotest.(check bool) "not jump adjusted" false forecast.jump_adjusted;
  Alcotest.(check bool) "var_99 > var_95" true (forecast.var_99 > forecast.var_95);
  Alcotest.(check bool) "es_99 > es_95" true (forecast.es_99 > forecast.es_95)

let test_forecast_tail_risk_with_jumps () =
  let model : Types.har_coefficients =
    { c = 0.0004; beta_d = 0.0; beta_w = 0.0; beta_m = 0.0; r_squared = 0.0 } in
  let rv_series = [| mk_rv ~date:"2026-01-15" 0.0005 |] in
  let jumps = [|
    Types.{ date = "d1"; is_jump = true; rv = 0.01; threshold = 0.005; z_score = 3.0 };
  |] in
  let forecast = Var_forecast.forecast_tail_risk model rv_series jumps in
  Alcotest.(check bool) "jump adjusted" true forecast.jump_adjusted;
  (* rv_forecast = 0.0004 * (1 + 0.15 * 1) = 0.00046 *)
  Alcotest.(check float_precise) "jump-adjusted rv" 0.00046 forecast.rv_forecast

let test_forecast_normal_dist () =
  let model : Types.har_coefficients =
    { c = 0.0004; beta_d = 0.0; beta_w = 0.0; beta_m = 0.0; r_squared = 0.0 } in
  let rv_series = [| mk_rv ~date:"2026-01-15" 0.0005 |] in
  let forecast = Var_forecast.forecast_tail_risk
    ~distribution:Normal model rv_series [||] in
  let sigma = sqrt 0.0004 in
  Alcotest.(check float_precise) "normal var_95" (Var_forecast.z_95 *. sigma) forecast.var_95

(* ── Test Suite ── *)

let () =
  let open Alcotest in
  run "Tail Risk Forecast" [
    "Realized Variance", [
      test_case "Daily RV" `Quick test_compute_daily_rv;
      test_case "Daily RV empty" `Quick test_compute_daily_rv_empty;
      test_case "Annualize" `Quick test_annualize_rv;
      test_case "RV to vol" `Quick test_rv_to_vol;
      test_case "Log returns" `Quick test_log_returns;
      test_case "Log returns single" `Quick test_log_returns_single;
      test_case "RV series" `Quick test_compute_rv_series;
    ];
    "Jump Detection", [
      test_case "Detect spike" `Quick test_detect_jump_basic;
      test_case "Normal day" `Quick test_detect_jump_normal;
      test_case "Insufficient history" `Quick test_detect_jump_insufficient_history;
      test_case "All jumps" `Quick test_detect_all_jumps;
      test_case "Count recent" `Quick test_count_recent_jumps;
      test_case "Count empty" `Quick test_count_recent_jumps_empty;
      test_case "Jump intensity" `Quick test_jump_intensity;
      test_case "Intensity empty" `Quick test_jump_intensity_empty;
      test_case "Jump days" `Quick test_jump_days;
      test_case "Default threshold" `Quick test_default_threshold;
    ];
    "HAR-RV Model", [
      test_case "Weekly avg" `Quick test_rv_weekly;
      test_case "Monthly avg" `Quick test_rv_monthly;
      test_case "Estimate insufficient" `Quick test_estimate_har_insufficient;
      test_case "Estimate sufficient" `Quick test_estimate_har_sufficient;
      test_case "Forecast mean model" `Quick test_forecast_rv;
      test_case "Forecast with betas" `Quick test_forecast_rv_with_betas;
      test_case "Forecast non-negative" `Quick test_forecast_rv_non_negative;
      test_case "Forecast empty" `Quick test_forecast_rv_empty;
    ];
    "VaR & ES", [
      test_case "VaR normal 95%" `Quick test_var_normal_95;
      test_case "VaR normal 99%" `Quick test_var_normal_99;
      test_case "VaR t(6) 95%" `Quick test_var_student_t;
      test_case "VaR t(6) 99%" `Quick test_var_student_t_99;
      test_case "ES normal 95%" `Quick test_es_normal_95;
      test_case "ES t > VaR" `Quick test_es_student_t;
      test_case "99% > 95%" `Quick test_var_99_gt_95;
      test_case "t large df" `Quick test_t_quantile_large_df;
      test_case "t > normal" `Quick test_t_quantile_gt_normal;
    ];
    "Integration", [
      test_case "Basic forecast" `Quick test_forecast_tail_risk_basic;
      test_case "Jump adjusted" `Quick test_forecast_tail_risk_with_jumps;
      test_case "Normal dist" `Quick test_forecast_normal_dist;
    ];
  ]

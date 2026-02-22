(** Unit tests for market regime forecast model *)

open Market_regime_forecast

(* ========== Types Tests ========== *)

let test_string_of_trend_regime () =
  Alcotest.(check string) "bull" "Bull"
    (Types.string_of_trend_regime Types.Bull);
  Alcotest.(check string) "bear" "Bear"
    (Types.string_of_trend_regime Types.Bear);
  Alcotest.(check string) "sideways" "Sideways"
    (Types.string_of_trend_regime Types.Sideways)

let test_string_of_vol_regime () =
  Alcotest.(check string) "high vol" "High Volatility"
    (Types.string_of_vol_regime Types.HighVol);
  Alcotest.(check string) "normal vol" "Normal Volatility"
    (Types.string_of_vol_regime Types.NormalVol);
  Alcotest.(check string) "low vol" "Low Volatility"
    (Types.string_of_vol_regime Types.LowVol)

let test_trend_regime_int_roundtrip () =
  let check_rt regime =
    let i = Types.int_of_trend_regime regime in
    let back = Types.trend_regime_of_int i in
    Alcotest.(check string) "roundtrip"
      (Types.string_of_trend_regime regime)
      (Types.string_of_trend_regime back)
  in
  check_rt Types.Bull;
  check_rt Types.Bear;
  check_rt Types.Sideways

(* ========== GARCH Tests ========== *)

let test_garch_conditional_variances () =
  let params : Types.garch_params = {
    omega = 0.00001; alpha = 0.10; beta = 0.85;
  } in
  let returns = [| 0.01; -0.02; 0.015; -0.005; 0.008; -0.012; 0.003 |] in
  let (residuals, variances) = Garch.conditional_variances ~params ~returns in
  Alcotest.(check int) "residuals length" (Array.length returns) (Array.length residuals);
  Alcotest.(check int) "variances length" (Array.length returns) (Array.length variances);
  Array.iter (fun v ->
    Alcotest.(check bool) "variance positive" true (v > 0.0)
  ) variances

let test_garch_neg_log_likelihood () =
  let params : Types.garch_params = {
    omega = 0.00001; alpha = 0.10; beta = 0.85;
  } in
  let returns = [| 0.01; -0.02; 0.015; -0.005; 0.008; -0.012; 0.003 |] in
  let nll = Garch.neg_log_likelihood ~params ~returns in
  Alcotest.(check bool) "NLL is finite" true (Float.is_finite nll)

let test_garch_forecast_variance () =
  let params : Types.garch_params = {
    omega = 0.00001; alpha = 0.10; beta = 0.85;
  } in
  let forecast = Garch.forecast_variance ~params
    ~last_residual_sq:0.0004 ~last_variance:0.0003 in
  (* omega + alpha * 0.0004 + beta * 0.0003
     = 0.00001 + 0.00004 + 0.000255 = 0.000305 *)
  Alcotest.(check bool) "forecast positive" true (forecast > 0.0);
  Alcotest.(check (float 0.0001)) "forecast value" 0.000305 forecast

let test_garch_persistence () =
  let params : Types.garch_params = {
    omega = 0.00001; alpha = 0.10; beta = 0.85;
  } in
  let persistence = params.alpha +. params.beta in
  Alcotest.(check (float 0.01)) "persistence = 0.95" 0.95 persistence;
  Alcotest.(check bool) "stationary (< 1)" true (persistence < 1.0)

(* ========== HMM Tests ========== *)

let test_hmm_init_params () =
  let returns = Array.init 50 (fun i ->
    if i < 25 then 0.01 +. float_of_int (i mod 5) *. 0.002
    else -0.01 +. float_of_int (i mod 5) *. 0.002
  ) in
  let params = Hmm.init_params ~returns ~n_states:3 in
  Alcotest.(check int) "3 states" 3 params.n_states;
  Alcotest.(check int) "3 means" 3 (Array.length params.emission_means);
  Alcotest.(check int) "3 variances" 3 (Array.length params.emission_vars);
  Alcotest.(check int) "3x3 transition" 3 (Array.length params.transition_matrix);
  Array.iter (fun v ->
    Alcotest.(check bool) "variance positive" true (v > 0.0)
  ) params.emission_vars

let test_hmm_regime_age () =
  (* All same state returns full length *)
  let states = [| 1; 1; 1; 1; 1 |] in
  let age = Hmm.regime_age ~states in
  Alcotest.(check int) "regime age = 5" 5 age

let test_hmm_regime_age_single () =
  let states = [| 2 |] in
  let age = Hmm.regime_age ~states in
  Alcotest.(check int) "single state age = 1" 1 age

let test_hmm_next_state_probs () =
  let params : Types.hmm_params = {
    n_states = 3;
    transition_matrix = [|
      [| 0.9; 0.05; 0.05 |];
      [| 0.05; 0.9; 0.05 |];
      [| 0.05; 0.05; 0.9 |];
    |];
    emission_means = [| 0.001; -0.001; 0.0 |];
    emission_vars = [| 0.0001; 0.0004; 0.0002 |];
    initial_probs = [| 0.33; 0.33; 0.34 |];
  } in
  let current = [| 1.0; 0.0; 0.0 |] in  (* Definitely in state 0 *)
  let next = Hmm.next_state_probs ~params ~current_probs:current in
  Alcotest.(check int) "3 probs" 3 (Array.length next);
  (* Next should be close to row 0 of transition matrix *)
  Alcotest.(check (float 0.01)) "stay in state 0" 0.9 next.(0);
  let sum = Array.fold_left (+.) 0.0 next in
  Alcotest.(check (float 0.01)) "probs sum to 1" 1.0 sum

(* ========== Classifier Tests ========== *)

let test_calc_period_return () =
  let returns = [| 0.01; 0.02; -0.01; 0.015; 0.005 |] in
  let ret = Classifier.calc_period_return ~returns ~days:3 in
  (* Last 3: -0.01, 0.015, 0.005 → cumulative ~= 0.01 *)
  Alcotest.(check bool) "period return is finite" true (Float.is_finite ret)

let test_classify_vol_regime () =
  let config = Types.default_config in
  Alcotest.(check string) "high vol"
    "High Volatility"
    (Types.string_of_vol_regime
      (Classifier.classify_vol_regime ~vol_forecast:0.30 ~vol_percentile:0.90 ~config));
  Alcotest.(check string) "low vol"
    "Low Volatility"
    (Types.string_of_vol_regime
      (Classifier.classify_vol_regime ~vol_forecast:0.10 ~vol_percentile:0.10 ~config));
  Alcotest.(check string) "normal vol"
    "Normal Volatility"
    (Types.string_of_vol_regime
      (Classifier.classify_vol_regime ~vol_forecast:0.18 ~vol_percentile:0.50 ~config))

let test_classify_trend_regime () =
  (* Bull: highest prob is state 0 *)
  let bull_probs = [| 0.8; 0.1; 0.1 |] in
  Alcotest.(check string) "bull"
    "Bull"
    (Types.string_of_trend_regime (Classifier.classify_trend_regime ~trend_probs:bull_probs));
  (* Bear: highest prob is state 1 *)
  let bear_probs = [| 0.1; 0.8; 0.1 |] in
  Alcotest.(check string) "bear"
    "Bear"
    (Types.string_of_trend_regime (Classifier.classify_trend_regime ~trend_probs:bear_probs));
  (* Sideways: highest prob is state 2 *)
  let side_probs = [| 0.1; 0.1; 0.8 |] in
  Alcotest.(check string) "sideways"
    "Sideways"
    (Types.string_of_trend_regime (Classifier.classify_trend_regime ~trend_probs:side_probs))

let test_compute_confidence () =
  (* Normalized: (max - 1/n) / (1 - 1/n). For n=3, uniform=0.333 *)
  let high_conf = [| 0.9; 0.05; 0.05 |] in
  let conf = Classifier.compute_confidence ~probs:high_conf in
  (* (0.9 - 0.333) / (1 - 0.333) = 0.567 / 0.667 = 0.85 *)
  Alcotest.(check (float 0.01)) "high confidence" 0.85 conf;
  let low_conf = [| 0.34; 0.33; 0.33 |] in
  let conf2 = Classifier.compute_confidence ~probs:low_conf in
  (* (0.34 - 0.333) / (1 - 0.333) = 0.007 / 0.667 = 0.01 *)
  Alcotest.(check (float 0.02)) "low confidence" 0.01 conf2

let test_covered_call_suitability () =
  let low_vol_sideways : Types.regime_state = {
    trend = Types.Sideways;
    volatility = Types.LowVol;
    trend_probs = [| 0.1; 0.1; 0.8 |];
    vol_forecast = 0.12;
    vol_percentile = 0.15;
    confidence = 0.8;
    regime_age = 30;
    return_1m = 0.01;
    return_3m = 0.02;
    return_6m = 0.03;
  } in
  let stars = Classifier.covered_call_suitability low_vol_sideways in
  Alcotest.(check bool) "sideways low vol = good for CC" true (stars >= 3)

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "Market Regime Forecast Tests" [
    "types", [
      Alcotest.test_case "Trend regime strings" `Quick test_string_of_trend_regime;
      Alcotest.test_case "Vol regime strings" `Quick test_string_of_vol_regime;
      Alcotest.test_case "Trend regime roundtrip" `Quick test_trend_regime_int_roundtrip;
    ];
    "garch", [
      Alcotest.test_case "Conditional variances" `Quick test_garch_conditional_variances;
      Alcotest.test_case "Neg log likelihood" `Quick test_garch_neg_log_likelihood;
      Alcotest.test_case "Forecast variance" `Quick test_garch_forecast_variance;
      Alcotest.test_case "Persistence" `Quick test_garch_persistence;
    ];
    "hmm", [
      Alcotest.test_case "Init params" `Quick test_hmm_init_params;
      Alcotest.test_case "Regime age" `Quick test_hmm_regime_age;
      Alcotest.test_case "Regime age single" `Quick test_hmm_regime_age_single;
      Alcotest.test_case "Next state probs" `Quick test_hmm_next_state_probs;
    ];
    "classifier", [
      Alcotest.test_case "Period return" `Quick test_calc_period_return;
      Alcotest.test_case "Classify vol regime" `Quick test_classify_vol_regime;
      Alcotest.test_case "Classify trend regime" `Quick test_classify_trend_regime;
      Alcotest.test_case "Compute confidence" `Quick test_compute_confidence;
      Alcotest.test_case "Covered call suitability" `Quick test_covered_call_suitability;
    ];
  ]

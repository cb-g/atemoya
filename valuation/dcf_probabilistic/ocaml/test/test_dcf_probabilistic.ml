(** Comprehensive tests for DCF probabilistic valuation model *)

open Dcf_probabilistic

(* ========== Sampling Module Tests ========== *)

let test_mean_calculation () =
  let arr = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let m = Sampling.mean arr in
  Alcotest.(check (float 0.001)) "mean of 1..5 is 3.0"
    3.0 m

let test_std_calculation () =
  (* std([1,2,3,4,5]) = sqrt(2.5) ≈ 1.581 *)
  let arr = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let s = Sampling.std arr in
  Alcotest.(check (float 0.01)) "std of 1..5 is ~1.581"
    1.581 s

let test_clean_array () =
  let arr = [| 1.0; Float.nan; 0.0; 3.0; Float.infinity; 5.0 |] in
  let cleaned = Sampling.clean_array arr in
  (* Should remove NaN, 0.0, infinity, keeping [1.0, 3.0, 5.0] *)
  Alcotest.(check int) "cleaned array has 3 elements"
    3 (Array.length cleaned);
  Alcotest.(check bool) "all elements are finite and non-zero"
    true (Array.for_all (fun x -> Float.is_finite x && x <> 0.0) cleaned)

let test_clamp_within_bounds () =
  let clamped = Sampling.clamp ~value:5.0 ~lower:0.0 ~upper:10.0 in
  Alcotest.(check (float 0.001)) "value within bounds unchanged"
    5.0 clamped

let test_clamp_above_upper () =
  let clamped = Sampling.clamp ~value:15.0 ~lower:0.0 ~upper:10.0 in
  Alcotest.(check (float 0.001)) "value clamped to upper"
    10.0 clamped

let test_clamp_below_lower () =
  let clamped = Sampling.clamp ~value:(-5.0) ~lower:0.0 ~upper:10.0 in
  Alcotest.(check (float 0.001)) "value clamped to lower"
    0.0 clamped

let test_squash_below_threshold () =
  let squashed = Sampling.squash ~value:5.0 ~threshold:10.0 in
  Alcotest.(check (float 0.001)) "value below threshold unchanged"
    5.0 squashed

let test_squash_above_threshold () =
  (* For x >= threshold: returns threshold + log(1 + (x - threshold)) *)
  (* squash(15, 10) = 10 + log(1 + 5) = 10 + log(6) ≈ 10 + 1.792 = 11.792 *)
  let squashed = Sampling.squash ~value:15.0 ~threshold:10.0 in
  Alcotest.(check (float 0.01)) "value above threshold squashed"
    11.792 squashed

let test_scale_beta_sample () =
  (* Beta sample in [0,1], scale to [5, 15] *)
  let scaled = Sampling.scale_beta_sample ~sample:0.5 ~lower:5.0 ~upper:15.0 in
  Alcotest.(check (float 0.001)) "scaled to middle of range"
    10.0 scaled;

  let scaled_min = Sampling.scale_beta_sample ~sample:0.0 ~lower:5.0 ~upper:15.0 in
  Alcotest.(check (float 0.001)) "scaled to lower bound"
    5.0 scaled_min;

  let scaled_max = Sampling.scale_beta_sample ~sample:1.0 ~lower:5.0 ~upper:15.0 in
  Alcotest.(check (float 0.001)) "scaled to upper bound"
    15.0 scaled_max

let test_bayesian_smooth () =
  (* Mix empirical (10.0) with prior (20.0) at weight 0.3 *)
  (* result = 0.7 × 10 + 0.3 × 20 = 7 + 6 = 13 *)
  let smoothed = Sampling.bayesian_smooth
    ~empirical:10.0 ~prior:20.0 ~weight:0.3 in
  Alcotest.(check (float 0.001)) "bayesian smoothing"
    13.0 smoothed

let test_bayesian_smooth_zero_weight () =
  (* weight = 0 should return empirical value *)
  let smoothed = Sampling.bayesian_smooth
    ~empirical:10.0 ~prior:20.0 ~weight:0.0 in
  Alcotest.(check (float 0.001)) "zero weight returns empirical"
    10.0 smoothed

let test_bayesian_smooth_full_weight () =
  (* weight = 1 should return prior value *)
  let smoothed = Sampling.bayesian_smooth
    ~empirical:10.0 ~prior:20.0 ~weight:1.0 in
  Alcotest.(check (float 0.001)) "full weight returns prior"
    20.0 smoothed

let test_standard_normal_properties () =
  (* Run 10,000 samples and verify statistical properties *)
  let samples = Array.init 10000 (fun _ -> Sampling.standard_normal_sample ()) in
  let m = Sampling.mean samples in
  let s = Sampling.std samples in

  (* Mean should be close to 0 (within ±0.1) *)
  Alcotest.(check bool) "standard normal mean ≈ 0"
    true (Float.abs m < 0.1);

  (* Std should be close to 1 (within ±0.1) *)
  Alcotest.(check bool) "standard normal std ≈ 1"
    true (Float.abs (s -. 1.0) < 0.1)

let test_gaussian_sample_properties () =
  (* Sample from N(50, 10) and verify properties *)
  let samples = Array.init 10000 (fun _ ->
    Sampling.gaussian_sample ~mean:50.0 ~std:10.0
  ) in
  let m = Sampling.mean samples in
  let s = Sampling.std samples in

  (* Mean should be close to 50 (within ±0.5) *)
  Alcotest.(check bool) "gaussian mean ≈ 50"
    true (Float.abs (m -. 50.0) < 0.5);

  (* Std should be close to 10 (within ±0.5) *)
  Alcotest.(check bool) "gaussian std ≈ 10"
    true (Float.abs (s -. 10.0) < 0.5)

(* ========== Statistics Module Tests ========== *)

let test_classify_valuation_overvalued () =
  (* mean_ivps = 80, price = 100, tolerance = 0.05 *)
  (* ratio = 80/100 = 0.8, which is < (1 - 0.05) = 0.95 → Overvalued *)
  let classification = Statistics.classify_valuation
    ~mean_ivps:80.0 ~price:100.0 ~tolerance:0.05 in
  Alcotest.(check bool) "classified as overvalued"
    true (classification = Types.Overvalued)

let test_classify_valuation_undervalued () =
  (* mean_ivps = 120, price = 100, tolerance = 0.05 *)
  (* ratio = 120/100 = 1.2, which is > (1 + 0.05) = 1.05 → Undervalued *)
  let classification = Statistics.classify_valuation
    ~mean_ivps:120.0 ~price:100.0 ~tolerance:0.05 in
  Alcotest.(check bool) "classified as undervalued"
    true (classification = Types.Undervalued)

let test_classify_valuation_fair () =
  (* mean_ivps = 102, price = 100, tolerance = 0.05 *)
  (* ratio = 102/100 = 1.02, which is in [0.95, 1.05] → FairlyValued *)
  let classification = Statistics.classify_valuation
    ~mean_ivps:102.0 ~price:100.0 ~tolerance:0.05 in
  Alcotest.(check bool) "classified as fairly valued"
    true (classification = Types.FairlyValued)

let test_generate_signal_strong_buy () =
  (* Both undervalued → StrongBuy *)
  let signal = Statistics.generate_signal
    ~fcfe_class:Types.Undervalued ~fcff_class:Types.Undervalued in
  Alcotest.(check bool) "signal is StrongBuy"
    true (signal = Types.StrongBuy)

let test_generate_signal_avoid () =
  (* Both overvalued → Avoid *)
  let signal = Statistics.generate_signal
    ~fcfe_class:Types.Overvalued ~fcff_class:Types.Overvalued in
  Alcotest.(check bool) "signal is Avoid"
    true (signal = Types.Avoid)

let test_generate_signal_hold () =
  (* Both fairly valued → Hold *)
  let signal = Statistics.generate_signal
    ~fcfe_class:Types.FairlyValued ~fcff_class:Types.FairlyValued in
  Alcotest.(check bool) "signal is Hold"
    true (signal = Types.Hold)

let test_signal_to_string () =
  let s = Statistics.signal_to_string Types.StrongBuy in
  Alcotest.(check string) "StrongBuy converts to string"
    "Strong Buy" s

let test_class_to_string () =
  let c = Statistics.class_to_string Types.Undervalued in
  Alcotest.(check string) "Undervalued converts to string"
    "Undervalued" c

(* ========== Integration Test ========== *)

let test_compute_statistics_basic () =
  (* Test with simple distribution *)
  let simulations = [| 95.0; 100.0; 105.0; 110.0; 115.0 |] in
  let stats = Statistics.compute_statistics simulations in

  Alcotest.(check (float 0.001)) "mean is 105"
    105.0 stats.mean;

  Alcotest.(check (float 0.01)) "std is ~7.91"
    7.91 stats.std;

  Alcotest.(check (float 0.001)) "min is 95"
    95.0 stats.min;

  Alcotest.(check (float 0.001)) "max is 115"
    115.0 stats.max;

  Alcotest.(check (float 0.001)) "p5 is ~95"
    95.0 stats.percentile_5;

  Alcotest.(check (float 0.001)) "p50 (median) is 105"
    105.0 stats.percentile_50;

  Alcotest.(check (float 0.001)) "p95 is 110 (4th of 5 values)"
    110.0 stats.percentile_95

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "DCF Probabilistic Tests" [
    "sampling_utils", [
      Alcotest.test_case "Mean calculation" `Quick test_mean_calculation;
      Alcotest.test_case "Std calculation" `Quick test_std_calculation;
      Alcotest.test_case "Clean array" `Quick test_clean_array;
      Alcotest.test_case "Clamp within bounds" `Quick test_clamp_within_bounds;
      Alcotest.test_case "Clamp above upper" `Quick test_clamp_above_upper;
      Alcotest.test_case "Clamp below lower" `Quick test_clamp_below_lower;
      Alcotest.test_case "Squash below threshold" `Quick test_squash_below_threshold;
      Alcotest.test_case "Squash above threshold" `Quick test_squash_above_threshold;
      Alcotest.test_case "Scale beta sample" `Quick test_scale_beta_sample;
      Alcotest.test_case "Bayesian smooth" `Quick test_bayesian_smooth;
      Alcotest.test_case "Bayesian smooth zero weight" `Quick test_bayesian_smooth_zero_weight;
      Alcotest.test_case "Bayesian smooth full weight" `Quick test_bayesian_smooth_full_weight;
    ];
    "sampling_distributions", [
      Alcotest.test_case "Standard normal properties" `Quick test_standard_normal_properties;
      Alcotest.test_case "Gaussian sample properties" `Quick test_gaussian_sample_properties;
    ];
    "statistics", [
      Alcotest.test_case "Classify overvalued" `Quick test_classify_valuation_overvalued;
      Alcotest.test_case "Classify undervalued" `Quick test_classify_valuation_undervalued;
      Alcotest.test_case "Classify fairly valued" `Quick test_classify_valuation_fair;
      Alcotest.test_case "Generate signal StrongBuy" `Quick test_generate_signal_strong_buy;
      Alcotest.test_case "Generate signal Avoid" `Quick test_generate_signal_avoid;
      Alcotest.test_case "Generate signal Hold" `Quick test_generate_signal_hold;
      Alcotest.test_case "Signal to string" `Quick test_signal_to_string;
      Alcotest.test_case "Class to string" `Quick test_class_to_string;
      Alcotest.test_case "Compute statistics basic" `Quick test_compute_statistics_basic;
    ];
  ]

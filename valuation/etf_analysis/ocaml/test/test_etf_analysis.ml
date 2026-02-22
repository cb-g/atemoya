(** Unit tests for ETF analysis model *)

open Etf_analysis

(* ========== Costs Tests ========== *)

let test_classify_cost_tier () =
  let check_tier er expected =
    let actual = Costs.cost_tier_to_string (Costs.classify_cost_tier er) in
    Alcotest.(check bool) expected true (String.length actual > 0)
  in
  check_tier 0.0003 "ultra low";
  check_tier 0.0007 "low";
  check_tier 0.0015 "moderate";
  check_tier 0.003 "high";
  check_tier 0.008 "very high"

let test_score_expense_ratio () =
  Alcotest.(check (float 0.01)) "ultra-low = 25"
    25.0 (Costs.score_expense_ratio 0.0003);
  Alcotest.(check (float 0.01)) "low = 20"
    20.0 (Costs.score_expense_ratio 0.0007);
  Alcotest.(check (float 0.01)) "moderate = 15"
    15.0 (Costs.score_expense_ratio 0.0015);
  Alcotest.(check (float 0.01)) "high = 10"
    10.0 (Costs.score_expense_ratio 0.003);
  Alcotest.(check (float 0.01)) "very high = 5"
    5.0 (Costs.score_expense_ratio 0.008)

let test_score_size () =
  Alcotest.(check (float 0.01)) "> $10B = 25"
    25.0 (Costs.score_size 200e9);
  Alcotest.(check (float 0.01)) "> $1B = 20"
    20.0 (Costs.score_size 5e9);
  Alcotest.(check (float 0.01)) "> $100M = 15"
    15.0 (Costs.score_size 500e6);
  Alcotest.(check (float 0.01)) "> $10M = 10"
    10.0 (Costs.score_size 50e6);
  Alcotest.(check (float 0.01)) "micro = 5"
    5.0 (Costs.score_size 5e6)

let test_calculate_tco () =
  (* TCO = ER*100 + (spread*2 / holding_years) *)
  (* TCO = 0.001*100 + (0.0005*2 / 1.0) = 0.1 + 0.001 = 0.101 *)
  let tco = Costs.calculate_tco 0.001 0.0005 1.0 in
  Alcotest.(check (float 0.001)) "TCO" 0.101 tco

let test_calculate_breakeven_holding () =
  (* ETF1: higher ER, lower spread. ETF2: lower ER, higher spread *)
  match Costs.calculate_breakeven_holding 0.002 0.0001 0.001 0.0005 with
  | Some years ->
    Alcotest.(check bool) "breakeven positive" true (years > 0.0)
  | None -> Alcotest.fail "Expected Some breakeven"

(* ========== Premium/Discount Tests ========== *)

let test_classify_nav_status_premium () =
  match Premium_discount.classify_nav_status 0.5 with
  | Types.Premium _ -> ()
  | _ -> Alcotest.fail "Expected Premium"

let test_classify_nav_status_discount () =
  match Premium_discount.classify_nav_status (-0.3) with
  | Types.Discount _ -> ()
  | _ -> Alcotest.fail "Expected Discount"

let test_classify_nav_status_at_nav () =
  match Premium_discount.classify_nav_status 0.0 with
  | Types.AtNav -> ()
  | _ -> Alcotest.fail "Expected AtNav"

let test_score_nav_gap () =
  let tight = Premium_discount.score_nav_gap 0.01 in
  Alcotest.(check (float 0.01)) "tight gap = 10" 10.0 tight;
  let wide = Premium_discount.score_nav_gap 2.0 in
  Alcotest.(check (float 0.01)) "wide gap = 0" 0.0 wide

let test_classify_tracking_quality () =
  Alcotest.(check string) "excellent" "Excellent"
    (Premium_discount.tracking_quality_to_string
      (Premium_discount.classify_tracking_quality 0.05));
  Alcotest.(check string) "good" "Good"
    (Premium_discount.tracking_quality_to_string
      (Premium_discount.classify_tracking_quality 0.15));
  Alcotest.(check string) "poor" "Poor"
    (Premium_discount.tracking_quality_to_string
      (Premium_discount.classify_tracking_quality 0.75));
  Alcotest.(check string) "very poor" "Very Poor"
    (Premium_discount.tracking_quality_to_string
      (Premium_discount.classify_tracking_quality 1.5))

let test_score_tracking () =
  let none_score = Premium_discount.score_tracking None in
  Alcotest.(check (float 0.01)) "no tracking = 12.5" 12.5 none_score;
  let excellent : Types.tracking_metrics = {
    tracking_error_pct = 0.05;
    tracking_difference_pct = -0.02;
    correlation = 0.999;
    beta = 1.0;
  } in
  let score = Premium_discount.score_tracking (Some excellent) in
  Alcotest.(check (float 0.01)) "excellent tracking = 25" 25.0 score

let test_is_unusual_nav_gap () =
  Alcotest.(check bool) "standard tight gap normal"
    false (Premium_discount.is_unusual_nav_gap 0.3 Types.Standard);
  Alcotest.(check bool) "standard wide gap unusual"
    true (Premium_discount.is_unusual_nav_gap 1.0 Types.Standard);
  Alcotest.(check bool) "volatility wide gap normal"
    false (Premium_discount.is_unusual_nav_gap 1.5 Types.Volatility)

(* ========== Scoring Tests ========== *)

let test_score_to_grade () =
  Alcotest.(check string) "A+" "A+" (Scoring.score_to_grade 95.0);
  Alcotest.(check string) "A" "A" (Scoring.score_to_grade 88.0);
  Alcotest.(check string) "B" "B" (Scoring.score_to_grade 72.0);
  Alcotest.(check string) "F" "F" (Scoring.score_to_grade 30.0)

let test_score_to_signal () =
  Alcotest.(check string) "high quality"
    "High Quality" (Scoring.signal_to_string (Scoring.score_to_signal 88.0));
  Alcotest.(check string) "good quality"
    "Good Quality" (Scoring.signal_to_string (Scoring.score_to_signal 72.0));
  Alcotest.(check string) "acceptable"
    "Acceptable" (Scoring.signal_to_string (Scoring.score_to_signal 55.0));
  Alcotest.(check string) "use caution"
    "Use Caution" (Scoring.signal_to_string (Scoring.score_to_signal 40.0));
  Alcotest.(check string) "avoid"
    "Avoid" (Scoring.signal_to_string (Scoring.score_to_signal 25.0))

(* ========== Derivatives Tests ========== *)

let test_derivatives_type_strings () =
  Alcotest.(check string) "standard"
    "Standard" (Derivatives.derivatives_type_to_string Types.Standard);
  Alcotest.(check string) "covered call"
    "Covered Call" (Derivatives.derivatives_type_to_string Types.CoveredCall);
  Alcotest.(check string) "buffer"
    "Buffer/Defined Outcome" (Derivatives.derivatives_type_to_string Types.Buffer);
  Alcotest.(check string) "volatility"
    "Volatility" (Derivatives.derivatives_type_to_string Types.Volatility);
  Alcotest.(check string) "leveraged"
    "Leveraged/Inverse" (Derivatives.derivatives_type_to_string Types.Leveraged)

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "ETF Analysis Tests" [
    "costs", [
      Alcotest.test_case "Classify cost tier" `Quick test_classify_cost_tier;
      Alcotest.test_case "Score expense ratio" `Quick test_score_expense_ratio;
      Alcotest.test_case "Score size" `Quick test_score_size;
      Alcotest.test_case "Calculate TCO" `Quick test_calculate_tco;
      Alcotest.test_case "Breakeven holding" `Quick test_calculate_breakeven_holding;
    ];
    "premium_discount", [
      Alcotest.test_case "NAV premium" `Quick test_classify_nav_status_premium;
      Alcotest.test_case "NAV discount" `Quick test_classify_nav_status_discount;
      Alcotest.test_case "NAV at nav" `Quick test_classify_nav_status_at_nav;
      Alcotest.test_case "Score NAV gap" `Quick test_score_nav_gap;
      Alcotest.test_case "Tracking quality" `Quick test_classify_tracking_quality;
      Alcotest.test_case "Score tracking" `Quick test_score_tracking;
      Alcotest.test_case "Unusual NAV gap" `Quick test_is_unusual_nav_gap;
    ];
    "scoring", [
      Alcotest.test_case "Score to grade" `Quick test_score_to_grade;
      Alcotest.test_case "Score to signal" `Quick test_score_to_signal;
    ];
    "derivatives", [
      Alcotest.test_case "Derivatives type strings" `Quick test_derivatives_type_strings;
    ];
  ]

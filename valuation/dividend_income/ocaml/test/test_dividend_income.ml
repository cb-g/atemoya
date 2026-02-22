(** Unit tests for dividend income model *)

open Dividend_income

(* ========== Dividend Metrics Tests ========== *)

let test_classify_yield () =
  Alcotest.(check string) "very high"
    "Very High (>6%)" (Types.string_of_yield_tier (Dividend_metrics.classify_yield 7.0));
  Alcotest.(check string) "high"
    "High (4-6%)" (Types.string_of_yield_tier (Dividend_metrics.classify_yield 5.0));
  Alcotest.(check string) "above avg"
    "Above Average (3-4%)" (Types.string_of_yield_tier (Dividend_metrics.classify_yield 3.5));
  Alcotest.(check string) "average"
    "Average (2-3%)" (Types.string_of_yield_tier (Dividend_metrics.classify_yield 2.5));
  Alcotest.(check string) "below avg"
    "Below Average (1-2%)" (Types.string_of_yield_tier (Dividend_metrics.classify_yield 1.5));
  Alcotest.(check string) "low"
    "Low (<1%)" (Types.string_of_yield_tier (Dividend_metrics.classify_yield 0.5))

let test_assess_payout () =
  Alcotest.(check string) "very safe"
    "Very Safe" (Types.string_of_payout_assessment (Dividend_metrics.assess_payout 0.40));
  Alcotest.(check string) "safe"
    "Safe" (Types.string_of_payout_assessment (Dividend_metrics.assess_payout 0.55));
  Alcotest.(check string) "moderate"
    "Moderate" (Types.string_of_payout_assessment (Dividend_metrics.assess_payout 0.65));
  Alcotest.(check string) "elevated"
    "Elevated" (Types.string_of_payout_assessment (Dividend_metrics.assess_payout 0.85));
  Alcotest.(check string) "unsustainable"
    "Unsustainable" (Types.string_of_payout_assessment (Dividend_metrics.assess_payout 0.95));
  Alcotest.(check string) "from reserves"
    "Paying From Reserves" (Types.string_of_payout_assessment (Dividend_metrics.assess_payout 1.10))

let test_assess_coverage () =
  Alcotest.(check string) "excellent" "Excellent" (Dividend_metrics.assess_coverage 3.5);
  Alcotest.(check string) "strong" "Strong" (Dividend_metrics.assess_coverage 2.5);
  Alcotest.(check string) "adequate" "Adequate" (Dividend_metrics.assess_coverage 1.7);
  Alcotest.(check string) "thin" "Thin" (Dividend_metrics.assess_coverage 1.1);
  Alcotest.(check string) "not covered" "Not Covered" (Dividend_metrics.assess_coverage 0.8)

let test_project_dividends () =
  let projections = Dividend_metrics.project_dividends 4.0 0.05 3 in
  Alcotest.(check int) "3 years projected" 3 (List.length projections);
  let first = List.hd projections in
  Alcotest.(check (float 0.01)) "year 1 = 4.20" 4.20 first

let test_yield_on_cost () =
  (* After 10 years at 5% growth: future_div = 4 * 1.05^10 = 6.52
     YOC = 6.52 / 100 * 100 = 6.52% *)
  let yoc = Dividend_metrics.yield_on_cost 100.0 4.0 0.05 10 in
  Alcotest.(check (float 0.1)) "YOC after 10y" 6.52 yoc

(* ========== DDM Tests ========== *)

let test_gordon_growth () =
  (* D1 = 4.0 * 1.03 = 4.12, Fair = 4.12 / (0.08 - 0.03) = 82.40 *)
  match Ddm.gordon_growth_model 4.0 0.08 0.03 with
  | None -> Alcotest.fail "Expected Some value"
  | Some v -> Alcotest.(check (float 0.1)) "GGM = 82.40" 82.4 v

let test_gordon_growth_invalid () =
  (* r <= g should return None *)
  let result = Ddm.gordon_growth_model 4.0 0.03 0.05 in
  Alcotest.(check bool) "r <= g = None" true (result = None)

let test_gordon_growth_zero_dividend () =
  let result = Ddm.gordon_growth_model 0.0 0.08 0.03 in
  Alcotest.(check bool) "zero div = None" true (result = None)

let test_two_stage_ddm () =
  match Ddm.two_stage_ddm 4.0 0.10 0.08 0.03 5 with
  | None -> Alcotest.fail "Expected Some value"
  | Some v ->
    Alcotest.(check bool) "two-stage positive" true (v > 0.0);
    Alcotest.(check bool) "two-stage > GGM"
      true (v > 4.0 *. 1.03 /. (0.10 -. 0.03))

let test_two_stage_ddm_invalid () =
  let result = Ddm.two_stage_ddm 4.0 0.03 0.08 0.05 5 in
  Alcotest.(check bool) "r <= terminal g = None" true (result = None)

let test_h_model () =
  match Ddm.h_model 4.0 0.10 0.08 0.03 5.0 with
  | None -> Alcotest.fail "Expected Some value"
  | Some v -> Alcotest.(check bool) "H-model positive" true (v > 0.0)

let test_yield_based_value () =
  (* Fair = 4.0 / 0.04 = 100.0 *)
  match Ddm.yield_based_value 4.0 0.04 with
  | None -> Alcotest.fail "Expected Some value"
  | Some v -> Alcotest.(check (float 0.01)) "yield-based = 100" 100.0 v

let test_yield_based_value_invalid () =
  let result = Ddm.yield_based_value 4.0 0.0 in
  Alcotest.(check bool) "zero yield = None" true (result = None)

let test_estimate_required_return () =
  (* r = rf + beta * MRP = 0.04 + 1.2 * 0.05 = 0.10 *)
  let r = Ddm.estimate_required_return 0.04 0.05 1.2 in
  Alcotest.(check (float 0.001)) "CAPM return" 0.10 r

(* ========== Safety Scoring Tests ========== *)

let test_score_payout_ratio () =
  Alcotest.(check (float 0.01)) "< 40% = 25" 25.0 (Safety_scoring.score_payout_ratio 0.35);
  Alcotest.(check (float 0.01)) "< 50% = 22" 22.0 (Safety_scoring.score_payout_ratio 0.45);
  Alcotest.(check (float 0.01)) "< 60% = 18" 18.0 (Safety_scoring.score_payout_ratio 0.55);
  Alcotest.(check (float 0.01)) "> 90% = 0" 0.0 (Safety_scoring.score_payout_ratio 0.95)

let test_score_fcf_coverage () =
  Alcotest.(check (float 0.01)) ">= 3.0 = 25" 25.0 (Safety_scoring.score_fcf_coverage 3.5);
  Alcotest.(check (float 0.01)) ">= 2.0 = 18" 18.0 (Safety_scoring.score_fcf_coverage 2.2);
  Alcotest.(check (float 0.01)) ">= 1.0 = 5" 5.0 (Safety_scoring.score_fcf_coverage 1.05);
  Alcotest.(check (float 0.01)) "<= 0 = 0" 0.0 (Safety_scoring.score_fcf_coverage (-0.5))

let test_score_dividend_streak () =
  Alcotest.(check (float 0.01)) "50+ = 25" 25.0 (Safety_scoring.score_dividend_streak 55);
  Alcotest.(check (float 0.01)) "25+ = 23" 23.0 (Safety_scoring.score_dividend_streak 30);
  Alcotest.(check (float 0.01)) "10+ = 15" 15.0 (Safety_scoring.score_dividend_streak 12);
  Alcotest.(check (float 0.01)) "0 = 0" 0.0 (Safety_scoring.score_dividend_streak 0)

let test_score_balance_sheet () =
  (* D/E 0.2, CR 2.0 → debt_score 10 + liquidity 5 = 15 *)
  let score = Safety_scoring.score_balance_sheet 0.2 2.0 in
  Alcotest.(check (float 0.01)) "strong B/S = 15" 15.0 score;
  (* D/E 1.5, CR 0.8 → debt 0 + liquidity 0 = 0 *)
  let score2 = Safety_scoring.score_balance_sheet 1.5 0.8 in
  Alcotest.(check (float 0.01)) "weak B/S = 0" 0.0 score2

let test_score_stability () =
  (* ROE 20%, margin 20% → 5 + 5 = 10 *)
  let score = Safety_scoring.score_stability 0.20 0.20 in
  Alcotest.(check (float 0.01)) "strong stability = 10" 10.0 score;
  (* ROE 3%, margin 3% → 0 + 0 = 0 *)
  let score2 = Safety_scoring.score_stability 0.03 0.03 in
  Alcotest.(check (float 0.01)) "weak stability = 0" 0.0 score2

let test_score_to_grade () =
  Alcotest.(check string) "A" "A" (Safety_scoring.score_to_grade 90.0);
  Alcotest.(check string) "B" "B" (Safety_scoring.score_to_grade 60.0);
  Alcotest.(check string) "C" "C" (Safety_scoring.score_to_grade 40.0);
  Alcotest.(check string) "F" "F" (Safety_scoring.score_to_grade 15.0)

(* ========== Types Tests ========== *)

let test_dividend_status_strings () =
  Alcotest.(check string) "king"
    "Dividend King" (Types.string_of_dividend_status Types.DividendKing);
  Alcotest.(check string) "aristocrat"
    "Dividend Aristocrat" (Types.string_of_dividend_status Types.DividendAristocrat);
  Alcotest.(check string) "no streak"
    "No Streak" (Types.string_of_dividend_status Types.NoStreak)

let test_dividend_status_of_string () =
  Alcotest.(check bool) "parse king"
    true (Types.dividend_status_of_string "Dividend King" = Types.DividendKing);
  Alcotest.(check bool) "parse unknown"
    true (Types.dividend_status_of_string "Unknown" = Types.NoStreak)

let test_income_signal_strings () =
  Alcotest.(check string) "strong buy"
    "Strong Buy for Income" (Types.string_of_income_signal Types.StrongBuyIncome);
  Alcotest.(check string) "not income"
    "Not an Income Stock" (Types.string_of_income_signal Types.NotIncomeStock)

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "Dividend Income Tests" [
    "dividend_metrics", [
      Alcotest.test_case "Classify yield" `Quick test_classify_yield;
      Alcotest.test_case "Assess payout" `Quick test_assess_payout;
      Alcotest.test_case "Assess coverage" `Quick test_assess_coverage;
      Alcotest.test_case "Project dividends" `Quick test_project_dividends;
      Alcotest.test_case "Yield on cost" `Quick test_yield_on_cost;
    ];
    "ddm", [
      Alcotest.test_case "Gordon Growth Model" `Quick test_gordon_growth;
      Alcotest.test_case "GGM invalid" `Quick test_gordon_growth_invalid;
      Alcotest.test_case "GGM zero dividend" `Quick test_gordon_growth_zero_dividend;
      Alcotest.test_case "Two-stage DDM" `Quick test_two_stage_ddm;
      Alcotest.test_case "Two-stage invalid" `Quick test_two_stage_ddm_invalid;
      Alcotest.test_case "H-Model" `Quick test_h_model;
      Alcotest.test_case "Yield-based value" `Quick test_yield_based_value;
      Alcotest.test_case "Yield-based invalid" `Quick test_yield_based_value_invalid;
      Alcotest.test_case "Estimate required return" `Quick test_estimate_required_return;
    ];
    "safety_scoring", [
      Alcotest.test_case "Score payout ratio" `Quick test_score_payout_ratio;
      Alcotest.test_case "Score FCF coverage" `Quick test_score_fcf_coverage;
      Alcotest.test_case "Score dividend streak" `Quick test_score_dividend_streak;
      Alcotest.test_case "Score balance sheet" `Quick test_score_balance_sheet;
      Alcotest.test_case "Score stability" `Quick test_score_stability;
      Alcotest.test_case "Score to grade" `Quick test_score_to_grade;
    ];
    "types", [
      Alcotest.test_case "Dividend status strings" `Quick test_dividend_status_strings;
      Alcotest.test_case "Dividend status of string" `Quick test_dividend_status_of_string;
      Alcotest.test_case "Income signal strings" `Quick test_income_signal_strings;
    ];
  ]

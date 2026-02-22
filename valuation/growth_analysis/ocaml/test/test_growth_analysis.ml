(** Unit tests for growth analysis model *)

open Growth_analysis

(* ========== Growth Metrics Tests ========== *)

let test_classify_growth_hypergrowth () =
  let tier = Growth_metrics.classify_growth 50.0 in
  Alcotest.(check string) "hypergrowth"
    "Hypergrowth (>40%)" (Types.string_of_growth_tier tier)

let test_classify_growth_high () =
  let tier = Growth_metrics.classify_growth 25.0 in
  Alcotest.(check string) "high growth"
    "High Growth (20-40%)" (Types.string_of_growth_tier tier)

let test_classify_growth_moderate () =
  let tier = Growth_metrics.classify_growth 15.0 in
  Alcotest.(check string) "moderate growth"
    "Moderate Growth (10-20%)" (Types.string_of_growth_tier tier)

let test_classify_growth_slow () =
  let tier = Growth_metrics.classify_growth 7.0 in
  Alcotest.(check string) "slow growth"
    "Slow Growth (5-10%)" (Types.string_of_growth_tier tier)

let test_classify_growth_no () =
  let tier = Growth_metrics.classify_growth 3.0 in
  Alcotest.(check string) "no growth"
    "No Growth (<5%)" (Types.string_of_growth_tier tier)

let test_classify_growth_declining () =
  let tier = Growth_metrics.classify_growth (-5.0) in
  Alcotest.(check string) "declining"
    "Declining" (Types.string_of_growth_tier tier)

let test_classify_rule_of_40_excellent () =
  let tier = Growth_metrics.classify_rule_of_40 45.0 in
  Alcotest.(check string) "excellent"
    "Excellent" (Types.string_of_rule_of_40_tier tier)

let test_classify_rule_of_40_concerning () =
  let tier = Growth_metrics.classify_rule_of_40 15.0 in
  Alcotest.(check string) "concerning"
    "Concerning" (Types.string_of_rule_of_40_tier tier)

let test_calculate_peg_valid () =
  let peg = Growth_metrics.calculate_peg 20.0 15.0 in
  match peg with
  | None -> Alcotest.fail "Expected Some PEG"
  | Some v -> Alcotest.(check (float 0.01)) "PEG = 20/15" 1.33 v

let test_calculate_peg_zero_growth () =
  let peg = Growth_metrics.calculate_peg 20.0 0.0 in
  Alcotest.(check bool) "zero growth returns None" true (peg = None)

let test_calculate_peg_negative_growth () =
  let peg = Growth_metrics.calculate_peg 20.0 (-5.0) in
  Alcotest.(check bool) "negative growth returns None" true (peg = None)

let test_calculate_ev_rev_per_growth () =
  let ratio = Growth_metrics.calculate_ev_rev_per_growth 5.0 20.0 in
  Alcotest.(check (float 0.01)) "EV/Rev per growth" 0.25 ratio

let test_calculate_ev_rev_per_growth_low () =
  let ratio = Growth_metrics.calculate_ev_rev_per_growth 5.0 0.5 in
  Alcotest.(check (float 0.01)) "low growth returns raw multiple" 5.0 ratio

let test_calculate_implied_growth () =
  let g = Growth_metrics.calculate_implied_growth 20.0 in
  match g with
  | None -> Alcotest.fail "Expected Some growth"
  | Some v -> Alcotest.(check (float 0.1)) "implied growth ~5%" 5.0 v

let test_calculate_analyst_upside () =
  let upside = Growth_metrics.calculate_analyst_upside 100.0 120.0 in
  match upside with
  | None -> Alcotest.fail "Expected Some upside"
  | Some v -> Alcotest.(check (float 0.01)) "20% upside" 20.0 v

let test_calculate_operating_leverage () =
  let data : Types.growth_data = {
    ticker = "TEST"; company_name = "Test Corp";
    sector = "Technology"; industry = "Software";
    current_price = 100.0; market_cap = 1e9;
    enterprise_value = 1.1e9; shares_outstanding = 1e7;
    revenue = 5e8; revenue_growth = 0.10;
    revenue_growth_yoy = 0.10; revenue_cagr_3y = 0.08;
    revenue_per_share = 50.0;
    trailing_eps = 8.0; forward_eps = 10.0;
    earnings_growth = 0.20; eps_growth_fwd = 0.25;
    gross_margin = 0.60; operating_margin = 0.20;
    ebitda_margin = 0.30; profit_margin = 0.16; fcf_margin = 0.14;
    ebitda = 1.5e8; free_cashflow = 7e7;
    operating_cashflow = 9e7; fcf_per_share = 7.0;
    ev_revenue = 2.2; ev_ebitda = 7.3;
    trailing_pe = 12.5; forward_pe = 10.0;
    rule_of_40 = 30.0;
    roe = 0.18; roa = 0.10; roic = 0.15; beta = 1.1;
    analyst_target_mean = 120.0; analyst_target_high = 140.0;
    analyst_target_low = 90.0; analyst_recommendation = "Buy";
    num_analysts = 15;
  } in
  let lev = Growth_metrics.calculate_operating_leverage data in
  Alcotest.(check (float 0.01)) "leverage = 2.0" 2.0 lev

(* ========== Scoring Tests ========== *)

let test_score_revenue_growth_high () =
  let score = Scoring.score_revenue_growth 45.0 in
  Alcotest.(check (float 0.01)) ">40% = 25 pts" 25.0 score

let test_score_revenue_growth_moderate () =
  let score = Scoring.score_revenue_growth 15.0 in
  Alcotest.(check (float 0.01)) ">10% = 10 pts" 10.0 score

let test_score_revenue_growth_zero () =
  let score = Scoring.score_revenue_growth (-2.0) in
  Alcotest.(check (float 0.01)) "negative = 0 pts" 0.0 score

let test_score_earnings_growth () =
  Alcotest.(check (float 0.01)) ">50% = 20"
    20.0 (Scoring.score_earnings_growth 55.0);
  Alcotest.(check (float 0.01)) ">20% = 12"
    12.0 (Scoring.score_earnings_growth 25.0);
  Alcotest.(check (float 0.01)) "negative = 0"
    0.0 (Scoring.score_earnings_growth (-5.0))

let test_score_margins () =
  let score = Scoring.score_margins 60.0 20.0 14.0 in
  Alcotest.(check bool) "positive margin score" true (score > 0.0);
  Alcotest.(check bool) "within bounds" true (score <= 20.0)

let test_score_efficiency () =
  let score = Scoring.score_efficiency 45.0 2.0 in
  Alcotest.(check (float 0.01)) "efficiency score" 16.0 score

let test_score_quality () =
  let score = Scoring.score_quality 20.0 15.0 in
  Alcotest.(check bool) "positive quality score" true (score > 0.0);
  Alcotest.(check bool) "within bounds" true (score <= 15.0)

let test_score_to_grade () =
  Alcotest.(check string) "A" "A" (Scoring.score_to_grade 90.0);
  Alcotest.(check string) "B+" "B+" (Scoring.score_to_grade 70.0);
  Alcotest.(check string) "C" "C" (Scoring.score_to_grade 35.0);
  Alcotest.(check string) "F" "F" (Scoring.score_to_grade 10.0)

(* ========== Types Tests ========== *)

let test_growth_tier_strings () =
  Alcotest.(check string) "hypergrowth"
    "Hypergrowth (>40%)" (Types.string_of_growth_tier Types.Hypergrowth);
  Alcotest.(check string) "declining"
    "Declining" (Types.string_of_growth_tier Types.Declining)

let test_growth_signal_strings () =
  Alcotest.(check string) "strong growth"
    "Strong Growth" (Types.string_of_growth_signal Types.StrongGrowth);
  Alcotest.(check string) "not growth stock"
    "Not a Growth Stock" (Types.string_of_growth_signal Types.NotGrowthStock)

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "Growth Analysis Tests" [
    "growth_metrics", [
      Alcotest.test_case "Classify hypergrowth" `Quick test_classify_growth_hypergrowth;
      Alcotest.test_case "Classify high growth" `Quick test_classify_growth_high;
      Alcotest.test_case "Classify moderate growth" `Quick test_classify_growth_moderate;
      Alcotest.test_case "Classify slow growth" `Quick test_classify_growth_slow;
      Alcotest.test_case "Classify no growth" `Quick test_classify_growth_no;
      Alcotest.test_case "Classify declining" `Quick test_classify_growth_declining;
      Alcotest.test_case "Rule of 40 excellent" `Quick test_classify_rule_of_40_excellent;
      Alcotest.test_case "Rule of 40 concerning" `Quick test_classify_rule_of_40_concerning;
      Alcotest.test_case "PEG valid" `Quick test_calculate_peg_valid;
      Alcotest.test_case "PEG zero growth" `Quick test_calculate_peg_zero_growth;
      Alcotest.test_case "PEG negative growth" `Quick test_calculate_peg_negative_growth;
      Alcotest.test_case "EV/Rev per growth" `Quick test_calculate_ev_rev_per_growth;
      Alcotest.test_case "EV/Rev per growth low" `Quick test_calculate_ev_rev_per_growth_low;
      Alcotest.test_case "Implied growth" `Quick test_calculate_implied_growth;
      Alcotest.test_case "Analyst upside" `Quick test_calculate_analyst_upside;
      Alcotest.test_case "Operating leverage" `Quick test_calculate_operating_leverage;
    ];
    "scoring", [
      Alcotest.test_case "Revenue growth high" `Quick test_score_revenue_growth_high;
      Alcotest.test_case "Revenue growth moderate" `Quick test_score_revenue_growth_moderate;
      Alcotest.test_case "Revenue growth zero" `Quick test_score_revenue_growth_zero;
      Alcotest.test_case "Earnings growth" `Quick test_score_earnings_growth;
      Alcotest.test_case "Margins" `Quick test_score_margins;
      Alcotest.test_case "Efficiency" `Quick test_score_efficiency;
      Alcotest.test_case "Quality" `Quick test_score_quality;
      Alcotest.test_case "Score to grade" `Quick test_score_to_grade;
    ];
    "types", [
      Alcotest.test_case "Growth tier strings" `Quick test_growth_tier_strings;
      Alcotest.test_case "Growth signal strings" `Quick test_growth_signal_strings;
    ];
  ]

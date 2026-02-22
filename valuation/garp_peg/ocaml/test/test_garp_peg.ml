(** Unit tests for GARP PEG model *)

open Garp_peg

(* ========== PEG Module Tests ========== *)

let test_calculate_peg_basic () =
  (* PEG = P/E / Growth% = 20 / 15 = 1.33 *)
  match Peg.calculate_peg 20.0 15.0 with
  | None -> Alcotest.fail "Expected Some PEG"
  | Some v -> Alcotest.(check (float 0.01)) "PEG = 1.33" 1.33 v

let test_calculate_peg_zero_growth () =
  let peg = Peg.calculate_peg 20.0 0.0 in
  Alcotest.(check bool) "zero growth = None" true (peg = None)

let test_calculate_peg_negative_growth () =
  let peg = Peg.calculate_peg 20.0 (-5.0) in
  Alcotest.(check bool) "negative growth = None" true (peg = None)

let test_calculate_pegy () =
  (* PEGY = P/E / (Growth + Yield) = 20 / (15 + 3) = 1.11 *)
  match Peg.calculate_pegy 20.0 15.0 3.0 with
  | None -> Alcotest.fail "Expected Some PEGY"
  | Some v -> Alcotest.(check (float 0.01)) "PEGY = 1.11" 1.11 v

let test_calculate_pegy_zero () =
  let pegy = Peg.calculate_pegy 20.0 0.0 0.0 in
  Alcotest.(check bool) "zero total = None" true (pegy = None)

let test_assess_peg () =
  let assess_low = Peg.assess_peg (Some 0.3) in
  Alcotest.(check bool) "low PEG positive" true
    (String.length assess_low > 0);
  let assess_high = Peg.assess_peg (Some 2.5) in
  Alcotest.(check bool) "high PEG assessment" true
    (String.length assess_high > 0);
  let assess_none = Peg.assess_peg None in
  Alcotest.(check bool) "None PEG assessment" true
    (String.length assess_none > 0)

let test_implied_fair_pe () =
  (* Fair P/E = growth rate (PEG = 1.0), so growth 15% → fair P/E = 15 *)
  match Peg.implied_fair_pe 15.0 with
  | None -> Alcotest.fail "Expected Some fair P/E"
  | Some v -> Alcotest.(check (float 0.01)) "fair P/E = 15" 15.0 v

let test_implied_fair_pe_negative () =
  let fair = Peg.implied_fair_pe (-5.0) in
  Alcotest.(check bool) "negative growth = None" true (fair = None)

let test_implied_fair_price () =
  (* Fair price = EPS * fair P/E *)
  match Peg.implied_fair_price 5.0 (Some 15.0) with
  | None -> Alcotest.fail "Expected Some fair price"
  | Some v -> Alcotest.(check (float 0.01)) "fair price = 75" 75.0 v

let test_implied_fair_price_none () =
  let price = Peg.implied_fair_price 5.0 None in
  Alcotest.(check bool) "None fair P/E = None" true (price = None)

let test_calculate_upside_downside () =
  (* upside = (fair - current) / current * 100 = (120 - 100) / 100 * 100 = 20% *)
  match Peg.calculate_upside_downside 100.0 (Some 120.0) with
  | None -> Alcotest.fail "Expected Some upside"
  | Some v -> Alcotest.(check (float 0.01)) "20% upside" 20.0 v

let test_calculate_upside_downside_negative () =
  match Peg.calculate_upside_downside 100.0 (Some 80.0) with
  | None -> Alcotest.fail "Expected Some downside"
  | Some v -> Alcotest.(check (float 0.01)) "-20% downside" (-20.0) v

(* ========== Scoring Module Tests ========== *)

let test_score_peg () =
  Alcotest.(check (float 0.01)) "PEG < 0.5 = 30"
    30.0 (Scoring.score_peg 0.3);
  Alcotest.(check (float 0.01)) "PEG < 1.0 = 25"
    25.0 (Scoring.score_peg 0.8);
  Alcotest.(check (float 0.01)) "PEG < 1.5 = 15"
    15.0 (Scoring.score_peg 1.2);
  Alcotest.(check (float 0.01)) "PEG < 2.0 = 5"
    5.0 (Scoring.score_peg 1.8);
  Alcotest.(check (float 0.01)) "PEG >= 2.0 = 0"
    0.0 (Scoring.score_peg 2.5)

let test_score_growth () =
  Alcotest.(check (float 0.01)) ">25% = 25"
    25.0 (Scoring.score_growth 30.0);
  Alcotest.(check (float 0.01)) ">15% = 20"
    20.0 (Scoring.score_growth 18.0);
  Alcotest.(check (float 0.01)) ">10% = 15"
    15.0 (Scoring.score_growth 12.0);
  Alcotest.(check (float 0.01)) "<=5% = 0"
    0.0 (Scoring.score_growth 3.0)

let test_score_fcf_conversion () =
  Alcotest.(check (float 0.01)) ">1.0 = 20"
    20.0 (Scoring.score_fcf_conversion 1.2);
  Alcotest.(check (float 0.01)) ">0.8 = 15"
    15.0 (Scoring.score_fcf_conversion 0.9);
  Alcotest.(check (float 0.01)) "<=0.0 = 0"
    0.0 (Scoring.score_fcf_conversion (-0.1))

let test_score_balance_sheet () =
  Alcotest.(check (float 0.01)) "D/E < 0.3 = 15"
    15.0 (Scoring.score_balance_sheet 0.2);
  Alcotest.(check (float 0.01)) "D/E < 0.5 = 10"
    10.0 (Scoring.score_balance_sheet 0.4);
  Alcotest.(check (float 0.01)) "D/E >= 1.0 = 0"
    0.0 (Scoring.score_balance_sheet 1.5)

let test_score_roe () =
  (* score_roe takes ratio, multiplies by 100 internally *)
  Alcotest.(check (float 0.01)) "ROE > 20% = 10"
    10.0 (Scoring.score_roe 0.25);
  Alcotest.(check (float 0.01)) "ROE > 15% = 7"
    7.0 (Scoring.score_roe 0.18);
  Alcotest.(check (float 0.01)) "ROE <= 0% = 0"
    0.0 (Scoring.score_roe (-0.05))

let test_score_to_grade () =
  Alcotest.(check string) "A" "A" (Scoring.score_to_grade 85.0);
  Alcotest.(check string) "B" "B" (Scoring.score_to_grade 65.0);
  Alcotest.(check string) "C" "C" (Scoring.score_to_grade 45.0);
  Alcotest.(check string) "D" "D" (Scoring.score_to_grade 25.0);
  Alcotest.(check string) "F" "F" (Scoring.score_to_grade 10.0)

let test_assess_earnings_quality () =
  Alcotest.(check string) "high" "High"
    (Scoring.assess_earnings_quality 1.2);
  Alcotest.(check string) "good" "Good"
    (Scoring.assess_earnings_quality 0.8);
  Alcotest.(check string) "poor" "Poor"
    (Scoring.assess_earnings_quality (-0.1))

let test_assess_balance_sheet () =
  Alcotest.(check string) "strong" "Strong"
    (Scoring.assess_balance_sheet 0.2);
  Alcotest.(check string) "good" "Good"
    (Scoring.assess_balance_sheet 0.4);
  Alcotest.(check string) "poor" "Poor"
    (Scoring.assess_balance_sheet 3.0)

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "GARP PEG Tests" [
    "peg", [
      Alcotest.test_case "Calculate PEG basic" `Quick test_calculate_peg_basic;
      Alcotest.test_case "PEG zero growth" `Quick test_calculate_peg_zero_growth;
      Alcotest.test_case "PEG negative growth" `Quick test_calculate_peg_negative_growth;
      Alcotest.test_case "Calculate PEGY" `Quick test_calculate_pegy;
      Alcotest.test_case "PEGY zero" `Quick test_calculate_pegy_zero;
      Alcotest.test_case "Assess PEG" `Quick test_assess_peg;
      Alcotest.test_case "Implied fair P/E" `Quick test_implied_fair_pe;
      Alcotest.test_case "Implied fair P/E negative" `Quick test_implied_fair_pe_negative;
      Alcotest.test_case "Implied fair price" `Quick test_implied_fair_price;
      Alcotest.test_case "Implied fair price None" `Quick test_implied_fair_price_none;
      Alcotest.test_case "Upside/downside positive" `Quick test_calculate_upside_downside;
      Alcotest.test_case "Upside/downside negative" `Quick test_calculate_upside_downside_negative;
    ];
    "scoring", [
      Alcotest.test_case "Score PEG" `Quick test_score_peg;
      Alcotest.test_case "Score growth" `Quick test_score_growth;
      Alcotest.test_case "Score FCF conversion" `Quick test_score_fcf_conversion;
      Alcotest.test_case "Score balance sheet" `Quick test_score_balance_sheet;
      Alcotest.test_case "Score ROE" `Quick test_score_roe;
      Alcotest.test_case "Score to grade" `Quick test_score_to_grade;
      Alcotest.test_case "Earnings quality" `Quick test_assess_earnings_quality;
      Alcotest.test_case "Balance sheet strength" `Quick test_assess_balance_sheet;
    ];
  ]

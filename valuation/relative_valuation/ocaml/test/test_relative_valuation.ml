(** Unit tests for relative valuation model *)

open Relative_valuation

(* ========== Helper: minimal company_data ========== *)

let make_company
    ?(ticker = "TEST") ?(current_price = 100.0) ?(market_cap = 1e9)
    ?(trailing_pe = 15.0) ?(forward_pe = 13.0) ?(pb_ratio = 3.0) ?(ps_ratio = 2.0)
    ?(p_fcf = 20.0) ?(ev_ebitda = 10.0) ?(ev_ebit = 12.0) ?(ev_revenue = 2.5)
    ?(revenue_growth = 0.10) ?(ebitda_margin = 0.25) ?(roe = 0.15)
    ?(sector = "Technology") ?(industry = "Software") () : Types.company_data =
  {
    ticker; company_name = ticker; current_price; market_cap;
    enterprise_value = market_cap *. 1.1;
    shares_outstanding = market_cap /. current_price;
    trailing_eps = current_price /. trailing_pe;
    forward_eps = current_price /. forward_pe;
    trailing_pe; forward_pe; pb_ratio; ps_ratio; p_fcf;
    book_value = market_cap /. pb_ratio;
    revenue = market_cap /. ps_ratio;
    revenue_per_share = (market_cap /. ps_ratio) /. (market_cap /. current_price);
    free_cashflow = market_cap /. p_fcf;
    fcf_per_share = (market_cap /. p_fcf) /. (market_cap /. current_price);
    ebitda = market_cap *. 1.1 /. ev_ebitda;
    operating_income = market_cap *. 1.1 /. ev_ebit;
    ev_ebitda; ev_ebit; ev_revenue;
    revenue_growth; earnings_growth = 0.12;
    gross_margin = 0.60; operating_margin = 0.20; ebitda_margin;
    profit_margin = 0.15;
    roe; roa = 0.10; roic = 0.12;
    beta = 1.1; dividend_yield = 0.01;
    sector; industry;
  }

(* ========== Multiples Tests ========== *)

let test_calculate_stats_basic () =
  let stats = Multiples.calculate_stats [10.0; 20.0; 30.0; 40.0; 50.0] in
  match stats with
  | None -> Alcotest.fail "Expected Some stats"
  | Some s ->
    Alcotest.(check (float 0.01)) "median" 30.0 s.median;
    Alcotest.(check (float 0.01)) "mean" 30.0 s.mean;
    Alcotest.(check (float 0.01)) "min" 10.0 s.min;
    Alcotest.(check (float 0.01)) "max" 50.0 s.max

let test_calculate_stats_empty () =
  let stats = Multiples.calculate_stats [] in
  Alcotest.(check bool) "empty list returns None" true (stats = None)

let test_calculate_premium () =
  let prem = Multiples.calculate_premium 12.0 10.0 in
  Alcotest.(check (float 0.01)) "20% premium" 20.0 prem

let test_calculate_premium_discount () =
  let prem = Multiples.calculate_premium 7.5 10.0 in
  Alcotest.(check (float 0.01)) "25% discount" (-25.0) prem

let test_calculate_percentile () =
  let stats : Types.peer_stats = {
    median = 15.0; mean = 15.0; min = 10.0; max = 20.0; std_dev = 3.0;
  } in
  let pct = Multiples.calculate_percentile 15.0 stats in
  Alcotest.(check (float 1.0)) "median is ~50th pct" 50.0 pct

let test_calculate_percentile_at_min () =
  let stats : Types.peer_stats = {
    median = 15.0; mean = 15.0; min = 10.0; max = 20.0; std_dev = 3.0;
  } in
  let pct = Multiples.calculate_percentile 10.0 stats in
  Alcotest.(check bool) "min is low percentile" true (pct < 25.0)

(* ========== Peer Selection Tests ========== *)

let test_score_industry_same () =
  let target = make_company ~sector:"Technology" ~industry:"Software" () in
  let peer = make_company ~sector:"Technology" ~industry:"Software" () in
  let score = Peer_selection.score_industry target peer in
  Alcotest.(check (float 0.01)) "same industry = 30" 30.0 score

let test_score_industry_same_sector () =
  let target = make_company ~sector:"Technology" ~industry:"Software" () in
  let peer = make_company ~sector:"Technology" ~industry:"Hardware" () in
  let score = Peer_selection.score_industry target peer in
  Alcotest.(check (float 0.01)) "same sector diff industry = 15" 15.0 score

let test_score_industry_different () =
  let target = make_company ~sector:"Technology" ~industry:"Software" () in
  let peer = make_company ~sector:"Healthcare" ~industry:"Pharma" () in
  let score = Peer_selection.score_industry target peer in
  Alcotest.(check (float 0.01)) "different sector = 0" 0.0 score

let test_score_size_same () =
  let target = make_company ~market_cap:1e9 () in
  let peer = make_company ~market_cap:1e9 () in
  let score = Peer_selection.score_size target peer in
  Alcotest.(check (float 0.01)) "same size = 25" 25.0 score

let test_score_size_very_different () =
  let target = make_company ~market_cap:1e9 () in
  let peer = make_company ~market_cap:100e9 () in
  let score = Peer_selection.score_size target peer in
  Alcotest.(check bool) "very different size = low score" true (score < 10.0)

let test_classify_peer_quality () =
  Alcotest.(check string) "excellent" "Excellent"
    (Peer_selection.classify_peer_quality 85.0);
  Alcotest.(check string) "good" "Good"
    (Peer_selection.classify_peer_quality 70.0);
  Alcotest.(check string) "adequate" "Adequate"
    (Peer_selection.classify_peer_quality 55.0);
  Alcotest.(check string) "marginal" "Marginal"
    (Peer_selection.classify_peer_quality 40.0);
  Alcotest.(check string) "poor" "Poor"
    (Peer_selection.classify_peer_quality 20.0)

(* ========== Scoring Tests ========== *)

let test_determine_assessment () =
  Alcotest.(check string) "very undervalued"
    "Very Undervalued"
    (Types.string_of_relative_assessment
      (Scoring.determine_assessment 85.0));
  Alcotest.(check string) "undervalued"
    "Undervalued"
    (Types.string_of_relative_assessment
      (Scoring.determine_assessment 65.0));
  Alcotest.(check string) "fairly valued"
    "Fairly Valued"
    (Types.string_of_relative_assessment
      (Scoring.determine_assessment 50.0));
  Alcotest.(check string) "overvalued"
    "Overvalued"
    (Types.string_of_relative_assessment
      (Scoring.determine_assessment 35.0));
  Alcotest.(check string) "very overvalued"
    "Very Overvalued"
    (Types.string_of_relative_assessment
      (Scoring.determine_assessment 15.0))

let test_determine_signal_strong_buy () =
  let company = make_company ~revenue_growth:0.15 ~ebitda_margin:0.30 () in
  let signal = Scoring.determine_signal company 85.0 in
  Alcotest.(check string) "strong buy"
    "Strong Buy" (Types.string_of_relative_signal signal)

let test_determine_signal_sell () =
  let company = make_company ~revenue_growth:0.02 ~ebitda_margin:0.10 () in
  let signal = Scoring.determine_signal company 15.0 in
  Alcotest.(check string) "sell"
    "Sell" (Types.string_of_relative_signal signal)

(* ========== Types Tests ========== *)

let test_string_of_assessment () =
  Alcotest.(check string) "VeryUndervalued"
    "Very Undervalued"
    (Types.string_of_relative_assessment Types.VeryUndervalued);
  Alcotest.(check string) "FairlyValued"
    "Fairly Valued"
    (Types.string_of_relative_assessment Types.FairlyValued)

let test_string_of_signal () =
  Alcotest.(check string) "StrongBuy"
    "Strong Buy"
    (Types.string_of_relative_signal Types.StrongBuy);
  Alcotest.(check string) "Hold"
    "Hold"
    (Types.string_of_relative_signal Types.Hold)

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "Relative Valuation Tests" [
    "multiples", [
      Alcotest.test_case "Calculate stats basic" `Quick test_calculate_stats_basic;
      Alcotest.test_case "Calculate stats empty" `Quick test_calculate_stats_empty;
      Alcotest.test_case "Calculate premium" `Quick test_calculate_premium;
      Alcotest.test_case "Calculate discount" `Quick test_calculate_premium_discount;
      Alcotest.test_case "Percentile at median" `Quick test_calculate_percentile;
      Alcotest.test_case "Percentile at min" `Quick test_calculate_percentile_at_min;
    ];
    "peer_selection", [
      Alcotest.test_case "Same industry score" `Quick test_score_industry_same;
      Alcotest.test_case "Same sector score" `Quick test_score_industry_same_sector;
      Alcotest.test_case "Different sector score" `Quick test_score_industry_different;
      Alcotest.test_case "Same size score" `Quick test_score_size_same;
      Alcotest.test_case "Very different size" `Quick test_score_size_very_different;
      Alcotest.test_case "Classify peer quality" `Quick test_classify_peer_quality;
    ];
    "scoring", [
      Alcotest.test_case "Determine assessment" `Quick test_determine_assessment;
      Alcotest.test_case "Signal strong buy" `Quick test_determine_signal_strong_buy;
      Alcotest.test_case "Signal sell" `Quick test_determine_signal_sell;
    ];
    "types", [
      Alcotest.test_case "Assessment to string" `Quick test_string_of_assessment;
      Alcotest.test_case "Signal to string" `Quick test_string_of_signal;
    ];
  ]

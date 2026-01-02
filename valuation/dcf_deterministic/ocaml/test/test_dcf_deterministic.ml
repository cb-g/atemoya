(** Comprehensive tests for DCF deterministic valuation model *)

open Dcf_deterministic

(* ========== Growth Module Tests ========== *)

let test_clamp_growth_rate_within_bounds () =
  let rate, was_clamped = Growth.clamp_growth_rate
    ~rate:0.05 ~lower_bound:0.0 ~upper_bound:0.10 in
  Alcotest.(check bool) "rate within bounds not clamped"
    false was_clamped;
  Alcotest.(check (float 0.001)) "rate unchanged"
    0.05 rate

let test_clamp_growth_rate_above_upper () =
  let rate, was_clamped = Growth.clamp_growth_rate
    ~rate:0.15 ~lower_bound:0.0 ~upper_bound:0.10 in
  Alcotest.(check bool) "rate above upper bound clamped"
    true was_clamped;
  Alcotest.(check (float 0.001)) "rate clamped to upper"
    0.10 rate

let test_clamp_growth_rate_below_lower () =
  let rate, was_clamped = Growth.clamp_growth_rate
    ~rate:(-0.05) ~lower_bound:0.0 ~upper_bound:0.10 in
  Alcotest.(check bool) "rate below lower bound clamped"
    true was_clamped;
  Alcotest.(check (float 0.001)) "rate clamped to lower"
    0.0 rate

let test_calculate_roe () =
  let roe = Growth.calculate_roe
    ~net_income:1000.0 ~book_value_equity:10000.0 in
  Alcotest.(check (float 0.001)) "ROE calculated correctly"
    0.10 roe

let test_calculate_roe_zero_equity () =
  let roe = Growth.calculate_roe
    ~net_income:1000.0 ~book_value_equity:0.0 in
  Alcotest.(check (float 0.001)) "ROE with zero equity is 0.0 (safe default)"
    0.0 roe

let test_calculate_roic () =
  let roic = Growth.calculate_roic
    ~nopat:2000.0 ~invested_capital:20000.0 in
  Alcotest.(check (float 0.001)) "ROIC calculated correctly"
    0.10 roic

let test_calculate_roic_zero_capital () =
  let roic = Growth.calculate_roic
    ~nopat:2000.0 ~invested_capital:0.0 in
  Alcotest.(check (float 0.001)) "ROIC with zero capital is 0.0 (safe default)"
    0.0 roic

(* ========== Capital Structure Module Tests ========== *)

let test_calculate_leveraged_beta_zero_leverage () =
  (* No debt: leveraged beta = unlever beta *)
  let beta_l = Capital_structure.calculate_leveraged_beta
    ~unlevered_beta:1.0 ~tax_rate:0.21 ~debt:0.0 ~equity:10000.0 in
  Alcotest.(check (float 0.001)) "zero leverage beta"
    1.0 beta_l

let test_calculate_leveraged_beta_with_debt () =
  (* Hamada formula: β_L = β_U × [1 + (1 - tax_rate) × (debt / equity)] *)
  (* β_L = 1.0 × [1 + (1 - 0.21) × (5000 / 10000)] *)
  (* β_L = 1.0 × [1 + 0.79 × 0.5] = 1.0 × 1.395 = 1.395 *)
  let beta_l = Capital_structure.calculate_leveraged_beta
    ~unlevered_beta:1.0 ~tax_rate:0.21 ~debt:5000.0 ~equity:10000.0 in
  Alcotest.(check (float 0.001)) "leveraged beta with debt"
    1.395 beta_l

let test_calculate_cost_of_equity () =
  (* CE = RFR + β_L × ERP *)
  (* CE = 0.04 + 1.2 × 0.06 = 0.04 + 0.072 = 0.112 = 11.2% *)
  let ce = Capital_structure.calculate_cost_of_equity
    ~risk_free_rate:0.04 ~leveraged_beta:1.2 ~equity_risk_premium:0.06 in
  Alcotest.(check (float 0.001)) "cost of equity"
    0.112 ce

let test_calculate_cost_of_borrowing () =
  (* CB = interest_expense / total_debt *)
  (* CB = 500 / 10000 = 0.05 = 5% *)
  let cb = Capital_structure.calculate_cost_of_borrowing
    ~interest_expense:500.0 ~total_debt:10000.0 in
  Alcotest.(check (float 0.001)) "cost of borrowing"
    0.05 cb

let test_calculate_cost_of_borrowing_zero_debt () =
  let cb = Capital_structure.calculate_cost_of_borrowing
    ~interest_expense:500.0 ~total_debt:0.0 in
  Alcotest.(check (float 0.001)) "cost of borrowing with zero debt is 0.0 (safe default)"
    0.0 cb

let test_calculate_wacc () =
  (* WACC = (E/(E+D)) × CE + (D/(E+D)) × CB × (1 - tax_rate) *)
  (* E = 10000, D = 5000, CE = 10%, CB = 5%, tax = 21% *)
  (* WACC = (10000/15000) × 0.10 + (5000/15000) × 0.05 × (1 - 0.21) *)
  (* WACC = 0.6667 × 0.10 + 0.3333 × 0.05 × 0.79 *)
  (* WACC = 0.06667 + 0.01317 = 0.07984 ≈ 7.98% *)
  let wacc = Capital_structure.calculate_wacc
    ~equity:10000.0 ~debt:5000.0
    ~cost_of_equity:0.10 ~cost_of_borrowing:0.05
    ~tax_rate:0.21 in
  Alcotest.(check (float 0.001)) "WACC calculation"
    0.07984 wacc

let test_calculate_wacc_no_debt () =
  (* With no debt, WACC = CE *)
  let wacc = Capital_structure.calculate_wacc
    ~equity:10000.0 ~debt:0.0
    ~cost_of_equity:0.10 ~cost_of_borrowing:0.0
    ~tax_rate:0.21 in
  Alcotest.(check (float 0.001)) "WACC with no debt equals CE"
    0.10 wacc

let test_calculate_cost_of_capital_integration () =
  (* Integration test with realistic data *)
  let market_data : Types.market_data = {
    ticker = "AAPL";
    price = 150.0;
    mve = 2_400_000_000_000.0;  (* $2.4T market cap *)
    mvb = 100_000_000_000.0;    (* $100B debt *)
    shares_outstanding = 16_000_000_000.0;
    currency = "USD";
    country = "USA";
    industry = "Technology";
  } in
  let financial_data : Types.financial_data = {
    ebit = 120_000_000_000.0;
    net_income = 90_000_000_000.0;
    interest_expense = 3_000_000_000.0;
    taxes = 20_000_000_000.0;
    capex = 15_000_000_000.0;
    depreciation = 10_000_000_000.0;
    delta_wc = 5_000_000_000.0;
    book_value_equity = 60_000_000_000.0;
    invested_capital = 150_000_000_000.0;
    is_bank = false;
  } in

  let coc = Capital_structure.calculate_cost_of_capital
    ~market_data ~financial_data
    ~unlevered_beta:1.1 ~risk_free_rate:0.04
    ~equity_risk_premium:0.06 ~tax_rate:0.21 in

  (* Verify all components are reasonable *)
  Alcotest.(check bool) "CE is positive and reasonable"
    true (coc.ce > 0.05 && coc.ce < 0.20);
  Alcotest.(check bool) "CB is positive and reasonable"
    true (coc.cb > 0.0 && coc.cb < 0.10);
  Alcotest.(check bool) "WACC is between CE and CB"
    true (coc.wacc > coc.cb && coc.wacc < coc.ce);
  Alcotest.(check bool) "Leveraged beta > unlevered beta (has debt)"
    true (coc.leveraged_beta > 1.1);
  Alcotest.(check (float 0.001)) "RFR stored correctly"
    0.04 coc.risk_free_rate;
  Alcotest.(check (float 0.001)) "ERP stored correctly"
    0.06 coc.equity_risk_premium

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "DCF Deterministic Tests" [
    "growth", [
      Alcotest.test_case "Clamp growth rate within bounds" `Quick test_clamp_growth_rate_within_bounds;
      Alcotest.test_case "Clamp growth rate above upper bound" `Quick test_clamp_growth_rate_above_upper;
      Alcotest.test_case "Clamp growth rate below lower bound" `Quick test_clamp_growth_rate_below_lower;
      Alcotest.test_case "Calculate ROE" `Quick test_calculate_roe;
      Alcotest.test_case "Calculate ROE with zero equity" `Quick test_calculate_roe_zero_equity;
      Alcotest.test_case "Calculate ROIC" `Quick test_calculate_roic;
      Alcotest.test_case "Calculate ROIC with zero capital" `Quick test_calculate_roic_zero_capital;
    ];
    "capital_structure", [
      Alcotest.test_case "Leveraged beta with zero leverage" `Quick test_calculate_leveraged_beta_zero_leverage;
      Alcotest.test_case "Leveraged beta with debt" `Quick test_calculate_leveraged_beta_with_debt;
      Alcotest.test_case "Cost of equity (CAPM)" `Quick test_calculate_cost_of_equity;
      Alcotest.test_case "Cost of borrowing" `Quick test_calculate_cost_of_borrowing;
      Alcotest.test_case "Cost of borrowing with zero debt" `Quick test_calculate_cost_of_borrowing_zero_debt;
      Alcotest.test_case "WACC calculation" `Quick test_calculate_wacc;
      Alcotest.test_case "WACC with no debt" `Quick test_calculate_wacc_no_debt;
      Alcotest.test_case "Cost of capital integration" `Quick test_calculate_cost_of_capital_integration;
    ];
  ]

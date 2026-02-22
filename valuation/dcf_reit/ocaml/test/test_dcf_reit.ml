(** Unit tests for REIT valuation model *)

open Dcf_reit
open Alcotest

(* Test FFO calculations *)
let test_ffo_calculation () =
  let financial : Types.financial_data = {
    revenue = 1_000_000.0;
    net_income = 200_000.0;
    depreciation = 100_000.0;
    amortization = 10_000.0;
    gains_on_sales = 20_000.0;
    impairments = 5_000.0;
    straight_line_rent_adj = 5_000.0;
    stock_compensation = 10_000.0;
    maintenance_capex = 30_000.0;
    development_capex = 100_000.0;
    total_debt = 500_000.0;
    cash = 50_000.0;
    total_assets = 1_500_000.0;
    total_equity = 800_000.0;
    book_value_per_share = 80.0;
    noi = 400_000.0;
    occupancy_rate = 0.95;
    same_store_noi_growth = 0.03;
    weighted_avg_lease_term = 5.0;
    lease_expiration_1yr = 0.10;
    (* mREIT fields - not used for equity REITs *)
    interest_income = 0.0;
    interest_expense = 0.0;
    net_interest_income = 0.0;
    earning_assets = 0.0;
    distributable_earnings = 0.0;
  } in

  (* FFO = NI + D&A + Impairments - Gains
         = 200,000 + 100,000 + 10,000 + 5,000 - 20,000 = 295,000 *)
  let expected_ffo = 295_000.0 in
  let actual_ffo = Ffo.calculate_ffo ~financial in

  check (float 0.01) "FFO calculation" expected_ffo actual_ffo

(* Test AFFO calculations *)
let test_affo_calculation () =
  let financial : Types.financial_data = {
    revenue = 1_000_000.0;
    net_income = 200_000.0;
    depreciation = 100_000.0;
    amortization = 10_000.0;
    gains_on_sales = 20_000.0;
    impairments = 5_000.0;
    straight_line_rent_adj = 5_000.0;
    stock_compensation = 10_000.0;
    maintenance_capex = 30_000.0;
    development_capex = 100_000.0;
    total_debt = 500_000.0;
    cash = 50_000.0;
    total_assets = 1_500_000.0;
    total_equity = 800_000.0;
    book_value_per_share = 80.0;
    noi = 400_000.0;
    occupancy_rate = 0.95;
    same_store_noi_growth = 0.03;
    weighted_avg_lease_term = 5.0;
    lease_expiration_1yr = 0.10;
    interest_income = 0.0;
    interest_expense = 0.0;
    net_interest_income = 0.0;
    earning_assets = 0.0;
    distributable_earnings = 0.0;
  } in

  (* AFFO = FFO - Maint CapEx - SL Rent Adj - Stock Comp
          = 295,000 - 30,000 - 5,000 - 10,000 = 250,000 *)
  let expected_affo = 250_000.0 in
  let actual_affo = Ffo.calculate_affo ~financial in

  check (float 0.01) "AFFO calculation" expected_affo actual_affo

(* Test NAV calculation *)
let test_nav_calculation () =
  let financial : Types.financial_data = {
    revenue = 1_000_000.0;
    net_income = 200_000.0;
    depreciation = 100_000.0;
    amortization = 10_000.0;
    gains_on_sales = 0.0;
    impairments = 0.0;
    straight_line_rent_adj = 0.0;
    stock_compensation = 0.0;
    maintenance_capex = 30_000.0;
    development_capex = 100_000.0;
    total_debt = 500_000.0;
    cash = 50_000.0;
    total_assets = 1_500_000.0;
    total_equity = 800_000.0;
    book_value_per_share = 80.0;
    noi = 400_000.0;
    occupancy_rate = 0.95;
    same_store_noi_growth = 0.03;
    weighted_avg_lease_term = 5.0;
    lease_expiration_1yr = 0.10;
    interest_income = 0.0;
    interest_expense = 0.0;
    net_interest_income = 0.0;
    earning_assets = 0.0;
    distributable_earnings = 0.0;
  } in

  let market : Types.market_data = {
    ticker = "TEST";
    price = 100.0;
    shares_outstanding = 10_000.0;
    market_cap = 1_000_000.0;
    dividend_yield = 0.05;
    dividend_per_share = 5.0;
    currency = "USD";
    sector = Types.Industrial;
    reit_type = Types.EquityREIT;
  } in

  (* Property Value = NOI / Cap Rate = 400,000 / 0.05 = 8,000,000
     NAV = 8,000,000 + 50,000 - 500,000 = 7,550,000
     NAV per share = 7,550,000 / 10,000 = 755 *)
  let nav = Nav.calculate_nav ~financial ~market ~cap_rate:0.05 in
  let expected_nav_ps = 755.0 in

  check (float 0.01) "NAV per share" expected_nav_ps nav.nav_per_share

(* Test Gordon Growth Model *)
let test_gordon_growth () =
  (* P = D1 / (ke - g) = 5.0 / (0.08 - 0.02) = 83.33 *)
  let dividend = 5.0 in
  let cost_of_equity = 0.08 in
  let growth = 0.02 in

  let expected = 5.0 *. (1.0 +. growth) /. (cost_of_equity -. growth) in
  let actual = Ddm.gordon_growth ~dividend ~cost_of_equity ~growth_rate:growth in

  check (float 0.01) "Gordon Growth" expected actual

(* Test quality scoring *)
let test_quality_occupancy () =
  (* 97% occupancy should score 1.0 *)
  let score = Quality.score_occupancy ~occupancy_rate:0.97 in
  check (float 0.01) "Occupancy score 97%" 1.0 score;

  (* 92% occupancy should score 0.8 *)
  let score2 = Quality.score_occupancy ~occupancy_rate:0.92 in
  check (float 0.01) "Occupancy score 92%" 0.8 score2

let () =
  run "DCF REIT Tests" [
    "FFO", [
      test_case "Calculate FFO" `Quick test_ffo_calculation;
      test_case "Calculate AFFO" `Quick test_affo_calculation;
    ];
    "NAV", [
      test_case "Calculate NAV" `Quick test_nav_calculation;
    ];
    "DDM", [
      test_case "Gordon Growth Model" `Quick test_gordon_growth;
    ];
    "Quality", [
      test_case "Occupancy scoring" `Quick test_quality_occupancy;
    ];
  ]

(** Mortgage REIT (mREIT) valuation module

    Mortgage REITs invest in mortgages and mortgage-backed securities,
    NOT physical properties. They earn Net Interest Income (NII) from
    the spread between borrowing costs and yields on mortgage assets.

    Key differences from equity REITs:
    1. No physical properties -> NAV based on earning assets, not NOI/cap rate
    2. FFO/AFFO not meaningful -> use Distributable Earnings (DE)
    3. Price/Book Value is primary metric (vs P/FFO for equity REITs)
    4. Higher leverage (5-10x vs 1-2x for equity REITs)
    5. Interest rate sensitivity is critical risk factor
*)

open Types

(** Calculate mREIT-specific metrics *)
let calculate_mreit_metrics ~(financial : financial_data)
    ~(market : market_data) : mreit_metrics =
  let shares = market.shares_outstanding in

  (* Net Interest Income *)
  let nii = financial.net_interest_income in
  let nii_per_share = if shares > 0.0 then nii /. shares else 0.0 in

  (* Net Interest Margin = NII / Average Earning Assets *)
  let nim =
    if financial.earning_assets > 0.0 then
      nii /. financial.earning_assets
    else 0.0
  in

  (* Book value per share *)
  let bvps = financial.book_value_per_share in

  (* Price to Book ratio *)
  let p_bv = if bvps > 0.0 then market.price /. bvps else 0.0 in

  (* Distributable Earnings *)
  let de = financial.distributable_earnings in
  let de_per_share = if shares > 0.0 then de /. shares else 0.0 in

  (* DE Payout ratio *)
  let annual_dividend = market.dividend_per_share *. shares in
  let de_payout = if de > 0.0 then annual_dividend /. de else 0.0 in

  (* Leverage ratio: Debt / Equity *)
  let leverage =
    if financial.total_equity > 0.0 then
      financial.total_debt /. financial.total_equity
    else 0.0
  in

  (* Interest coverage: NII / Interest Expense *)
  let interest_coverage =
    if financial.interest_expense > 0.0 then
      nii /. financial.interest_expense
    else 0.0
  in

  {
    net_interest_income = nii;
    nii_per_share;
    net_interest_margin = nim;
    book_value_per_share = bvps;
    price_to_book = p_bv;
    distributable_earnings = de;
    de_per_share;
    de_payout_ratio = de_payout;
    leverage_ratio = leverage;
    interest_coverage;
  }

(** mREIT sector benchmarks *)
type mreit_benchmarks = {
  avg_price_to_book : float;
  avg_price_to_de : float;
  avg_nim : float;         (* Net Interest Margin *)
  avg_leverage : float;
}

let default_mreit_benchmarks : mreit_benchmarks = {
  avg_price_to_book = 0.85;  (* mREITs often trade at discount to book *)
  avg_price_to_de = 8.0;     (* P/DE multiple *)
  avg_nim = 0.025;           (* 2.5% NIM is typical *)
  avg_leverage = 6.0;        (* 6x debt/equity is typical *)
}

(** P/Book valuation for mREIT *)
let value_by_price_to_book ~(mreit : mreit_metrics)
    ~(quality_adj : float) : valuation_method =
  let benchmarks = default_mreit_benchmarks in

  (* Adjust target P/BV for quality *)
  let target_p_bv = benchmarks.avg_price_to_book *. (1.0 +. quality_adj) in
  let implied_value = mreit.book_value_per_share *. target_p_bv in

  PriceToBook {
    p_bv = mreit.price_to_book;
    sector_avg = benchmarks.avg_price_to_book;
    implied_value;
  }

(** P/DE valuation for mREIT *)
let value_by_price_to_de ~(mreit : mreit_metrics) ~price
    ~(quality_adj : float) : valuation_method =
  let benchmarks = default_mreit_benchmarks in

  let p_de =
    if mreit.de_per_share > 0.0 then price /. mreit.de_per_share
    else 0.0
  in

  (* Adjust target P/DE for quality *)
  let target_p_de = benchmarks.avg_price_to_de *. (1.0 +. quality_adj) in
  let implied_value = mreit.de_per_share *. target_p_de in

  PriceToDE {
    p_de;
    sector_avg = benchmarks.avg_price_to_de;
    implied_value;
  }

(** Quality scoring for mREITs *)
let score_mreit_balance_sheet ~(mreit : mreit_metrics) : float =
  (* mREITs use much higher leverage than equity REITs, 5-8x is normal *)
  let leverage_score =
    if mreit.leverage_ratio <= 5.0 then 1.0       (* Conservative *)
    else if mreit.leverage_ratio <= 7.0 then 0.8  (* Normal *)
    else if mreit.leverage_ratio <= 9.0 then 0.5  (* Elevated *)
    else 0.2                                      (* High risk *)
  in

  (* Interest coverage *)
  let coverage_score =
    if mreit.interest_coverage >= 2.0 then 1.0
    else if mreit.interest_coverage >= 1.5 then 0.7
    else if mreit.interest_coverage >= 1.2 then 0.4
    else 0.1
  in

  (leverage_score +. coverage_score) /. 2.0

(** Score net interest margin *)
let score_mreit_nim ~(mreit : mreit_metrics) : float =
  let nim = mreit.net_interest_margin in
  if nim >= 0.035 then 1.0        (* >3.5% excellent *)
  else if nim >= 0.025 then 0.8   (* 2.5-3.5% good *)
  else if nim >= 0.015 then 0.5   (* 1.5-2.5% fair *)
  else 0.2                        (* <1.5% weak *)

(** Score book value stability (P/BV indicates market confidence) *)
let score_mreit_book_stability ~(mreit : mreit_metrics) : float =
  let p_bv = mreit.price_to_book in
  (* P/BV close to 1.0 = confidence, deep discount = concern *)
  if p_bv >= 1.0 then 1.0         (* Premium to book *)
  else if p_bv >= 0.90 then 0.9   (* Near book *)
  else if p_bv >= 0.80 then 0.7   (* Small discount *)
  else if p_bv >= 0.65 then 0.4   (* Significant discount *)
  else 0.2                        (* Deep discount = trouble *)

(** DE payout safety score *)
let score_mreit_dividend_safety ~(mreit : mreit_metrics) : float =
  let payout = mreit.de_payout_ratio in
  if payout <= 0.0 then 0.0
  else if payout < 0.80 then 1.0   (* Conservative *)
  else if payout < 0.90 then 0.8   (* Healthy *)
  else if payout < 1.00 then 0.6   (* Tight *)
  else if payout < 1.10 then 0.3   (* At risk *)
  else 0.1                         (* Likely cut *)

(** Calculate mREIT quality metrics *)
let calculate_mreit_quality ~(mreit : mreit_metrics) : quality_metrics =
  let balance_sheet_score = score_mreit_balance_sheet ~mreit in
  let nim_score = score_mreit_nim ~mreit in
  let book_stability_score = score_mreit_book_stability ~mreit in
  let dividend_safety_score = score_mreit_dividend_safety ~mreit in

  (* mREITs don't have occupancy or lease metrics *)
  let occupancy_score = 0.5 in  (* Neutral placeholder *)
  let lease_quality_score = 0.5 in  (* Neutral placeholder *)

  (* Weight: balance sheet and dividend safety most important *)
  let overall_quality =
    (balance_sheet_score *. 0.30)
    +. (nim_score *. 0.20)
    +. (book_stability_score *. 0.15)
    +. (dividend_safety_score *. 0.35)
  in

  {
    occupancy_score;
    lease_quality_score;
    balance_sheet_score;
    growth_score = nim_score;  (* Use NIM as proxy for "growth" *)
    dividend_safety_score;
    overall_quality;
  }

(** Blend mREIT fair value *)
let blend_mreit_fair_value ~p_bv_val ~p_de_val ~ddm_val : float =
  let extract_value = function
    | PriceToBook { implied_value; _ } -> implied_value
    | PriceToDE { implied_value; _ } -> implied_value
    | DividendDiscount { intrinsic_value; _ } -> intrinsic_value
    | _ -> 0.0
  in

  let values = [
    (extract_value p_bv_val, 0.40);   (* 40% P/BV - primary mREIT metric *)
    (extract_value p_de_val, 0.35);   (* 35% P/DE - earnings quality *)
    (extract_value ddm_val, 0.25);    (* 25% DDM - income validation *)
  ] in

  let weighted_sum = List.fold_left (fun acc (v, w) ->
    if v > 0.0 then acc +. (v *. w) else acc
  ) 0.0 values in

  let total_weight = List.fold_left (fun acc (v, w) ->
    if v > 0.0 then acc +. w else acc
  ) 0.0 values in

  if total_weight > 0.0 then weighted_sum /. total_weight else 0.0

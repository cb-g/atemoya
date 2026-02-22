(** Quality metrics for REIT assessment

    Quality factors determine:
    1. NAV premium/discount justification
    2. Appropriate P/FFO multiple
    3. Risk adjustments to cost of capital
    4. Overall investment recommendation
*)

open Types

(** Score occupancy rate (0-1 score) *)
let score_occupancy ~occupancy_rate : float =
  (* >95% excellent, 90-95% good, 85-90% fair, <85% poor *)
  if occupancy_rate >= 0.95 then 1.0
  else if occupancy_rate >= 0.90 then 0.8
  else if occupancy_rate >= 0.85 then 0.6
  else if occupancy_rate >= 0.80 then 0.4
  else 0.2

(** Score lease quality based on WALT and near-term expirations *)
let score_lease_quality ~walt ~lease_exp_1yr : float =
  (* WALT > 7 years is excellent, < 3 years is concerning
     Low near-term expirations reduce re-leasing risk *)
  let walt_score =
    if walt >= 7.0 then 1.0
    else if walt >= 5.0 then 0.8
    else if walt >= 3.0 then 0.6
    else 0.3
  in
  let expiry_score =
    if lease_exp_1yr <= 0.05 then 1.0   (* <5% expiring *)
    else if lease_exp_1yr <= 0.10 then 0.8
    else if lease_exp_1yr <= 0.15 then 0.6
    else 0.3
  in
  (walt_score +. expiry_score) /. 2.0

(** Score balance sheet health *)
let score_balance_sheet ~(financial : financial_data) ~(market : market_data) : float =
  (* Key metrics: Debt/Market Cap, Debt/NOI *)
  let debt_to_cap =
    if market.market_cap > 0.0 then
      financial.total_debt /. (market.market_cap +. financial.total_debt)
    else 1.0
  in
  let debt_to_noi =
    if financial.noi > 0.0 then financial.total_debt /. financial.noi else 10.0
  in

  let leverage_score =
    if debt_to_cap <= 0.30 then 1.0
    else if debt_to_cap <= 0.40 then 0.8
    else if debt_to_cap <= 0.50 then 0.6
    else if debt_to_cap <= 0.60 then 0.4
    else 0.2
  in

  let coverage_score =
    if debt_to_noi <= 5.0 then 1.0
    else if debt_to_noi <= 7.0 then 0.8
    else if debt_to_noi <= 9.0 then 0.5
    else 0.2
  in

  (leverage_score +. coverage_score) /. 2.0

(** Score growth metrics *)
let score_growth ~same_store_noi_growth : float =
  (* Same-store NOI growth is key organic growth indicator *)
  if same_store_noi_growth >= 0.05 then 1.0       (* >5% excellent *)
  else if same_store_noi_growth >= 0.03 then 0.8  (* 3-5% good *)
  else if same_store_noi_growth >= 0.01 then 0.6  (* 1-3% okay *)
  else if same_store_noi_growth >= 0.0 then 0.4   (* flat *)
  else 0.2                                        (* declining *)

(** Calculate all quality metrics *)
let calculate_quality ~(financial : financial_data)
    ~(market : market_data) ~(ffo : ffo_metrics) : quality_metrics =
  let occupancy_score = score_occupancy ~occupancy_rate:financial.occupancy_rate in

  let lease_quality_score = score_lease_quality
    ~walt:financial.weighted_avg_lease_term
    ~lease_exp_1yr:financial.lease_expiration_1yr
  in

  let balance_sheet_score = score_balance_sheet ~financial ~market in
  let growth_score = score_growth ~same_store_noi_growth:financial.same_store_noi_growth in
  let dividend_safety_score = Ffo.dividend_safety_score ~ffo_metrics:ffo in

  (* Weighted average - balance sheet and dividend safety weighted higher *)
  let overall_quality =
    (occupancy_score *. 0.15)
    +. (lease_quality_score *. 0.15)
    +. (balance_sheet_score *. 0.25)
    +. (growth_score *. 0.20)
    +. (dividend_safety_score *. 0.25)
  in

  {
    occupancy_score;
    lease_quality_score;
    balance_sheet_score;
    growth_score;
    dividend_safety_score;
    overall_quality;
  }

(** Quality tier classification *)
type quality_tier = Premium | Quality | Average | BelowAverage | Poor
[@@deriving show]

let classify_quality ~(quality : quality_metrics) : quality_tier =
  if quality.overall_quality >= 0.85 then Premium
  else if quality.overall_quality >= 0.70 then Quality
  else if quality.overall_quality >= 0.55 then Average
  else if quality.overall_quality >= 0.40 then BelowAverage
  else Poor

(** Quality-adjusted multiple premium *)
let quality_multiple_adjustment ~(quality : quality_metrics) : float =
  (* Premium/discount to sector average multiples based on quality *)
  (* Premium: +20%, Quality: +10%, Average: 0%, Below: -10%, Poor: -20% *)
  (quality.overall_quality -. 0.55) *. 0.5

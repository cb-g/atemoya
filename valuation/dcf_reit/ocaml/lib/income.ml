(** Income investor metrics for REITs

    Income investors prioritize yield and dividend sustainability over
    capital appreciation. This module provides metrics relevant to that
    investment style.

    Key differences from value investing:
    - Value investor asks: "Is price < intrinsic value?"
    - Income investor asks: "Is the yield sustainable and attractive?"

    Both can be "right" - a stock can be overvalued AND a good income investment.
    Example: Realty Income (O) may trade at 114% NAV premium (expensive for value)
    but still be attractive for income (5.5% yield, 32yr growth streak, monthly pay).

    Income investors care about:
    1. Current yield relative to risk-free rate and alternatives
    2. Dividend sustainability (coverage ratio, occupancy, lease structure)
    3. Dividend growth track record and potential
    4. Quality of underlying cash flows (triple-net vs gross leases)
    5. Rate environment (declining rates = REITs more attractive)
*)

open Types

(** Quality factors for income assessment *)
type income_quality_factors = {
  occupancy_premium : float;        (* Bonus for high occupancy (0-10) *)
  lease_structure_premium : float;  (* Bonus for triple-net leases (0-10) *)
  dividend_track_record : float;    (* Bonus for long dividend history (0-15) *)
  rate_environment_bonus : float;   (* Bonus when yield spread is attractive (0-10) *)
  monthly_dividend_bonus : float;   (* Bonus for monthly payers (0-5) *)
}
[@@deriving show]

(** Income investor metrics *)
type income_metrics = {
  (* Current yield *)
  dividend_yield : float;           (* Annual dividend / Price *)
  dividend_per_share : float;       (* Annual dividend amount *)

  (* Coverage and sustainability *)
  coverage_ratio : float;           (* Earnings (FFO/DE) / Dividend - >1.0 is safe *)
  coverage_status : string;         (* "Well Covered", "Covered", "At Risk", "Uncovered" *)
  earnings_per_share : float;       (* FFO for equity, DE for mREIT *)

  (* Payout analysis *)
  payout_ratio : float;             (* Dividend / Earnings - <85% is healthy *)
  payout_status : string;           (* "Conservative", "Normal", "Aggressive", "Unsustainable" *)

  (* Yield context *)
  yield_vs_sector : float;          (* Yield premium/discount vs sector average *)
  yield_vs_10yr : float;            (* Spread to 10-year Treasury *)
  yield_percentile : float;         (* Where current yield ranks historically 0-100 *)

  (* Quality factors *)
  quality_factors : income_quality_factors option;

  (* Income score *)
  income_score : float;             (* 0-100 composite score *)
  income_grade : string;            (* A, B, C, D, F *)
  income_recommendation : string;   (* "Strong Income Buy", "Income Buy", etc. *)
}
[@@deriving show]

(** Sector average dividend yields *)
let sector_avg_yields = [
  (Retail, 4.5);
  (Office, 5.0);
  (Industrial, 3.0);
  (Residential, 3.5);
  (Healthcare, 5.5);
  (DataCenter, 2.5);
  (SelfStorage, 3.5);
  (Hotel, 4.0);
  (Specialty, 3.0);
  (Diversified, 4.0);
  (Mortgage, 10.0);
]

let get_sector_avg_yield sector =
  List.assoc_opt sector sector_avg_yields |> Option.value ~default:4.0

(** Calculate coverage status based on coverage ratio *)
let coverage_status_of_ratio ratio =
  if ratio >= 1.3 then "Well Covered"
  else if ratio >= 1.0 then "Covered"
  else if ratio >= 0.8 then "At Risk"
  else "Uncovered"

(** Calculate payout status based on payout ratio *)
let payout_status_of_ratio ratio =
  if ratio <= 0.70 then "Conservative"
  else if ratio <= 0.85 then "Normal"
  else if ratio <= 1.0 then "Aggressive"
  else "Unsustainable"

(** Calculate income grade based on score *)
let grade_of_score score =
  if score >= 80.0 then "A"
  else if score >= 65.0 then "B"
  else if score >= 50.0 then "C"
  else if score >= 35.0 then "D"
  else "F"

(** Calculate income recommendation *)
let recommendation_of_score score coverage_ratio =
  if coverage_ratio < 0.8 then
    "Caution - Dividend at risk"
  else if score >= 75.0 then
    "Strong Income Buy"
  else if score >= 60.0 then
    "Income Buy"
  else if score >= 45.0 then
    "Income Hold"
  else if score >= 30.0 then
    "Income Reduce"
  else
    "Income Avoid"

(** Known dividend aristocrats and their years of consecutive increases *)
let dividend_track_records = [
  ("O", 32);      (* Realty Income - 32 years *)
  ("NNN", 35);    (* National Retail Properties - 35 years *)
  ("FRT", 57);    (* Federal Realty - 57 years *)
  ("SPG", 15);    (* Simon Property Group *)
  ("PSA", 15);    (* Public Storage *)
  ("AVB", 15);    (* AvalonBay *)
  ("EQR", 15);    (* Equity Residential *)
  ("PLD", 12);    (* Prologis *)
  ("EQIX", 10);   (* Equinix *)
  ("AMT", 10);    (* American Tower *)
  ("VICI", 5);    (* VICI - newer but consistent *)
]

(** Get dividend track record years for a ticker *)
let get_track_record ticker =
  List.assoc_opt (String.uppercase_ascii ticker) dividend_track_records
  |> Option.value ~default:0

(** Known monthly dividend payers *)
let monthly_payers = ["O"; "STAG"; "MAIN"; "GAIN"; "GLAD"; "GOOD"; "LTC"; "SLG"]

let is_monthly_payer ticker =
  List.mem (String.uppercase_ascii ticker) monthly_payers

(** Calculate income quality factors *)
let calculate_quality_factors ~ticker ~occupancy_rate ~risk_free_rate ~dividend_yield =
  (* Occupancy premium: 95%+ occupancy is excellent for income reliability *)
  let occupancy_premium =
    if occupancy_rate >= 0.98 then 10.0
    else if occupancy_rate >= 0.96 then 8.0
    else if occupancy_rate >= 0.94 then 6.0
    else if occupancy_rate >= 0.90 then 4.0
    else 0.0
  in

  (* Dividend track record: years of consecutive increases *)
  let years = get_track_record ticker in
  let dividend_track_record =
    if years >= 25 then 15.0       (* Dividend aristocrat *)
    else if years >= 15 then 12.0  (* Strong track record *)
    else if years >= 10 then 9.0   (* Solid history *)
    else if years >= 5 then 6.0    (* Emerging track record *)
    else 0.0
  in

  (* Rate environment bonus: larger spread to risk-free = more attractive *)
  let yield_spread = dividend_yield -. risk_free_rate in
  let rate_environment_bonus =
    if yield_spread >= 0.03 then 10.0      (* 3%+ spread is very attractive *)
    else if yield_spread >= 0.02 then 8.0  (* 2%+ spread *)
    else if yield_spread >= 0.01 then 5.0  (* 1%+ spread *)
    else if yield_spread >= 0.0 then 2.0   (* At least beats risk-free *)
    else 0.0
  in

  (* Monthly dividend bonus *)
  let monthly_dividend_bonus =
    if is_monthly_payer ticker then 5.0 else 0.0
  in

  (* Lease structure premium - triple-net REITs get bonus *)
  (* Triple-net sectors: retail (NNN leases), specialty (gaming, towers) *)
  let lease_structure_premium = 5.0 in  (* Default - could be parameterized *)

  {
    occupancy_premium;
    lease_structure_premium;
    dividend_track_record;
    rate_environment_bonus;
    monthly_dividend_bonus;
  }

(** Calculate income metrics for equity REITs *)
let calculate_equity_reit ~(market : market_data) ~(ffo_metrics : ffo_metrics)
    ~(quality : quality_metrics) ~risk_free_rate =
  (* Convert dividend_yield from decimal to percentage for calculations *)
  let dividend_yield_pct = market.dividend_yield *. 100.0 in
  let dividend_per_share = market.dividend_per_share in
  let earnings_per_share = ffo_metrics.affo_per_share in

  (* Coverage: AFFO / Dividend *)
  let coverage_ratio =
    if dividend_per_share > 0.0 then earnings_per_share /. dividend_per_share
    else 0.0
  in
  let coverage_status = coverage_status_of_ratio coverage_ratio in

  (* Payout: Dividend / AFFO *)
  let payout_ratio = ffo_metrics.affo_payout_ratio in
  let payout_status = payout_status_of_ratio payout_ratio in

  (* Yield context - all in percentage form *)
  let sector_avg = get_sector_avg_yield market.sector in
  let yield_vs_sector = dividend_yield_pct -. sector_avg in
  let yield_vs_10yr = dividend_yield_pct -. (risk_free_rate *. 100.0) in

  (* Yield percentile - simplified: assume 2-8% historical range *)
  let yield_percentile =
    let normalized = (dividend_yield_pct -. 2.0) /. 6.0 in
    Float.max 0.0 (Float.min 100.0 (normalized *. 100.0))
  in

  (* Calculate quality factors *)
  let qf = calculate_quality_factors
    ~ticker:market.ticker
    ~occupancy_rate:quality.occupancy_score  (* Using quality score as proxy *)
    ~risk_free_rate
    ~dividend_yield:market.dividend_yield
  in

  (* Income score calculation - REVISED for income investor perspective *)
  let score = ref 0.0 in

  (* 1. Yield attractiveness (0-25 points) - income investors love yield *)
  score := !score +. (Float.min 25.0 (dividend_yield_pct *. 4.5));

  (* 2. Coverage safety (0-20 points) - must be sustainable *)
  (* Key insight: for income investors, 1.0x coverage is acceptable if quality is high *)
  score := !score +. (
    if coverage_ratio >= 1.3 then 20.0
    else if coverage_ratio >= 1.1 then 18.0
    else if coverage_ratio >= 1.0 then 15.0  (* 1.0x is OK for quality REITs *)
    else if coverage_ratio >= 0.95 then 10.0 (* Slight concern *)
    else if coverage_ratio >= 0.90 then 5.0  (* At risk *)
    else 0.0
  );

  (* 3. Payout ratio (0-10 points) - LESS punitive than before *)
  (* Income investors accept higher payouts if coverage and quality are good *)
  score := !score +. (
    if payout_ratio <= 0.75 then 10.0
    else if payout_ratio <= 0.85 then 8.0
    else if payout_ratio <= 0.95 then 6.0   (* Was 5.0 before - less penalty *)
    else if payout_ratio <= 1.0 then 4.0    (* Tight but acceptable *)
    else 0.0
  );

  (* 4. Yield spread to risk-free (0-10 points) *)
  score := !score +. (Float.max 0.0 (Float.min 10.0 (yield_vs_10yr *. 2.0)));

  (* 5. Quality factors (0-45 points) - THIS IS NEW *)
  score := !score +. qf.occupancy_premium;           (* 0-10 *)
  score := !score +. qf.dividend_track_record;       (* 0-15 *)
  score := !score +. qf.rate_environment_bonus;      (* 0-10 *)
  score := !score +. qf.monthly_dividend_bonus;      (* 0-5 *)
  score := !score +. qf.lease_structure_premium;     (* 0-5 *)

  (* Cap at 100 *)
  let income_score = Float.min 100.0 !score in
  let income_grade = grade_of_score income_score in
  let income_recommendation = recommendation_of_score income_score coverage_ratio in

  {
    dividend_yield = market.dividend_yield;  (* Store as decimal *)
    dividend_per_share;
    coverage_ratio;
    coverage_status;
    earnings_per_share;
    payout_ratio;
    payout_status;
    yield_vs_sector;
    yield_vs_10yr;
    yield_percentile;
    quality_factors = Some qf;
    income_score;
    income_grade;
    income_recommendation;
  }

(** Calculate income metrics for mortgage REITs *)
let calculate_mreit ~(market : market_data) ~(mreit_metrics : mreit_metrics) ~risk_free_rate =
  (* Convert dividend_yield from decimal to percentage for calculations *)
  let dividend_yield_pct = market.dividend_yield *. 100.0 in
  let dividend_per_share = market.dividend_per_share in
  let earnings_per_share = mreit_metrics.de_per_share in

  (* Coverage: DE / Dividend *)
  let coverage_ratio =
    if dividend_per_share > 0.0 then earnings_per_share /. dividend_per_share
    else 0.0
  in
  let coverage_status = coverage_status_of_ratio coverage_ratio in

  (* Payout: Dividend / DE *)
  let payout_ratio = mreit_metrics.de_payout_ratio in
  let payout_status = payout_status_of_ratio payout_ratio in

  (* Yield context - all in percentage form *)
  let sector_avg = get_sector_avg_yield Mortgage in  (* ~10% for mREITs *)
  let yield_vs_sector = dividend_yield_pct -. sector_avg in
  let yield_vs_10yr = dividend_yield_pct -. (risk_free_rate *. 100.0) in

  (* Yield percentile for mREITs - assume 8-14% historical range *)
  let yield_percentile =
    let normalized = (dividend_yield_pct -. 8.0) /. 6.0 in
    Float.max 0.0 (Float.min 100.0 (normalized *. 100.0))
  in

  (* Income score calculation - mREITs have different risk profile *)
  let score = ref 0.0 in

  (* Yield attractiveness (0-25 points) - lower weight for mREITs, yield is "expected" *)
  score := !score +. (Float.min 25.0 (dividend_yield_pct *. 2.5));

  (* Coverage safety (0-35 points) - MORE important for mREITs *)
  score := !score +. (
    if coverage_ratio >= 1.2 then 35.0
    else if coverage_ratio >= 1.1 then 30.0
    else if coverage_ratio >= 1.0 then 25.0
    else if coverage_ratio >= 0.9 then 15.0
    else if coverage_ratio >= 0.8 then 10.0
    else 0.0
  );

  (* Payout conservatism (0-20 points) *)
  score := !score +. (
    if payout_ratio <= 0.80 then 20.0
    else if payout_ratio <= 0.90 then 15.0
    else if payout_ratio <= 1.0 then 10.0
    else if payout_ratio <= 1.1 then 5.0
    else 0.0
  );

  (* Book value discount bonus (0-10 points) - mREIT specific *)
  let p_bv = mreit_metrics.price_to_book in
  score := !score +. (
    if p_bv > 0.0 && p_bv < 0.85 then 10.0      (* Trading at 15%+ discount to book *)
    else if p_bv > 0.0 && p_bv < 0.95 then 7.0  (* Slight discount *)
    else if p_bv > 0.0 && p_bv < 1.05 then 5.0  (* Near book *)
    else 0.0                                     (* Premium to book or invalid *)
  );

  (* Interest coverage bonus (0-10 points) *)
  let int_cov = mreit_metrics.interest_coverage in
  score := !score +. (
    if int_cov >= 2.0 then 10.0
    else if int_cov >= 1.5 then 7.0
    else if int_cov >= 1.2 then 5.0
    else 0.0
  );

  let income_score = Float.min 100.0 !score in
  let income_grade = grade_of_score income_score in
  let income_recommendation = recommendation_of_score income_score coverage_ratio in

  {
    dividend_yield = market.dividend_yield;  (* Store as decimal *)
    dividend_per_share;
    coverage_ratio;
    coverage_status;
    earnings_per_share;
    payout_ratio;
    payout_status;
    yield_vs_sector;
    yield_vs_10yr;
    yield_percentile;
    quality_factors = None;  (* mREITs don't use these factors *)
    income_score;
    income_grade;
    income_recommendation;
  }

(** Format income metrics for display *)
let format_income_metrics m =
  let base = Printf.sprintf
    {|Income Investor View:
  Dividend Yield:     %.2f%%
  Dividend/Share:     $%.2f
  Coverage Ratio:     %.2f (%s)
  Payout Ratio:       %.0f%% (%s)
  Yield vs Sector:    %+.1f%%
  Yield vs 10Y:       %+.1f%%|}
    (m.dividend_yield *. 100.0)
    m.dividend_per_share
    m.coverage_ratio m.coverage_status
    (m.payout_ratio *. 100.0) m.payout_status
    m.yield_vs_sector
    m.yield_vs_10yr
  in
  let quality_section = match m.quality_factors with
    | Some qf ->
        Printf.sprintf {|
  Quality Bonuses:
    - Occupancy:        +%.0f pts
    - Track Record:     +%.0f pts
    - Rate Spread:      +%.0f pts
    - Monthly Div:      +%.0f pts|}
          qf.occupancy_premium
          qf.dividend_track_record
          qf.rate_environment_bonus
          qf.monthly_dividend_bonus
    | None -> ""
  in
  let footer = Printf.sprintf {|
  Income Score:       %.0f/100 (Grade: %s)
  Recommendation:     %s|}
    m.income_score m.income_grade
    m.income_recommendation
  in
  base ^ quality_section ^ footer

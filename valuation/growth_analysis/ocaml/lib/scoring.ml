(** Growth scoring and signal generation *)

open Types

(** Score revenue growth (0-25 points) *)
let score_revenue_growth (growth_pct : float) : float =
  if growth_pct > 40.0 then 25.0
  else if growth_pct > 30.0 then 22.0
  else if growth_pct > 20.0 then 18.0
  else if growth_pct > 15.0 then 14.0
  else if growth_pct > 10.0 then 10.0
  else if growth_pct > 5.0 then 5.0
  else 0.0

(** Score earnings growth (0-20 points) *)
let score_earnings_growth (growth_pct : float) : float =
  if growth_pct > 50.0 then 20.0
  else if growth_pct > 30.0 then 16.0
  else if growth_pct > 20.0 then 12.0
  else if growth_pct > 10.0 then 8.0
  else if growth_pct > 0.0 then 4.0
  else 0.0

(** Score margin quality (0-20 points) *)
let score_margins (gross_margin : float) (operating_margin : float) (fcf_margin : float) : float =
  let gross_score =
    if gross_margin > 60.0 then 7.0
    else if gross_margin > 40.0 then 5.0
    else if gross_margin > 25.0 then 3.0
    else 0.0
  in
  let op_score =
    if operating_margin > 25.0 then 7.0
    else if operating_margin > 15.0 then 5.0
    else if operating_margin > 5.0 then 3.0
    else 0.0
  in
  let fcf_score =
    if fcf_margin > 20.0 then 6.0
    else if fcf_margin > 10.0 then 4.0
    else if fcf_margin > 0.0 then 2.0
    else 0.0
  in
  gross_score +. op_score +. fcf_score

(** Score efficiency - Rule of 40 and operating leverage (0-20 points) *)
let score_efficiency (rule_of_40 : float) (operating_leverage : float) : float =
  let r40_score =
    if rule_of_40 > 50.0 then 12.0
    else if rule_of_40 > 40.0 then 10.0
    else if rule_of_40 > 30.0 then 7.0
    else if rule_of_40 > 20.0 then 4.0
    else 0.0
  in
  let leverage_score =
    if operating_leverage > 2.0 then 8.0
    else if operating_leverage > 1.5 then 6.0
    else if operating_leverage > 1.0 then 4.0
    else if operating_leverage > 0.5 then 2.0
    else 0.0
  in
  r40_score +. leverage_score

(** Score quality - ROE, ROIC (0-15 points) *)
let score_quality (roe : float) (roic : float) : float =
  let roe_score =
    if roe > 25.0 then 8.0
    else if roe > 15.0 then 6.0
    else if roe > 10.0 then 4.0
    else if roe > 0.0 then 2.0
    else 0.0
  in
  let roic_score =
    if roic > 20.0 then 7.0
    else if roic > 12.0 then 5.0
    else if roic > 8.0 then 3.0
    else if roic > 0.0 then 1.0
    else 0.0
  in
  roe_score +. roic_score

(** Convert score to grade *)
let score_to_grade (score : float) : string =
  if score >= 85.0 then "A"
  else if score >= 75.0 then "A-"
  else if score >= 65.0 then "B+"
  else if score >= 55.0 then "B"
  else if score >= 45.0 then "C+"
  else if score >= 35.0 then "C"
  else if score >= 25.0 then "D"
  else "F"

(** Calculate growth score *)
let calculate_growth_score (data : growth_data) (metrics : growth_metrics) (margins : margin_analysis) : growth_score =
  let revenue_growth_score = score_revenue_growth metrics.revenue_growth_pct in
  let earnings_growth_score = score_earnings_growth metrics.earnings_growth_pct in
  let margin_score = score_margins margins.gross_margin_pct margins.operating_margin_pct margins.fcf_margin_pct in
  let efficiency_score = score_efficiency metrics.rule_of_40 margins.operating_leverage in
  let quality_score = score_quality (data.roe *. 100.0) (data.roic *. 100.0) in

  let total = revenue_growth_score +. earnings_growth_score +. margin_score +. efficiency_score +. quality_score in

  {
    total_score = total;
    grade = score_to_grade total;
    revenue_growth_score;
    earnings_growth_score;
    margin_score;
    efficiency_score;
    quality_score;
  }

(** Determine growth signal *)
let determine_signal (metrics : growth_metrics) (margins : margin_analysis) (score : growth_score) : growth_signal =
  (* Not a growth stock if revenue growth < 10% *)
  if metrics.revenue_growth_pct < 10.0 then NotGrowthStock

  (* Strong growth: high score + expanding margins + high growth *)
  else if score.total_score >= 70.0 && margins.margin_trajectory = Expanding && metrics.revenue_growth_pct >= 20.0 then
    StrongGrowth

  (* Growth buy: good score *)
  else if score.total_score >= 55.0 then GrowthBuy

  (* Growth hold: moderate *)
  else if score.total_score >= 40.0 then GrowthHold

  (* Caution: low score or contracting margins *)
  else GrowthCaution

(** Full analysis *)
let analyze (data : growth_data) : growth_result =
  let growth_metrics = Growth_metrics.calculate_growth_metrics data in
  let margin_analysis = Growth_metrics.calculate_margin_analysis data in
  let valuation = Growth_metrics.calculate_growth_valuation data in
  let score = calculate_growth_score data growth_metrics margin_analysis in
  let signal = determine_signal growth_metrics margin_analysis score in

  {
    ticker = data.ticker;
    company_name = data.company_name;
    sector = data.sector;
    current_price = data.current_price;
    growth_metrics;
    margin_analysis;
    valuation;
    score;
    signal;
  }

(** Compare multiple growth stocks *)
let compare (results : growth_result list) : growth_result list =
  List.sort (fun a b -> compare b.score.total_score a.score.total_score) results

(** Dividend metrics calculations *)

open Types

(** Classify dividend yield into tiers *)
let classify_yield (yield_pct : float) : yield_tier =
  if yield_pct > 6.0 then VeryHighYield
  else if yield_pct > 4.0 then HighYield
  else if yield_pct > 3.0 then AboveAverage
  else if yield_pct > 2.0 then Average
  else if yield_pct > 1.0 then BelowAverage
  else LowYield

(** Assess payout ratio sustainability *)
let assess_payout (payout_ratio : float) : payout_assessment =
  if payout_ratio > 1.0 then PayingFromReserves
  else if payout_ratio > 0.90 then Unsustainable
  else if payout_ratio > 0.75 then Elevated
  else if payout_ratio > 0.60 then Moderate
  else if payout_ratio > 0.50 then Safe
  else VerySafe

(** Assess coverage ratio quality *)
let assess_coverage (coverage : float) : string =
  if coverage >= 3.0 then "Excellent"
  else if coverage >= 2.0 then "Strong"
  else if coverage >= 1.5 then "Adequate"
  else if coverage >= 1.0 then "Thin"
  else "Not Covered"

(** Calculate dividend metrics from raw data *)
let calculate_metrics (data : dividend_data) : dividend_metrics =
  let yield_pct = data.dividend_yield *. 100.0 in

  (* Use the worse of the two payout ratios for assessment *)
  let payout_for_assessment =
    max data.payout_ratio_eps data.payout_ratio_fcf
  in

  (* Use the worse coverage for quality assessment *)
  let coverage_for_assessment =
    if data.fcf_coverage > 0.0 then
      min data.eps_coverage data.fcf_coverage
    else
      data.eps_coverage
  in

  {
    yield_pct;
    yield_tier = classify_yield yield_pct;
    annual_dividend = data.dividend_rate;
    payout_ratio_eps = data.payout_ratio_eps;
    payout_ratio_fcf = data.payout_ratio_fcf;
    payout_assessment = assess_payout payout_for_assessment;
    eps_coverage = data.eps_coverage;
    fcf_coverage = data.fcf_coverage;
    coverage_quality = assess_coverage coverage_for_assessment;
  }

(** Calculate growth metrics from raw data *)
let calculate_growth_metrics (data : dividend_data) : growth_metrics =
  let status = dividend_status_of_string data.dividend_status in

  (* Assess Chowder Number *)
  (* For high yield (>3%), Chowder >= 12 is good *)
  (* For low yield (<3%), Chowder >= 15 is good *)
  let yield_pct = data.dividend_yield *. 100.0 in
  let chowder_threshold = if yield_pct >= 3.0 then 12.0 else 15.0 in
  let chowder_assessment =
    if data.chowder_number >= chowder_threshold +. 5.0 then "Excellent"
    else if data.chowder_number >= chowder_threshold then "Good"
    else if data.chowder_number >= chowder_threshold -. 3.0 then "Acceptable"
    else "Below Target"
  in

  {
    dgr_1y = data.dgr_1y;
    dgr_3y = data.dgr_3y;
    dgr_5y = data.dgr_5y;
    dgr_10y = data.dgr_10y;
    consecutive_increases = data.consecutive_increases;
    dividend_status = status;
    chowder_number = data.chowder_number;
    chowder_assessment;
  }

(** Project future dividends based on growth rate *)
let project_dividends (current_dividend : float) (growth_rate : float) (years : int) : float list =
  let rec loop acc n current =
    if n > years then List.rev acc
    else loop (current :: acc) (n + 1) (current *. (1.0 +. growth_rate))
  in
  loop [] 1 (current_dividend *. (1.0 +. growth_rate))

(** Calculate Yield on Cost (YOC) after n years *)
let yield_on_cost (original_price : float) (current_dividend : float) (growth_rate : float) (years : int) : float =
  let future_dividend = current_dividend *. ((1.0 +. growth_rate) ** float_of_int years) in
  future_dividend /. original_price *. 100.0

(** Check if dividend yield is a "yield trap" (unsustainably high) *)
let is_yield_trap (data : dividend_data) : bool * string list =
  let warnings = ref [] in

  (* Very high yield *)
  if data.dividend_yield > 0.08 then
    warnings := "Yield > 8% - often signals trouble" :: !warnings;

  (* Payout ratio too high *)
  if data.payout_ratio_eps > 0.9 then
    warnings := "Payout ratio > 90% - limited sustainability" :: !warnings;

  (* FCF doesn't cover dividend *)
  if data.fcf_coverage > 0.0 && data.fcf_coverage < 1.0 then
    warnings := "FCF doesn't cover dividend" :: !warnings;

  (* Negative EPS *)
  if data.trailing_eps < 0.0 then
    warnings := "Negative EPS - paying from reserves/debt" :: !warnings;

  (* No dividend growth or declining *)
  if data.dgr_5y < 0.0 then
    warnings := "Dividend declining over 5 years" :: !warnings;

  let is_trap = List.length !warnings >= 2 in
  (is_trap, !warnings)

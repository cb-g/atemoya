(** GARP scoring system *)

open Types

(** Calculate PEG score (0-30 points) *)
let score_peg (peg : float) : float =
  if peg <= 0.0 then 0.0  (* Invalid PEG *)
  else if peg < 0.5 then 30.0
  else if peg < 1.0 then 25.0
  else if peg < 1.5 then 15.0
  else if peg < 2.0 then 5.0
  else 0.0


(** Calculate growth score (0-25 points)
    Growth rate is in percentage points *)
let score_growth (growth_pct : float) : float =
  if growth_pct > 25.0 then 25.0
  else if growth_pct > 15.0 then 20.0
  else if growth_pct > 10.0 then 15.0
  else if growth_pct > 5.0 then 10.0
  else 0.0


(** Calculate FCF conversion / earnings quality score (0-20 points) *)
let score_fcf_conversion (fcf_conv : float) : float =
  if fcf_conv > 1.0 then 20.0
  else if fcf_conv > 0.8 then 15.0
  else if fcf_conv > 0.5 then 10.0
  else if fcf_conv > 0.0 then 5.0
  else 0.0


(** Calculate balance sheet score (0-15 points) based on D/E ratio *)
let score_balance_sheet (debt_to_equity : float) : float =
  if debt_to_equity < 0.3 then 15.0
  else if debt_to_equity < 0.5 then 10.0
  else if debt_to_equity < 1.0 then 5.0
  else 0.0


(** Calculate ROE score (0-10 points)
    ROE is as decimal (0.15 = 15%) *)
let score_roe (roe : float) : float =
  let roe_pct = roe *. 100.0 in
  if roe_pct > 20.0 then 10.0
  else if roe_pct > 15.0 then 7.0
  else if roe_pct > 10.0 then 5.0
  else if roe_pct > 0.0 then 2.0
  else 0.0


(** Convert total score to letter grade *)
let score_to_grade (score : float) : string =
  if score >= 80.0 then "A"
  else if score >= 60.0 then "B"
  else if score >= 40.0 then "C"
  else if score >= 20.0 then "D"
  else "F"


(** Assess earnings quality based on FCF conversion *)
let assess_earnings_quality (fcf_conv : float) : string =
  if fcf_conv > 1.0 then "High"
  else if fcf_conv > 0.7 then "Good"
  else if fcf_conv > 0.4 then "Medium"
  else if fcf_conv > 0.0 then "Low"
  else "Poor"


(** Assess balance sheet strength based on D/E ratio *)
let assess_balance_sheet (debt_to_equity : float) : string =
  if debt_to_equity < 0.3 then "Strong"
  else if debt_to_equity < 0.5 then "Good"
  else if debt_to_equity < 1.0 then "Moderate"
  else if debt_to_equity < 2.0 then "Weak"
  else "Poor"


(** Calculate quality metrics from raw data *)
let calculate_quality_metrics (data : garp_data) : quality_metrics =
  {
    fcf_conversion = data.fcf_conversion;
    debt_to_equity = data.debt_to_equity;
    roe = data.roe;
    roa = data.roa;
    earnings_quality = assess_earnings_quality data.fcf_conversion;
    balance_sheet_strength = assess_balance_sheet data.debt_to_equity;
  }


(** Calculate complete GARP score *)
let calculate_garp_score (peg_metrics : peg_metrics) (data : garp_data) : garp_score =
  (* Use forward PEG if available, else trailing *)
  let peg_for_scoring =
    if peg_metrics.peg_forward > 0.0 then peg_metrics.peg_forward
    else peg_metrics.peg_trailing
  in

  let peg_score = score_peg peg_for_scoring in
  let growth_score = score_growth peg_metrics.growth_rate_used in
  let quality_score = score_fcf_conversion data.fcf_conversion in
  let balance_sheet_score = score_balance_sheet data.debt_to_equity in
  let roe_score = score_roe data.roe in

  let total_score = peg_score +. growth_score +. quality_score +.
                    balance_sheet_score +. roe_score in

  {
    total_score;
    grade = score_to_grade total_score;
    peg_score;
    growth_score;
    quality_score;
    balance_sheet_score;
    roe_score;
  }


(** Determine investment signal from score and PEG *)
let determine_signal (score : garp_score) (peg_metrics : peg_metrics) : garp_signal =
  let peg =
    if peg_metrics.peg_forward > 0.0 then peg_metrics.peg_forward
    else peg_metrics.peg_trailing
  in

  (* No valid PEG *)
  if peg <= 0.0 then NotApplicable
  (* Strong Buy: Low PEG + High Score *)
  else if peg < 0.5 && score.total_score >= 70.0 then StrongBuy
  else if peg < 1.0 && score.total_score >= 60.0 then StrongBuy
  (* Buy: Attractive PEG + Good Score *)
  else if peg < 1.0 && score.total_score >= 40.0 then Buy
  else if peg < 1.5 && score.total_score >= 70.0 then Buy
  (* Hold: Fair PEG or mixed signals *)
  else if peg < 1.5 && score.total_score >= 40.0 then Hold
  else if peg < 2.0 && score.total_score >= 60.0 then Hold
  (* Caution: Getting expensive or quality concerns *)
  else if peg < 2.0 then Caution
  else if score.total_score < 40.0 then Caution
  (* Avoid: Expensive PEG *)
  else Avoid


(** Create complete GARP result from raw data *)
let analyze (data : garp_data) : garp_result =
  let peg_metrics = Peg.calculate_peg_metrics data in
  let quality_metrics = calculate_quality_metrics data in
  let garp_score = calculate_garp_score peg_metrics data in
  let signal = determine_signal garp_score peg_metrics in

  (* Calculate fair value estimates *)
  let implied_fair_pe = Peg.implied_fair_pe peg_metrics.growth_rate_used in

  (* Use forward EPS for fair price calculation *)
  let eps_for_valuation =
    if data.eps_forward > 0.0 then data.eps_forward
    else data.eps_trailing
  in
  let implied_fair_price = Peg.implied_fair_price eps_for_valuation implied_fair_pe in
  let upside_downside = Peg.calculate_upside_downside data.price implied_fair_price in

  {
    ticker = data.ticker;
    price = data.price;
    peg_metrics;
    quality_metrics;
    garp_score;
    signal;
    implied_fair_pe;
    implied_fair_price;
    upside_downside;
    raw_data = data;
  }


(** Compare multiple tickers and rank by GARP score *)
let compare (results : garp_result list) : garp_comparison =
  (* Sort by total score descending *)
  let sorted = List.sort
    (fun a b -> compare b.garp_score.total_score a.garp_score.total_score)
    results
  in

  (* Find best PEG (lowest positive PEG) *)
  let valid_pegs = List.filter_map (fun r ->
    let peg = if r.peg_metrics.peg_forward > 0.0 then r.peg_metrics.peg_forward
              else r.peg_metrics.peg_trailing in
    if peg > 0.0 then Some (r.ticker, peg) else None
  ) results in
  let best_peg = match List.sort (fun (_, a) (_, b) -> compare a b) valid_pegs with
    | (ticker, _) :: _ -> Some ticker
    | [] -> None
  in

  (* Best score is first in sorted list *)
  let best_score = match sorted with
    | r :: _ -> Some r.ticker
    | [] -> None
  in

  (* Create ranking list *)
  let ranking = List.map (fun r -> (r.ticker, r.garp_score.total_score)) sorted in

  {
    results = sorted;
    best_peg;
    best_score;
    ranking;
  }

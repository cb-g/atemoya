(** ETF Quality Scoring *)

open Types

(** Calculate grade from score *)
let score_to_grade (score : float) : string =
  if score >= 90.0 then "A+"
  else if score >= 85.0 then "A"
  else if score >= 80.0 then "A-"
  else if score >= 75.0 then "B+"
  else if score >= 70.0 then "B"
  else if score >= 65.0 then "B-"
  else if score >= 60.0 then "C+"
  else if score >= 55.0 then "C"
  else if score >= 50.0 then "C-"
  else if score >= 45.0 then "D+"
  else if score >= 40.0 then "D"
  else "F"

(** Determine signal from score *)
let score_to_signal (score : float) : etf_signal =
  if score >= 80.0 then HighQuality
  else if score >= 65.0 then GoodQuality
  else if score >= 50.0 then Acceptable
  else if score >= 35.0 then UseCaution
  else Avoid

(** Get string representation of signal *)
let signal_to_string (signal : etf_signal) : string =
  match signal with
  | HighQuality -> "High Quality"
  | GoodQuality -> "Good Quality"
  | Acceptable -> "Acceptable"
  | UseCaution -> "Use Caution"
  | Avoid -> "Avoid"

(** Calculate ETF quality score *)
let calculate_score (data : etf_data) : etf_score =
  (* Cost score (0-25) *)
  let cost_score = Costs.score_expense_ratio data.expense_ratio in

  (* Tracking score (0-25) *)
  let tracking_score = Premium_discount.score_tracking data.tracking in

  (* Liquidity score (0-25) *)
  let liquidity_score = Costs.score_liquidity
      data.bid_ask_spread_pct
      data.avg_volume
      data.current_price
  in

  (* Size score (0-25) *)
  let size_score = Costs.score_size data.aum in

  let total_score = cost_score +. tracking_score +. liquidity_score +. size_score in
  let grade = score_to_grade total_score in

  {
    total_score;
    grade;
    cost_score;
    tracking_score;
    liquidity_score;
    size_score;
  }

(** Calculate derivatives-adjusted score *)
let calculate_derivatives_score (data : etf_data) (analysis : derivatives_analysis) : etf_score =
  let base_score = calculate_score data in

  match data.derivatives_type with
  | Standard ->
    (* Standard ETFs use base score *)
    base_score
  | CoveredCall | PutWrite | Buffer | Volatility | Leveraged ->
    (* Derivatives ETFs: replace tracking with derivatives-specific score *)
    let deriv_score = Derivatives.score_derivatives data analysis in
    (* Scale from 0-50 to 0-25 to fit the tracking slot *)
    let scaled_deriv = min 25.0 (deriv_score *. 0.5) in

    let adjusted_total =
      base_score.cost_score +.
      scaled_deriv +.
      base_score.liquidity_score +.
      base_score.size_score
    in

    {
      total_score = adjusted_total;
      grade = score_to_grade adjusted_total;
      cost_score = base_score.cost_score;
      tracking_score = scaled_deriv;
      liquidity_score = base_score.liquidity_score;
      size_score = base_score.size_score;
    }

(** Generate overall recommendations based on analysis *)
let generate_recommendations (data : etf_data) (analysis : derivatives_analysis) : string list =
  let nav_recs = Premium_discount.generate_nav_recommendations data in
  let cost_recs = Costs.generate_cost_recommendations data in
  let deriv_recs = Derivatives.derivatives_recommendations data analysis in

  (* Combine all recommendations *)
  nav_recs @ cost_recs @ deriv_recs

(** Perform complete ETF analysis *)
let analyze_etf (data : etf_data) : etf_result =
  (* Classify tiers *)
  let nav_status = Premium_discount.classify_nav_status data.premium_discount_pct in

  let liquidity_tier = Costs.classify_liquidity_tier
      data.bid_ask_spread_pct
      (data.avg_volume *. data.current_price)
  in

  let cost_tier = Costs.classify_cost_tier data.expense_ratio in

  let tracking_quality =
    match data.tracking with
    | Some t -> Some (Premium_discount.classify_tracking_quality t.tracking_error_pct)
    | None -> None
  in

  let size_tier = Costs.classify_size_tier data.aum in

  (* Derivatives analysis *)
  let derivatives_analysis = Derivatives.analyze_derivatives data in

  (* Calculate score *)
  let score = calculate_derivatives_score data derivatives_analysis in

  (* Generate signal *)
  let signal = score_to_signal score.total_score in

  (* Generate recommendations *)
  let recommendations = generate_recommendations data derivatives_analysis in

  {
    data;
    nav_status;
    liquidity_tier;
    cost_tier;
    tracking_quality;
    size_tier;
    score;
    signal;
    derivatives_analysis;
    recommendations;
  }

(** Compare multiple ETFs *)
let compare_etfs (results : etf_result list) : etf_comparison =
  let find_best (selector : etf_result -> float) =
    match results with
    | [] -> ""
    | hd :: tl ->
      let best = List.fold_left (fun best r ->
          if selector r > selector best then r else best
        ) hd tl
      in
      best.data.ticker
  in

  let best_cost = find_best (fun r -> -. r.data.expense_ratio) in (* Lower is better *)
  let best_tracking = find_best (fun r ->
      match r.data.tracking with
      | Some t -> -. t.tracking_error_pct  (* Lower is better *)
      | None -> -1000.0
    ) in
  let best_liquidity = find_best (fun r -> -. r.data.bid_ask_spread_pct) in (* Lower is better *)
  let best_overall = find_best (fun r -> r.score.total_score) in

  {
    results;
    best_cost;
    best_tracking;
    best_liquidity;
    best_overall;
  }

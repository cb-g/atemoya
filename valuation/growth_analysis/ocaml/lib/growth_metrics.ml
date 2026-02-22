(** Growth metrics calculations *)

open Types

(** Classify revenue growth into tiers *)
let classify_growth (growth_pct : float) : growth_tier =
  if growth_pct < 0.0 then Declining
  else if growth_pct < 5.0 then NoGrowth
  else if growth_pct < 10.0 then SlowGrowth
  else if growth_pct < 20.0 then ModerateGrowth
  else if growth_pct < 40.0 then HighGrowth
  else Hypergrowth

(** Classify Rule of 40 score *)
let classify_rule_of_40 (score : float) : rule_of_40_tier =
  if score >= 40.0 then Excellent
  else if score >= 30.0 then Good
  else if score >= 20.0 then Moderate
  else Concerning

(** Determine margin trajectory based on operating margin vs gross margin ratio *)
let determine_margin_trajectory (data : growth_data) : margin_trajectory =
  (* Simple heuristic: compare operating margin to historical norms *)
  (* If operating margin is improving relative to gross, margins are expanding *)
  let op_to_gross =
    if data.gross_margin > 0.0 then data.operating_margin /. data.gross_margin
    else 0.0
  in
  if op_to_gross > 0.5 then Expanding
  else if op_to_gross > 0.3 then Stable
  else Contracting

(** Calculate operating leverage (earnings growth / revenue growth) *)
let calculate_operating_leverage (data : growth_data) : float =
  if data.revenue_growth > 0.01 then
    data.earnings_growth /. data.revenue_growth
  else
    1.0  (* Default to 1.0 if no meaningful revenue growth *)

(** Calculate PEG ratio *)
let calculate_peg (forward_pe : float) (earnings_growth_pct : float) : float option =
  if forward_pe <= 0.0 || earnings_growth_pct <= 0.0 then None
  else Some (forward_pe /. earnings_growth_pct)

(** Calculate EV/Revenue per point of growth *)
let calculate_ev_rev_per_growth (ev_revenue : float) (growth_pct : float) : float =
  if growth_pct > 1.0 then ev_revenue /. growth_pct
  else ev_revenue  (* Return raw multiple if growth is minimal *)

(** Calculate implied growth rate from current valuation
    Using simplified Gordon Growth Model: P/E = 1 / (r - g)
    Solving for g: g = r - 1/PE
    Assuming 10% required return *)
let calculate_implied_growth (forward_pe : float) : float option =
  if forward_pe <= 0.0 then None
  else
    let required_return = 0.10 in  (* 10% required return *)
    let implied_g = required_return -. (1.0 /. forward_pe) in
    if implied_g > 0.0 && implied_g < 1.0 then Some (implied_g *. 100.0)
    else None

(** Calculate analyst upside percentage *)
let calculate_analyst_upside (current_price : float) (target_mean : float) : float option =
  if target_mean > 0.0 && current_price > 0.0 then
    Some ((target_mean -. current_price) /. current_price *. 100.0)
  else
    None

(** Calculate all growth metrics *)
let calculate_growth_metrics (data : growth_data) : growth_metrics =
  let revenue_growth_pct = data.revenue_growth *. 100.0 in
  let revenue_cagr_3y_pct = data.revenue_cagr_3y *. 100.0 in
  let earnings_growth_pct = data.earnings_growth *. 100.0 in

  let growth_tier = classify_growth revenue_growth_pct in
  let rule_of_40_tier = classify_rule_of_40 data.rule_of_40 in

  let ev_revenue_per_growth = calculate_ev_rev_per_growth data.ev_revenue revenue_growth_pct in
  let peg_ratio = calculate_peg data.forward_pe earnings_growth_pct in

  {
    revenue_growth_pct;
    revenue_cagr_3y_pct;
    earnings_growth_pct;
    growth_tier;
    rule_of_40 = data.rule_of_40;
    rule_of_40_tier;
    ev_revenue_per_growth;
    peg_ratio;
  }

(** Calculate margin analysis *)
let calculate_margin_analysis (data : growth_data) : margin_analysis =
  let margin_trajectory = determine_margin_trajectory data in
  let operating_leverage = calculate_operating_leverage data in

  {
    gross_margin_pct = data.gross_margin *. 100.0;
    operating_margin_pct = data.operating_margin *. 100.0;
    fcf_margin_pct = data.fcf_margin *. 100.0;
    margin_trajectory;
    operating_leverage;
  }

(** Calculate growth valuation metrics *)
let calculate_growth_valuation (data : growth_data) : growth_valuation =
  let implied_growth = calculate_implied_growth data.forward_pe in
  let analyst_upside_pct = calculate_analyst_upside data.current_price data.analyst_target_mean in

  {
    ev_revenue = data.ev_revenue;
    ev_ebitda = data.ev_ebitda;
    forward_pe = data.forward_pe;
    implied_growth;
    analyst_upside_pct;
  }

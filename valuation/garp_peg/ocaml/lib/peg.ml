(** PEG ratio calculations for GARP analysis *)

open Types

(** Maximum reasonable growth rate (50% is very high but plausible for high-growth stocks) *)
let max_reasonable_growth = 50.0

(** Select the best available growth rate from the data.
    Strategy:
    1. Prefer eps_growth_1y (forward vs trailing EPS) - most grounded
    2. Fall back to revenue_growth (more stable than earnings_growth)
    3. Use earnings_growth if nothing else available
    4. Last resort: 5Y analyst estimate

    All growth rates are capped at 50% as very high growth is rarely sustainable.
    This prevents overly optimistic PEG ratios from unrealistic growth projections. *)
let select_growth_rate (data : garp_data) : float * string =
  (* Convert from decimal to percentage for PEG calculation *)
  (* PEG = P/E / Growth% where Growth is in percentage points (e.g., 15 not 0.15) *)

  (* Helper to apply capping and generate appropriate source string *)
  let with_cap rate source =
    let rate_pct = rate *. 100.0 in
    if rate_pct > max_reasonable_growth then
      (max_reasonable_growth, source ^ " (capped at 50%)")
    else
      (rate_pct, source)
  in

  (* Prefer 1Y EPS growth (forward vs trailing) - most reliable *)
  if data.eps_growth_1y > 0.01 then
    with_cap data.eps_growth_1y "1Y EPS growth"
  (* Fall back to revenue growth - more stable than earnings_growth *)
  else if data.revenue_growth > 0.01 then
    with_cap data.revenue_growth "Revenue growth"
  (* Try earnings growth *)
  else if data.earnings_growth > 0.01 then
    with_cap data.earnings_growth "Earnings growth"
  (* Last resort: 5Y estimate (often unreliable) *)
  else if data.growth_estimate_5y > 0.01 then
    with_cap data.growth_estimate_5y "5Y analyst estimate"
  (* No valid growth data *)
  else
    (0.0, "No growth data available")


(** Calculate PEG ratio: P/E / Growth Rate (%)
    Returns None if growth rate is zero or negative *)
let calculate_peg (pe : float) (growth_pct : float) : float option =
  if pe <= 0.0 || growth_pct <= 0.0 then None
  else Some (pe /. growth_pct)


(** Calculate PEGY ratio: P/E / (Growth Rate + Dividend Yield)
    Useful for dividend-paying growth stocks *)
let calculate_pegy (pe : float) (growth_pct : float) (div_yield_pct : float) : float option =
  let total_return = growth_pct +. div_yield_pct in
  if pe <= 0.0 || total_return <= 0.0 then None
  else Some (pe /. total_return)


(** Assess PEG ratio and return interpretation string *)
let assess_peg (peg : float option) : string =
  match peg with
  | None -> "Cannot calculate (negative earnings or no growth)"
  | Some p when p < 0.0 -> "Invalid (negative)"
  | Some p when p < 0.5 -> "Very Undervalued"
  | Some p when p < 1.0 -> "Undervalued"
  | Some p when p < 1.5 -> "Fairly Valued"
  | Some p when p < 2.0 -> "Moderately Expensive"
  | Some _ -> "Expensive"


(** Calculate all PEG metrics from raw data *)
let calculate_peg_metrics (data : garp_data) : peg_metrics =
  let growth_rate, growth_source = select_growth_rate data in
  let div_yield_pct = data.dividend_yield *. 100.0 in

  (* Calculate various PEG ratios *)
  let peg_trailing_opt = calculate_peg data.pe_trailing growth_rate in
  let peg_forward_opt = calculate_peg data.pe_forward growth_rate in
  let pegy_opt = calculate_pegy data.pe_forward growth_rate div_yield_pct in

  (* Convert options to floats (0.0 if None) *)
  let peg_trailing = Option.value peg_trailing_opt ~default:0.0 in
  let peg_forward = Option.value peg_forward_opt ~default:0.0 in
  let pegy = Option.value pegy_opt ~default:0.0 in

  (* Use forward PEG for assessment if available, else trailing *)
  let peg_for_assessment =
    if peg_forward > 0.0 then Some peg_forward
    else if peg_trailing > 0.0 then Some peg_trailing
    else None
  in

  {
    pe_trailing = data.pe_trailing;
    pe_forward = data.pe_forward;
    growth_rate_used = growth_rate;
    growth_source;
    peg_trailing;
    peg_forward;
    pegy;
    peg_assessment = assess_peg peg_for_assessment;
  }


(** Calculate implied fair P/E based on growth rate.
    Fair P/E = Growth Rate (i.e., PEG = 1.0) *)
let implied_fair_pe (growth_rate_pct : float) : float option =
  if growth_rate_pct <= 0.0 then None
  else Some growth_rate_pct


(** Calculate implied fair price based on fair P/E *)
let implied_fair_price (eps : float) (fair_pe : float option) : float option =
  match fair_pe with
  | None -> None
  | Some _ when eps <= 0.0 -> None
  | Some pe -> Some (eps *. pe)


(** Calculate upside/downside to fair price *)
let calculate_upside_downside (current_price : float) (fair_price : float option) : float option =
  match fair_price with
  | None -> None
  | Some fp when fp <= 0.0 -> None
  | Some fp -> Some ((fp -. current_price) /. current_price *. 100.0)


(** Peter Lynch's rules of thumb for PEG *)
let lynch_assessment (peg : float option) (growth_rate : float) : string =
  match peg with
  | None -> "Cannot assess - no PEG available"
  | Some p ->
    if growth_rate > 50.0 then
      "Caution: Very high growth (>50%) may not be sustainable"
    else if growth_rate < 5.0 then
      "Note: Low growth (<5%) - consider dividend yield (PEGY)"
    else if p < 1.0 then
      Printf.sprintf "Attractive: PEG %.2f < 1.0 (Lynch rule)" p
    else if p > 2.0 then
      Printf.sprintf "Expensive: PEG %.2f > 2.0 (avoid per Lynch)" p
    else
      Printf.sprintf "Fair: PEG %.2f in neutral zone" p

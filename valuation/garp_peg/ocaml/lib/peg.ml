(** PEG ratio calculations for GARP analysis *)

open Types

(** Maximum reasonable growth rate (50% is very high but plausible for high-growth stocks) *)
let max_reasonable_growth = 50.0

(** Explicit high-growth horizon (years) over which near-term growth fades to the
    terminal rate in the justified-P/E model. *)
let high_growth_years = 10

(** Hard cap on the near-term growth rate fed to the justified-P/E model (decimal).
    Even a fading model shouldn't start from an implausibly high rate. *)
let max_initial_growth = 0.40

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


(** Justified (fair) TRAILING P/E from a two-stage earnings model.

    Replaces the naive PEG = 1.0 rule (fair P/E = growth%), which systematically
    over-values high growth because it assigns a P/E equal to the growth rate with
    no discounting, no fade, and no risk adjustment. Here:
      - near-term [growth] fades LINEARLY to [terminal_growth] over [years];
      - each year's earnings are split into payout vs. retention via the
        sustainable-growth identity (retention = g / ROE), so fast growers
        reinvest more and distribute less;
      - the payout stream + a Gordon terminal value are discounted at the
        firm's cost of equity [cost_of_equity] (CAPM, computed upstream).

    Returns a trailing justified P/E (value per unit of trailing EPS, with E0
    normalized to 1.0), or None when the discount rate does not exceed terminal
    growth. All rate arguments are decimals (0.15 = 15%). *)
let justified_fair_pe
    ~(growth : float) ~(terminal_growth : float)
    ~(cost_of_equity : float) ~(roe : float) ~(years : int) : float option =
  let r = cost_of_equity in
  let gt = terminal_growth in
  if r <= gt +. 0.005 then None  (* need r > g_terminal for a finite terminal value *)
  else begin
    (* Cap initial growth at the firm's ROE (Higgins sustainable-growth ceiling:
       EPS cannot compound faster than ROE under <=100% retention) and at an
       absolute max. Guards the model against spurious one-off EPS-growth inputs. *)
    let growth_ceiling = if roe > 0.0 then min max_initial_growth roe else max_initial_growth in
    let g0 = max 0.0 (min growth_ceiling growth) in
    let n = max 1 years in
    (* Payout funded by what isn't retained to grow at the firm's ROE; fall back
       to a mature payout when ROE is missing/degenerate. *)
    let payout_for g =
      if roe > 0.01 then max 0.0 (min 1.0 (1.0 -. g /. roe))
      else 0.5
    in
    let nf = float_of_int n in
    (* Stage 1: discrete linear fade of growth from g0 (year 1) to gt (year n). *)
    let rec accum t e_prev pv =
      if t > n then (pv, e_prev)
      else
        let g_t = g0 +. (gt -. g0) *. (float_of_int t /. nf) in
        let e_t = e_prev *. (1.0 +. g_t) in
        let pv' = pv +. (payout_for g_t *. e_t) /. ((1.0 +. r) ** float_of_int t) in
        accum (t + 1) e_t pv'
    in
    let pv_stage1, e_n = accum 1 1.0 0.0 in  (* E0 normalized to 1.0 *)
    (* Stage 2: Gordon terminal value on year-n earnings grown one more period. *)
    let tv_n = payout_for gt *. e_n *. (1.0 +. gt) /. (r -. gt) in
    let pv_terminal = tv_n /. ((1.0 +. r) ** nf) in
    let pe = pv_stage1 +. pv_terminal in
    if pe > 0.0 then Some pe else None
  end


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

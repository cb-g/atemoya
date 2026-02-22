(** Dividend Discount Model (DDM) valuations *)

open Types

(** Gordon Growth Model (constant growth DDM)
    Fair Value = D1 / (r - g)
    where D1 = D0 * (1 + g), r = required return, g = growth rate
    Only valid when r > g *)
let gordon_growth_model (current_dividend : float) (required_return : float) (growth_rate : float) : float option =
  if required_return <= growth_rate then None
  else if current_dividend <= 0.0 then None
  else
    let d1 = current_dividend *. (1.0 +. growth_rate) in
    Some (d1 /. (required_return -. growth_rate))

(** Two-Stage DDM
    Stage 1: High growth for n years
    Stage 2: Terminal growth forever
    PV = Sum(D_t / (1+r)^t) + Terminal_Value / (1+r)^n *)
let two_stage_ddm
    (current_dividend : float)
    (required_return : float)
    (high_growth_rate : float)
    (terminal_growth_rate : float)
    (high_growth_years : int)
  : float option =
  if required_return <= terminal_growth_rate then None
  else if current_dividend <= 0.0 then None
  else
    (* Stage 1: Sum of high-growth dividends *)
    let rec stage1_pv acc n dividend =
      if n > high_growth_years then (acc, dividend)
      else
        let next_div = dividend *. (1.0 +. high_growth_rate) in
        let pv = next_div /. ((1.0 +. required_return) ** float_of_int n) in
        stage1_pv (acc +. pv) (n + 1) next_div
    in
    let (pv_stage1, last_high_growth_div) = stage1_pv 0.0 1 current_dividend in

    (* Stage 2: Terminal value using Gordon Growth *)
    let terminal_dividend = last_high_growth_div *. (1.0 +. terminal_growth_rate) in
    let terminal_value = terminal_dividend /. (required_return -. terminal_growth_rate) in
    let pv_terminal = terminal_value /. ((1.0 +. required_return) ** float_of_int high_growth_years) in

    Some (pv_stage1 +. pv_terminal)

(** H-Model (gradual decline from high to low growth)
    Fair Value = D0 * (1 + g_long) / (r - g_long) + D0 * H * (g_short - g_long) / (r - g_long)
    where H = half-life of high growth period *)
let h_model
    (current_dividend : float)
    (required_return : float)
    (short_term_growth : float)
    (long_term_growth : float)
    (half_life : float)
  : float option =
  if required_return <= long_term_growth then None
  else if current_dividend <= 0.0 then None
  else
    let base_value = current_dividend *. (1.0 +. long_term_growth) /. (required_return -. long_term_growth) in
    let growth_premium = current_dividend *. half_life *. (short_term_growth -. long_term_growth) /. (required_return -. long_term_growth) in
    Some (base_value +. growth_premium)

(** Yield-based valuation
    Fair Price = Annual Dividend / Fair Yield
    Uses historical average yield as fair yield *)
let yield_based_value (annual_dividend : float) (fair_yield : float) : float option =
  if fair_yield <= 0.0 then None
  else if annual_dividend <= 0.0 then None
  else Some (annual_dividend /. fair_yield)

(** Calculate all DDM valuations *)
let calculate_ddm_valuation (data : dividend_data) (params : ddm_params) : ddm_valuation =
  let current_div = data.dividend_rate in

  (* Use 5-year DGR for short-term, but cap at something reasonable *)
  let short_term_growth =
    if data.dgr_5y > 0.0 then min data.dgr_5y 0.15
    else data.dgr_3y
  in

  (* Gordon Growth - use terminal growth rate *)
  let gordon = gordon_growth_model current_div params.required_return params.terminal_growth in

  (* Two-Stage DDM - high growth then terminal *)
  let two_stage =
    if short_term_growth > params.terminal_growth then
      two_stage_ddm current_div params.required_return short_term_growth params.terminal_growth params.high_growth_years
    else
      gordon  (* Fall back to Gordon if no high growth *)
  in

  (* H-Model - gradual transition *)
  let h_model_val =
    if short_term_growth > params.terminal_growth then
      h_model current_div params.required_return short_term_growth params.terminal_growth (float_of_int params.high_growth_years /. 2.0)
    else
      gordon
  in

  (* Yield-based - if historical yield is available *)
  let yield_based =
    match params.historical_yield with
    | Some hist_yield -> yield_based_value current_div hist_yield
    | None -> None
  in

  (* Calculate average fair value from available valuations *)
  let values = List.filter_map Fun.id [gordon; two_stage; h_model_val; yield_based] in
  let average_fair_value =
    if List.length values > 0 then
      Some (List.fold_left ( +. ) 0.0 values /. float_of_int (List.length values))
    else
      None
  in

  (* Calculate upside/downside *)
  let upside_downside =
    match average_fair_value with
    | Some fv when fv > 0.0 ->
        Some ((fv -. data.current_price) /. data.current_price *. 100.0)
    | _ -> None
  in

  {
    gordon_growth_value = gordon;
    two_stage_value = two_stage;
    h_model_value = h_model_val;
    yield_based_value = yield_based;
    average_fair_value;
    upside_downside_pct = upside_downside;
  }

(** Estimate required return using CAPM *)
let estimate_required_return (risk_free_rate : float) (market_premium : float) (beta : float) : float =
  risk_free_rate +. beta *. market_premium

(** Create default DDM parameters *)
let default_params ?(required_return=0.08) ?(terminal_growth=0.03) ?(high_growth_years=5) ?historical_yield () : ddm_params =
  { required_return; terminal_growth; high_growth_years; historical_yield }

(** Sensitivity analysis: calculate fair values at different discount rates *)
let sensitivity_discount_rates (data : dividend_data) (rates : float list) (growth : float) : (float * float option) list =
  List.map (fun r ->
    let value = gordon_growth_model data.dividend_rate r growth in
    (r, value)
  ) rates

(** Sensitivity analysis: calculate fair values at different growth rates *)
let sensitivity_growth_rates (data : dividend_data) (required_return : float) (rates : float list) : (float * float option) list =
  List.map (fun g ->
    let value = gordon_growth_model data.dividend_rate required_return g in
    (g, value)
  ) rates

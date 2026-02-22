(** Dividend Discount Model for REIT valuation

    REITs are ideal candidates for DDM because:
    1. Required to distribute 90%+ of taxable income
    2. Dividends are primary return component
    3. Relatively stable, predictable payouts
    4. Growth funded externally, not from retained earnings

    Models implemented:
    - Gordon Growth Model (single-stage)
    - Two-Stage DDM (high growth then terminal)
    - H-Model (gradual growth decline)
*)

open Types

(** Gordon Growth Model (constant growth perpetuity)
    P = D1 / (ke - g)
    where D1 = D0 * (1 + g) *)
let gordon_growth ~dividend ~cost_of_equity ~growth_rate : float =
  if cost_of_equity <= growth_rate then
    (* Growth exceeds cost of equity - model invalid *)
    0.0
  else
    let d1 = dividend *. (1.0 +. growth_rate) in
    d1 /. (cost_of_equity -. growth_rate)

(** Implied growth rate from Gordon Growth Model
    g = ke - D1/P *)
let implied_growth ~price ~dividend ~cost_of_equity : float =
  if price <= 0.0 then 0.0
  else
    let d1 = dividend *. 1.0 in  (* Assume D0 = D1 for simplicity *)
    cost_of_equity -. (d1 /. price)

(** Two-Stage DDM
    Stage 1: Project dividends at high growth rate
    Stage 2: Terminal value using Gordon Growth at terminal rate *)
let two_stage_ddm ~dividend ~cost_of_equity ~high_growth
    ~terminal_growth ~high_growth_years : float =
  if cost_of_equity <= terminal_growth then 0.0
  else
    (* Stage 1: PV of dividends during high growth period *)
    let rec pv_dividends acc year div =
      if year > high_growth_years then acc
      else
        let pv = div /. ((1.0 +. cost_of_equity) ** float_of_int year) in
        pv_dividends (acc +. pv) (year + 1) (div *. (1.0 +. high_growth))
    in
    let d1 = dividend *. (1.0 +. high_growth) in
    let stage1_pv = pv_dividends 0.0 1 d1 in

    (* Terminal dividend: dividend grown through high growth period, then one more year at terminal *)
    let terminal_dividend =
      dividend
      *. ((1.0 +. high_growth) ** float_of_int high_growth_years)
      *. (1.0 +. terminal_growth)
    in

    (* Terminal value using Gordon Growth *)
    let terminal_value = terminal_dividend /. (cost_of_equity -. terminal_growth) in

    (* PV of terminal value *)
    let terminal_pv =
      terminal_value /. ((1.0 +. cost_of_equity) ** float_of_int high_growth_years)
    in

    stage1_pv +. terminal_pv

(** H-Model: Growth linearly declines from high to terminal over H years
    P = D0 * (1 + gL) / (ke - gL) + D0 * H * (gS - gL) / (ke - gL)
    where gS = short-term growth, gL = long-term growth, H = half-life *)
let h_model ~dividend ~cost_of_equity ~short_term_growth
    ~long_term_growth ~half_life : float =
  if cost_of_equity <= long_term_growth then 0.0
  else
    let stable_value =
      dividend *. (1.0 +. long_term_growth) /. (cost_of_equity -. long_term_growth)
    in
    let growth_premium =
      dividend *. half_life *. (short_term_growth -. long_term_growth)
      /. (cost_of_equity -. long_term_growth)
    in
    stable_value +. growth_premium

(** Calculate DDM valuation using two-stage model *)
let calculate_ddm_value ~(market : market_data) ~(params : ddm_params) : float =
  two_stage_ddm
    ~dividend:market.dividend_per_share
    ~cost_of_equity:params.cost_of_equity
    ~high_growth:params.dividend_growth_rate
    ~terminal_growth:params.terminal_growth_rate
    ~high_growth_years:params.projection_years

(** Calculate cost of equity for REIT *)
let calculate_cost_of_equity ~risk_free_rate ~equity_risk_premium
    ~beta ~size_premium : float =
  risk_free_rate +. (beta *. equity_risk_premium) +. size_premium

(** Default REIT beta by sector *)
let sector_beta = function
  | Industrial -> 0.85     (* Lower cyclicality *)
  | DataCenter -> 0.90     (* Tech correlation *)
  | SelfStorage -> 0.75    (* Defensive *)
  | Residential -> 0.80    (* Essential need *)
  | Healthcare -> 0.70     (* Very defensive *)
  | Specialty -> 0.90      (* Varies *)
  | Office -> 1.10         (* Cyclical, WFH risk *)
  | Retail -> 1.15         (* E-commerce disruption *)
  | Hotel -> 1.40          (* Highly cyclical *)
  | Diversified -> 0.95    (* Blend *)
  | Mortgage -> 1.30       (* High interest rate sensitivity *)

(** Calculate WACC for REIT *)
let calculate_wacc ~cost_of_equity ~cost_of_debt ~tax_rate ~debt_ratio : float =
  let equity_ratio = 1.0 -. debt_ratio in
  let after_tax_debt = cost_of_debt *. (1.0 -. tax_rate) in
  (cost_of_equity *. equity_ratio) +. (after_tax_debt *. debt_ratio)

(** Full cost of capital calculation *)
let calculate_cost_of_capital ~(financial : financial_data)
    ~(market : market_data) ~risk_free_rate ~equity_risk_premium : cost_of_capital =
  let beta = sector_beta market.sector in
  let size_premium =
    if market.market_cap < 2_000_000_000.0 then 0.015  (* 1.5% for small caps *)
    else if market.market_cap < 10_000_000_000.0 then 0.005  (* 0.5% for mid caps *)
    else 0.0
  in
  let cost_of_equity =
    calculate_cost_of_equity ~risk_free_rate ~equity_risk_premium ~beta ~size_premium
  in

  (* Estimate cost of debt from interest coverage *)
  let cost_of_debt =
    if financial.total_debt > 0.0 && financial.noi > 0.0 then
      (* Rough estimate: spread based on debt/EBITDA-ish metric *)
      let debt_noi_ratio = financial.total_debt /. financial.noi in
      if debt_noi_ratio < 5.0 then risk_free_rate +. 0.015
      else if debt_noi_ratio < 8.0 then risk_free_rate +. 0.025
      else risk_free_rate +. 0.040
    else risk_free_rate +. 0.020
  in

  (* REITs often have minimal corporate tax due to distribution requirements *)
  let tax_rate = 0.0 in

  let total_capital = market.market_cap +. financial.total_debt in
  let debt_ratio =
    if total_capital > 0.0 then financial.total_debt /. total_capital else 0.0
  in

  let wacc =
    calculate_wacc ~cost_of_equity ~cost_of_debt ~tax_rate ~debt_ratio
  in

  {
    risk_free_rate;
    equity_risk_premium;
    reit_beta = beta;
    size_premium;
    cost_of_equity;
    cost_of_debt;
    tax_rate;
    debt_ratio;
    wacc;
  }

(** Dividend yield sustainability check *)
let is_yield_sustainable ~dividend_yield ~affo_yield : bool =
  (* AFFO yield should exceed dividend yield for sustainability *)
  affo_yield >= dividend_yield *. 0.95

(** Project future dividends *)
let project_dividends ~initial_dividend ~growth_rate ~years : float array =
  Array.init years (fun i ->
    initial_dividend *. ((1.0 +. growth_rate) ** float_of_int (i + 1))
  )

(** FFO and AFFO calculations for REIT valuation

    FFO (Funds From Operations) is the REIT industry standard measure of
    operating performance. It adjusts GAAP net income for non-cash items
    that distort cash generation ability.

    Formula:
    FFO = Net Income
        + Depreciation & Amortization (real estate only)
        + Impairment Charges
        - Gains on Property Sales

    AFFO (Adjusted FFO) further adjusts for:
    - Maintenance CapEx (required to sustain properties)
    - Straight-line rent adjustments
    - Stock-based compensation

    AFFO is considered a better proxy for sustainable cash flow.
*)

open Types

let calculate_ffo ~(financial : financial_data) : float =
  financial.net_income
  +. financial.depreciation
  +. financial.amortization
  +. financial.impairments
  -. financial.gains_on_sales

let calculate_affo ~(financial : financial_data) : float =
  let ffo = calculate_ffo ~financial in
  ffo
  -. financial.maintenance_capex
  -. financial.straight_line_rent_adj
  -. financial.stock_compensation

let calculate_ffo_metrics ~(financial : financial_data)
    ~(market : market_data) : ffo_metrics =
  let ffo = calculate_ffo ~financial in
  let affo = calculate_affo ~financial in

  let shares = market.shares_outstanding in
  let ffo_per_share = if shares > 0.0 then ffo /. shares else 0.0 in
  let affo_per_share = if shares > 0.0 then affo /. shares else 0.0 in

  let annual_dividend = market.dividend_per_share *. shares in
  let ffo_payout = if ffo > 0.0 then annual_dividend /. ffo else 0.0 in
  let affo_payout = if affo > 0.0 then annual_dividend /. affo else 0.0 in

  {
    ffo;
    affo;
    ffo_per_share;
    affo_per_share;
    ffo_payout_ratio = ffo_payout;
    affo_payout_ratio = affo_payout;
  }

(** Calculate P/FFO ratio *)
let price_to_ffo ~price ~ffo_per_share : float =
  if ffo_per_share > 0.0 then price /. ffo_per_share else 0.0

(** Calculate P/AFFO ratio *)
let price_to_affo ~price ~affo_per_share : float =
  if affo_per_share > 0.0 then price /. affo_per_share else 0.0

(** Implied value from sector P/FFO multiple *)
let implied_value_from_p_ffo ~ffo_per_share ~sector_p_ffo : float =
  ffo_per_share *. sector_p_ffo

(** Implied value from sector P/AFFO multiple *)
let implied_value_from_p_affo ~affo_per_share ~sector_p_affo : float =
  affo_per_share *. sector_p_affo

(** Assess dividend safety based on payout ratios *)
let dividend_safety_score ~(ffo_metrics : ffo_metrics) : float =
  (* Ideal AFFO payout: 70-85% leaves room for growth
     >100% is unsustainable, <60% suggests dividend could grow *)
  let payout = ffo_metrics.affo_payout_ratio in
  if payout <= 0.0 then 0.0
  else if payout < 0.60 then 1.0  (* Very safe, room to grow *)
  else if payout < 0.75 then 0.9  (* Healthy *)
  else if payout < 0.85 then 0.8  (* Acceptable *)
  else if payout < 0.95 then 0.6  (* Tight *)
  else if payout < 1.05 then 0.3  (* At risk *)
  else 0.1                        (* Unsustainable *)

(** FFO growth rate required to justify current P/FFO *)
let implied_ffo_growth ~price ~ffo_per_share ~cost_of_equity : float =
  (* Gordon Growth: P = FFO / (ke - g), solving for g: *)
  (* g = ke - FFO/P *)
  let ffo_yield = if price > 0.0 then ffo_per_share /. price else 0.0 in
  cost_of_equity -. ffo_yield

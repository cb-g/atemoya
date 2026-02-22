(** NAV (Net Asset Value) calculation for REIT valuation

    NAV represents the intrinsic value of a REIT's underlying properties.
    Unlike traditional DCF which values future cash flows, NAV values
    the current portfolio at market prices.

    Formula:
    Property Value = NOI / Cap Rate
    NAV = Property Value + Cash + Other Assets - Total Debt
    NAV per Share = NAV / Shares Outstanding

    Cap rates vary by:
    - Property sector (industrial < residential < office < retail)
    - Location (gateway cities vs secondary markets)
    - Property quality (Class A vs Class B/C)
    - Interest rate environment (inverse relationship)
*)

open Types

(** Default cap rates by sector (based on market conditions)
    These are mid-cycle estimates; actual rates vary with market conditions *)
let default_cap_rate = function
  | Industrial -> 0.050    (* 5.0% - Strong demand, low supply *)
  | DataCenter -> 0.055    (* 5.5% - Tech-driven growth *)
  | SelfStorage -> 0.055   (* 5.5% - Fragmented, stable demand *)
  | Residential -> 0.050   (* 5.0% - Housing shortage support *)
  | Healthcare -> 0.065    (* 6.5% - Aging demographics *)
  | Specialty -> 0.055     (* 5.5% - Varies widely *)
  | Office -> 0.070        (* 7.0% - WFH headwinds *)
  | Retail -> 0.070        (* 7.0% - E-commerce disruption *)
  | Hotel -> 0.080         (* 8.0% - Cyclical, volatile *)
  | Diversified -> 0.060   (* 6.0% - Weighted average *)
  | Mortgage -> 0.0        (* N/A - mREITs don't use cap rate based NAV *)

(** Calculate implied property value from NOI and cap rate *)
let property_value_from_noi ~noi ~cap_rate : float =
  if cap_rate > 0.0 then noi /. cap_rate else 0.0

(** Calculate implied cap rate from property value and NOI *)
let implied_cap_rate ~noi ~property_value : float =
  if property_value > 0.0 then noi /. property_value else 0.0

(** Calculate NAV components *)
let calculate_nav ~(financial : financial_data) ~(market : market_data)
    ~cap_rate : nav_components =
  (* Property value from NOI / cap rate *)
  let property_value = property_value_from_noi ~noi:financial.noi ~cap_rate in

  (* Other assets (simplified: just cash) *)
  let other_assets = financial.cash in

  (* NAV = Property Value + Other Assets - Debt *)
  let nav = property_value +. other_assets -. financial.total_debt in

  let nav_per_share =
    if market.shares_outstanding > 0.0 then
      nav /. market.shares_outstanding
    else 0.0
  in

  (* Premium/discount = (Price - NAV) / NAV *)
  let premium_discount =
    if nav_per_share > 0.0 then
      (market.price -. nav_per_share) /. nav_per_share
    else 0.0
  in

  {
    property_value;
    other_assets;
    total_debt = financial.total_debt;
    nav;
    nav_per_share;
    premium_discount;
  }

(** Calculate NAV using sector default cap rate *)
let calculate_nav_default ~(financial : financial_data)
    ~(market : market_data) : nav_components =
  let cap_rate = default_cap_rate market.sector in
  calculate_nav ~financial ~market ~cap_rate

(** Implied value based on NAV and target premium/discount *)
let nav_implied_value ~nav_per_share ~target_premium : float =
  nav_per_share *. (1.0 +. target_premium)

(** Target premium/discount based on quality *)
let quality_adjusted_premium ~(quality : quality_metrics) : float =
  (* High quality REITs deserve premium to NAV
     Low quality may trade at discount *)
  let base_premium = -0.05 in  (* Start at 5% discount *)
  let quality_adj = (quality.overall_quality -. 0.5) *. 0.30 in
  (* Range: -20% discount to +10% premium *)
  max (-0.20) (min 0.10 (base_premium +. quality_adj))

(** Calculate cap rate assumptions *)
let calculate_cap_rate_assumptions ~(financial : financial_data)
    ~(market : market_data) ~risk_free_rate : cap_rate_assumptions =
  (* Implied cap rate from current market cap *)
  let implied =
    if market.market_cap > 0.0 then
      financial.noi /. (market.market_cap +. financial.total_debt -. financial.cash)
    else 0.0
  in
  let market_cap = default_cap_rate market.sector in
  let spread = market_cap -. risk_free_rate in
  {
    sector = market.sector;
    implied_cap_rate = implied;
    market_cap_rate = market_cap;
    cap_rate_spread = spread;
  }

(** Sensitivity: NAV at different cap rates *)
let nav_sensitivity ~(financial : financial_data) ~(market : market_data)
    ~cap_rates : (float * float) list =
  List.map (fun cap_rate ->
    let nav = calculate_nav ~financial ~market ~cap_rate in
    (cap_rate, nav.nav_per_share)
  ) cap_rates

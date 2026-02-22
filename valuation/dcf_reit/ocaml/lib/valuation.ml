(** Combined REIT valuation using multiple methodologies

    Four valuation approaches:
    1. P/FFO multiple vs sector average
    2. P/AFFO multiple vs sector average
    3. NAV (Net Asset Value) approach
    4. Dividend Discount Model

    Final fair value is a weighted blend of all methods.
*)

open Types

(** Default sector benchmarks *)
let default_sector_benchmarks = function
  | Industrial ->
      { sector = Industrial; avg_cap_rate = 0.050; avg_p_ffo = 22.0;
        avg_p_affo = 26.0; avg_nav_premium = 0.05 }
  | DataCenter ->
      { sector = DataCenter; avg_cap_rate = 0.055; avg_p_ffo = 20.0;
        avg_p_affo = 24.0; avg_nav_premium = 0.10 }
  | SelfStorage ->
      { sector = SelfStorage; avg_cap_rate = 0.055; avg_p_ffo = 18.0;
        avg_p_affo = 22.0; avg_nav_premium = 0.00 }
  | Residential ->
      { sector = Residential; avg_cap_rate = 0.050; avg_p_ffo = 20.0;
        avg_p_affo = 24.0; avg_nav_premium = 0.05 }
  | Healthcare ->
      { sector = Healthcare; avg_cap_rate = 0.065; avg_p_ffo = 14.0;
        avg_p_affo = 17.0; avg_nav_premium = -0.05 }
  | Specialty ->
      { sector = Specialty; avg_cap_rate = 0.055; avg_p_ffo = 18.0;
        avg_p_affo = 22.0; avg_nav_premium = 0.00 }
  | Office ->
      { sector = Office; avg_cap_rate = 0.070; avg_p_ffo = 12.0;
        avg_p_affo = 15.0; avg_nav_premium = -0.15 }
  | Retail ->
      { sector = Retail; avg_cap_rate = 0.070; avg_p_ffo = 13.0;
        avg_p_affo = 16.0; avg_nav_premium = -0.10 }
  | Hotel ->
      { sector = Hotel; avg_cap_rate = 0.080; avg_p_ffo = 10.0;
        avg_p_affo = 12.0; avg_nav_premium = -0.20 }
  | Diversified ->
      { sector = Diversified; avg_cap_rate = 0.060; avg_p_ffo = 15.0;
        avg_p_affo = 18.0; avg_nav_premium = -0.05 }
  | Mortgage ->
      (* mREITs use different metrics - these are placeholders for compatibility *)
      { sector = Mortgage; avg_cap_rate = 0.0; avg_p_ffo = 0.0;
        avg_p_affo = 0.0; avg_nav_premium = 0.0 }

(** P/FFO valuation method *)
let value_by_p_ffo ~(ffo : ffo_metrics) ~(market : market_data)
    ~(quality : quality_metrics) : valuation_method =
  let benchmarks = default_sector_benchmarks market.sector in
  let p_ffo = Ffo.price_to_ffo ~price:market.price ~ffo_per_share:ffo.ffo_per_share in

  (* Adjust sector multiple for quality *)
  let quality_adj = Quality.quality_multiple_adjustment ~quality in
  let adjusted_multiple = benchmarks.avg_p_ffo *. (1.0 +. quality_adj) in

  let implied_value = ffo.ffo_per_share *. adjusted_multiple in

  PriceToFFO {
    p_ffo;
    sector_avg = benchmarks.avg_p_ffo;
    implied_value;
  }

(** P/AFFO valuation method *)
let value_by_p_affo ~(ffo : ffo_metrics) ~(market : market_data)
    ~(quality : quality_metrics) : valuation_method =
  let benchmarks = default_sector_benchmarks market.sector in
  let p_affo = Ffo.price_to_affo ~price:market.price ~affo_per_share:ffo.affo_per_share in

  let quality_adj = Quality.quality_multiple_adjustment ~quality in
  let adjusted_multiple = benchmarks.avg_p_affo *. (1.0 +. quality_adj) in

  let implied_value = ffo.affo_per_share *. adjusted_multiple in

  PriceToAFFO {
    p_affo;
    sector_avg = benchmarks.avg_p_affo;
    implied_value;
  }

(** NAV valuation method *)
let value_by_nav ~(nav : nav_components) ~(market : market_data)
    ~(quality : quality_metrics) : valuation_method =
  let benchmarks = default_sector_benchmarks market.sector in

  (* Target premium adjusted for quality *)
  let quality_premium = Nav.quality_adjusted_premium ~quality in
  let target_premium = benchmarks.avg_nav_premium +. quality_premium in

  let implied_value = Nav.nav_implied_value ~nav_per_share:nav.nav_per_share ~target_premium in

  NAVMethod {
    nav_per_share = nav.nav_per_share;
    premium_discount = nav.premium_discount;
    target_premium;
    implied_value;
  }

(** DDM valuation method *)
let value_by_ddm ~(market : market_data) ~(cost_of_capital : cost_of_capital)
    ~growth_rate : valuation_method =
  let params = {
    cost_of_equity = cost_of_capital.cost_of_equity;
    dividend_growth_rate = growth_rate;
    terminal_growth_rate = 0.02;  (* 2% long-term *)
    projection_years = 5;
  } in

  let intrinsic_value = Ddm.calculate_ddm_value ~market ~params in
  let implied_growth =
    Ddm.implied_growth ~price:market.price ~dividend:market.dividend_per_share
      ~cost_of_equity:cost_of_capital.cost_of_equity
  in

  DividendDiscount {
    intrinsic_value;
    dividend_yield = market.dividend_yield;
    implied_growth;
  }

(** Extract implied value from valuation method *)
let implied_value_of = function
  | PriceToFFO { implied_value; _ } -> implied_value
  | PriceToAFFO { implied_value; _ } -> implied_value
  | NAVMethod { implied_value; _ } -> implied_value
  | DividendDiscount { intrinsic_value; _ } -> intrinsic_value
  | PriceToBook { implied_value; _ } -> implied_value
  | PriceToDE { implied_value; _ } -> implied_value

(** Sector-aware blending weights.
    Net-lease and income-oriented REITs weight AFFO/DDM heavily (cash flow driven).
    Asset-heavy REITs (industrial, data center) weight NAV more.
    Distressed sectors (office, hotel) de-weight NAV. *)
let sector_weights (sector : property_sector) =
  (*               P/FFO  P/AFFO  NAV    DDM   *)
  match sector with
  | Industrial  -> (0.25,  0.25,  0.30,  0.20)
  | DataCenter  -> (0.25,  0.25,  0.25,  0.25)
  | SelfStorage -> (0.25,  0.30,  0.25,  0.20)
  | Residential -> (0.25,  0.30,  0.20,  0.25)
  | Retail      -> (0.20,  0.35,  0.10,  0.35)  (* net-lease: income-driven *)
  | Healthcare  -> (0.20,  0.30,  0.15,  0.35)
  | Specialty   -> (0.25,  0.30,  0.20,  0.25)
  | Office      -> (0.30,  0.30,  0.15,  0.25)  (* office: NAV unreliable *)
  | Hotel       -> (0.25,  0.30,  0.15,  0.30)
  | Diversified -> (0.25,  0.30,  0.20,  0.25)
  | Mortgage    -> (0.0,   0.0,   0.0,   0.0)   (* handled by mreit blend *)

(** Calculate blended fair value with sector-aware weights *)
let blend_fair_value ~sector ~p_ffo_val ~p_affo_val ~nav_val ~ddm_val : float =
  let (w_ffo, w_affo, w_nav, w_ddm) = sector_weights sector in
  let values = [
    (implied_value_of p_ffo_val, w_ffo);
    (implied_value_of p_affo_val, w_affo);
    (implied_value_of nav_val, w_nav);
    (implied_value_of ddm_val, w_ddm);
  ] in

  let weighted_sum = List.fold_left (fun acc (v, w) ->
    if v > 0.0 then acc +. (v *. w) else acc
  ) 0.0 values in

  let total_weight = List.fold_left (fun acc (v, w) ->
    if v > 0.0 then acc +. w else acc
  ) 0.0 values in

  if total_weight > 0.0 then weighted_sum /. total_weight else 0.0

(** Determine investment signal *)
let determine_signal ~price ~fair_value ~(quality : quality_metrics) : investment_signal =
  let upside = if price > 0.0 then (fair_value -. price) /. price else 0.0 in

  (* Quality threshold for recommendations *)
  let quality_ok = quality.overall_quality >= 0.45 in

  if not quality_ok then Caution
  else if upside > 0.30 then StrongBuy
  else if upside > 0.15 then Buy
  else if upside > -0.10 then Hold
  else if upside > -0.25 then Sell
  else StrongSell

(** Full REIT valuation - handles both equity REITs and mREITs *)
let value_reit ~(financial : financial_data) ~(market : market_data)
    ~risk_free_rate ~equity_risk_premium : valuation_result =

  (* 1. Calculate FFO metrics (for equity REITs, placeholder for mREITs) *)
  let ffo_metrics = Ffo.calculate_ffo_metrics ~financial ~market in

  (* 2. Calculate NAV (meaningful for equity REITs only) *)
  let nav = Nav.calculate_nav_default ~financial ~market in

  (* 3. Calculate cost of capital *)
  let cost_of_capital =
    Ddm.calculate_cost_of_capital ~financial ~market ~risk_free_rate ~equity_risk_premium
  in

  (* Branch based on REIT type *)
  match market.reit_type with
  | MortgageREIT ->
      (* mREIT-specific valuation *)
      let mreit_metrics = Mreit.calculate_mreit_metrics ~financial ~market in
      let quality = Mreit.calculate_mreit_quality ~mreit:mreit_metrics in

      (* Quality adjustment for multiples *)
      let quality_adj = Quality.quality_multiple_adjustment ~quality in

      (* mREIT valuation methods *)
      let p_bv_valuation = Mreit.value_by_price_to_book ~mreit:mreit_metrics ~quality_adj in
      let p_de_valuation = Mreit.value_by_price_to_de ~mreit:mreit_metrics ~price:market.price ~quality_adj in
      let ddm_valuation = value_by_ddm ~market ~cost_of_capital ~growth_rate:0.0 in

      (* Fair value for mREITs *)
      let fair_value = Mreit.blend_mreit_fair_value
        ~p_bv_val:p_bv_valuation
        ~p_de_val:p_de_valuation
        ~ddm_val:ddm_valuation
      in

      let upside_potential =
        if market.price > 0.0 then (fair_value -. market.price) /. market.price else 0.0
      in

      let signal = determine_signal ~price:market.price ~fair_value ~quality in

      (* Placeholder equity REIT valuations (not meaningful for mREITs) *)
      let p_ffo_valuation = PriceToFFO { p_ffo = 0.0; sector_avg = 0.0; implied_value = 0.0 } in
      let p_affo_valuation = PriceToAFFO { p_affo = 0.0; sector_avg = 0.0; implied_value = 0.0 } in
      let nav_valuation = NAVMethod { nav_per_share = 0.0; premium_discount = 0.0;
                                       target_premium = 0.0; implied_value = 0.0 } in

      {
        ticker = market.ticker;
        price = market.price;
        reit_type = MortgageREIT;
        ffo_metrics;
        mreit_metrics = Some mreit_metrics;
        nav;
        cost_of_capital;
        p_ffo_valuation;
        p_affo_valuation;
        nav_valuation;
        ddm_valuation;
        p_bv_valuation = Some p_bv_valuation;
        p_de_valuation = Some p_de_valuation;
        fair_value;
        upside_potential;
        quality;
        signal;
      }

  | EquityREIT | HybridREIT ->
      (* Standard equity REIT valuation *)
      let quality = Quality.calculate_quality ~financial ~market ~ffo:ffo_metrics in

      (* Estimate growth rate from same-store NOI growth *)
      let growth_rate = max 0.0 (min 0.05 financial.same_store_noi_growth) in

      (* Run all valuation methods *)
      let p_ffo_valuation = value_by_p_ffo ~ffo:ffo_metrics ~market ~quality in
      let p_affo_valuation = value_by_p_affo ~ffo:ffo_metrics ~market ~quality in
      let nav_valuation = value_by_nav ~nav ~market ~quality in
      let ddm_valuation = value_by_ddm ~market ~cost_of_capital ~growth_rate in

      (* Blend fair value with sector-aware weights *)
      let fair_value = blend_fair_value
        ~sector:market.sector
        ~p_ffo_val:p_ffo_valuation
        ~p_affo_val:p_affo_valuation
        ~nav_val:nav_valuation
        ~ddm_val:ddm_valuation
      in

      let upside_potential =
        if market.price > 0.0 then (fair_value -. market.price) /. market.price else 0.0
      in

      let signal = determine_signal ~price:market.price ~fair_value ~quality in

      {
        ticker = market.ticker;
        price = market.price;
        reit_type = market.reit_type;
        ffo_metrics;
        mreit_metrics = None;
        nav;
        cost_of_capital;
        p_ffo_valuation;
        p_affo_valuation;
        nav_valuation;
        ddm_valuation;
        p_bv_valuation = None;
        p_de_valuation = None;
        fair_value;
        upside_potential;
        quality;
        signal;
      }

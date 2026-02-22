(* Skew trading strategies - construction and management *)

open Types
open Skew_measurement

(* ========================================================================== *)
(* Black-Scholes Helpers *)
(* ========================================================================== *)

let erf x =
  let a1 =  0.254829592 in
  let a2 = -0.284496736 in
  let a3 =  1.421413741 in
  let a4 = -1.453152027 in
  let a5 =  1.061405429 in
  let p  =  0.3275911 in
  let sign = if x < 0.0 then -1.0 else 1.0 in
  let x = abs_float x in
  let t = 1.0 /. (1.0 +. p *. x) in
  let y = 1.0 -. (((((a5 *. t +. a4) *. t) +. a3) *. t +. a2) *. t +. a1) *. t *. exp (-. x *. x) in
  sign *. y

let normal_cdf x =
  0.5 *. (1.0 +. erf (x /. sqrt 2.0))

(* ========================================================================== *)
(* Black-Scholes Pricing and Greeks *)
(* ========================================================================== *)

let bs_price ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  if expiry <= 0.0 || volatility <= 0.0 then 0.0
  else begin
    let d1 = (log (spot /. strike) +. (rate -. dividend +. 0.5 *. volatility *. volatility) *. expiry)
             /. (volatility *. sqrt expiry) in
    let d2 = d1 -. volatility *. sqrt expiry in

    match option_type with
    | Call ->
        spot *. exp (-.dividend *. expiry) *. normal_cdf d1 -.
        strike *. exp (-.rate *. expiry) *. normal_cdf d2
    | Put ->
        strike *. exp (-.rate *. expiry) *. normal_cdf (-.d2) -.
        spot *. exp (-.dividend *. expiry) *. normal_cdf (-.d1)
  end

let bs_greeks ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  if expiry <= 0.0 || volatility <= 0.0 then
    { delta = 0.0; gamma = 0.0; vega = 0.0; theta = 0.0; rho = 0.0 }
  else begin
    let d1 = (log (spot /. strike) +. (rate -. dividend +. 0.5 *. volatility *. volatility) *. expiry)
             /. (volatility *. sqrt expiry) in
    let d2 = d1 -. volatility *. sqrt expiry in

    (* Normal PDF *)
    let n_d1 = (1.0 /. sqrt (2.0 *. Float.pi)) *. exp (-.0.5 *. d1 *. d1) in

    (* Delta *)
    let delta = match option_type with
      | Call -> exp (-.dividend *. expiry) *. normal_cdf d1
      | Put -> exp (-.dividend *. expiry) *. (normal_cdf d1 -. 1.0)
    in

    (* Gamma (same for calls and puts) *)
    let gamma = (exp (-.dividend *. expiry) *. n_d1) /. (spot *. volatility *. sqrt expiry) in

    (* Vega *)
    let vega = spot *. exp (-.dividend *. expiry) *. n_d1 *. sqrt expiry in

    (* Theta *)
    let theta_part1 = -.(spot *. n_d1 *. volatility *. exp (-.dividend *. expiry)) /. (2.0 *. sqrt expiry) in
    let theta_part2 = match option_type with
      | Call ->
          -.rate *. strike *. exp (-.rate *. expiry) *. normal_cdf d2 +.
          dividend *. spot *. exp (-.dividend *. expiry) *. normal_cdf d1
      | Put ->
          rate *. strike *. exp (-.rate *. expiry) *. normal_cdf (-.d2) -.
          dividend *. spot *. exp (-.dividend *. expiry) *. normal_cdf (-.d1)
    in
    let theta = theta_part1 +. theta_part2 in

    (* Rho *)
    let rho = match option_type with
      | Call -> strike *. expiry *. exp (-.rate *. expiry) *. normal_cdf d2
      | Put -> -.strike *. expiry *. exp (-.rate *. expiry) *. normal_cdf (-.d2)
    in

    { delta; gamma; vega; theta; rho }
  end

(* ========================================================================== *)
(* Risk Reversal *)
(* ========================================================================== *)

let build_risk_reversal vol_surface underlying_data ~rate ~expiry ~delta_target ~direction ~notional =
  (*
    Risk Reversal (25-delta example):
    - Long direction: Buy 25Δ call, Sell 25Δ put
    - Short direction: Sell 25Δ call, Buy 25Δ put

    Profits from changes in skew (RR25)
  *)
  let spot = underlying_data.spot_price in
  let dividend = underlying_data.dividend_yield in

  (* Find 25-delta strikes *)
  let call_strike = match find_delta_strike Call ~target_delta:delta_target ~spot ~expiry ~rate ~dividend vol_surface with
    | Some k -> k
    | None -> spot *. 1.1  (* Fallback *)
  in

  let put_strike = match find_delta_strike Put ~target_delta:(-.delta_target) ~spot ~expiry ~rate ~dividend vol_surface with
    | Some k -> k
    | None -> spot *. 0.9  (* Fallback *)
  in

  (* Get IVs and prices *)
  let call_iv = get_iv_from_surface vol_surface ~strike:call_strike ~expiry ~spot in
  let call_price = bs_price ~option_type:Call ~spot ~strike:call_strike ~expiry ~rate ~dividend ~volatility:call_iv in
  let call_greeks = bs_greeks ~option_type:Call ~spot ~strike:call_strike ~expiry ~rate ~dividend ~volatility:call_iv in

  let put_iv = get_iv_from_surface vol_surface ~strike:put_strike ~expiry ~spot in
  let put_price = bs_price ~option_type:Put ~spot ~strike:put_strike ~expiry ~rate ~dividend ~volatility:put_iv in
  let put_greeks = bs_greeks ~option_type:Put ~spot ~strike:put_strike ~expiry ~rate ~dividend ~volatility:put_iv in

  (* Determine quantities based on direction *)
  let (call_qty, put_qty) = match direction with
    | `Long ->
        (* Long skew: buy call, sell put *)
        let qty = notional /. call_price in
        (qty, -.qty)
    | `Short ->
        (* Short skew: sell call, buy put *)
        let qty = notional /. put_price in
        (-.qty, qty)
  in

  (* Build legs *)
  let legs = [|
    {
      option_type = Call;
      strike = call_strike;
      expiry;
      quantity = call_qty;
      entry_price = call_price;
      delta = call_greeks.delta *. call_qty;
      vega = call_greeks.vega *. call_qty;
      gamma = call_greeks.gamma *. call_qty;
    };
    {
      option_type = Put;
      strike = put_strike;
      expiry;
      quantity = put_qty;
      entry_price = put_price;
      delta = put_greeks.delta *. put_qty;
      vega = put_greeks.vega *. put_qty;
      gamma = put_greeks.gamma *. put_qty;
    };
  |] in

  (* Compute totals *)
  let total_cost = call_price *. call_qty +. put_price *. put_qty in
  let total_delta = call_greeks.delta *. call_qty +. put_greeks.delta *. put_qty in
  let total_vega = call_greeks.vega *. call_qty +. put_greeks.vega *. put_qty in
  let total_gamma = call_greeks.gamma *. call_qty +. put_greeks.gamma *. put_qty in

  {
    ticker = underlying_data.ticker;
    strategy_type = RiskReversal { buy_strike = call_strike; sell_strike = put_strike; ratio = 1.0 };
    legs;
    entry_date = Unix.time ();
    entry_spot = spot;
    total_cost;
    total_delta;
    total_vega;
    total_gamma;
    target_pnl = None;
    stop_loss = None;
  }

(* ========================================================================== *)
(* Butterfly Spread *)
(* ========================================================================== *)

let build_butterfly vol_surface underlying_data ~rate ~expiry ~strikes:(low, mid, high) ~notional =
  (*
    Butterfly: Buy 1 low, Sell 2 mid, Buy 1 high
    Profits from smile flattening
  *)
  let spot = underlying_data.spot_price in
  let dividend = underlying_data.dividend_yield in

  (* Price options *)
  let price_option strike =
    let iv = get_iv_from_surface vol_surface ~strike ~expiry ~spot in
    let option_type = if strike < spot then Put else Call in
    let price = bs_price ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility:iv in
    let greeks = bs_greeks ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility:iv in
    (option_type, price, greeks)
  in

  let (low_type, low_price, low_greeks) = price_option low in
  let (mid_type, mid_price, mid_greeks) = price_option mid in
  let (high_type, high_price, high_greeks) = price_option high in

  (* Quantities: +1, -2, +1 (normalized to notional) *)
  let unit_cost = low_price -. 2.0 *. mid_price +. high_price in
  let multiplier = if unit_cost > 0.0 then notional /. unit_cost else 1.0 in

  let low_qty = multiplier in
  let mid_qty = -.2.0 *. multiplier in
  let high_qty = multiplier in

  let legs = [|
    {
      option_type = low_type;
      strike = low;
      expiry;
      quantity = low_qty;
      entry_price = low_price;
      delta = low_greeks.delta *. low_qty;
      vega = low_greeks.vega *. low_qty;
      gamma = low_greeks.gamma *. low_qty;
    };
    {
      option_type = mid_type;
      strike = mid;
      expiry;
      quantity = mid_qty;
      entry_price = mid_price;
      delta = mid_greeks.delta *. mid_qty;
      vega = mid_greeks.vega *. mid_qty;
      gamma = mid_greeks.gamma *. mid_qty;
    };
    {
      option_type = high_type;
      strike = high;
      expiry;
      quantity = high_qty;
      entry_price = high_price;
      delta = high_greeks.delta *. high_qty;
      vega = high_greeks.vega *. high_qty;
      gamma = high_greeks.gamma *. high_qty;
    };
  |] in

  let total_cost = Array.fold_left (fun acc (leg : option_leg) ->
    acc +. leg.entry_price *. leg.quantity
  ) 0.0 legs in

  let total_delta = Array.fold_left (fun acc (leg : option_leg) -> acc +. leg.delta) 0.0 legs in
  let total_vega = Array.fold_left (fun acc (leg : option_leg) -> acc +. leg.vega) 0.0 legs in
  let total_gamma = Array.fold_left (fun acc (leg : option_leg) -> acc +. leg.gamma) 0.0 legs in

  {
    ticker = underlying_data.ticker;
    strategy_type = Butterfly { low_strike = low; mid_strike = mid; high_strike = high };
    legs;
    entry_date = Unix.time ();
    entry_spot = spot;
    total_cost;
    total_delta;
    total_vega;
    total_gamma;
    target_pnl = None;
    stop_loss = None;
  }

(* ========================================================================== *)
(* Ratio Spread *)
(* ========================================================================== *)

let build_ratio_spread vol_surface underlying_data ~rate ~expiry ~option_type ~strikes:(long_strike, short_strike) ~ratio ~notional =
  (*
    Ratio Spread: Buy N at long_strike, Sell M at short_strike
    Example: Buy 2 OTM puts, Sell 1 ATM put (2:1 ratio)
  *)
  let spot = underlying_data.spot_price in
  let dividend = underlying_data.dividend_yield in

  let long_iv = get_iv_from_surface vol_surface ~strike:long_strike ~expiry ~spot in
  let long_price = bs_price ~option_type ~spot ~strike:long_strike ~expiry ~rate ~dividend ~volatility:long_iv in
  let long_greeks = bs_greeks ~option_type ~spot ~strike:long_strike ~expiry ~rate ~dividend ~volatility:long_iv in

  let short_iv = get_iv_from_surface vol_surface ~strike:short_strike ~expiry ~spot in
  let short_price = bs_price ~option_type ~spot ~strike:short_strike ~expiry ~rate ~dividend ~volatility:short_iv in
  let short_greeks = bs_greeks ~option_type ~spot ~strike:short_strike ~expiry ~rate ~dividend ~volatility:short_iv in

  (* Scale to notional *)
  let long_qty = notional /. long_price in
  let short_qty = -.long_qty *. (float_of_int ratio) in

  let legs = [|
    {
      option_type;
      strike = long_strike;
      expiry;
      quantity = long_qty;
      entry_price = long_price;
      delta = long_greeks.delta *. long_qty;
      vega = long_greeks.vega *. long_qty;
      gamma = long_greeks.gamma *. long_qty;
    };
    {
      option_type;
      strike = short_strike;
      expiry;
      quantity = short_qty;
      entry_price = short_price;
      delta = short_greeks.delta *. short_qty;
      vega = short_greeks.vega *. short_qty;
      gamma = short_greeks.gamma *. short_qty;
    };
  |] in

  let total_cost = long_price *. long_qty +. short_price *. short_qty in
  let total_delta = long_greeks.delta *. long_qty +. short_greeks.delta *. short_qty in
  let total_vega = long_greeks.vega *. long_qty +. short_greeks.vega *. short_qty in
  let total_gamma = long_greeks.gamma *. long_qty +. short_greeks.gamma *. short_qty in

  {
    ticker = underlying_data.ticker;
    strategy_type = RatioSpread { long_strike; short_strike; ratio };
    legs;
    entry_date = Unix.time ();
    entry_spot = spot;
    total_cost;
    total_delta;
    total_vega;
    total_gamma;
    target_pnl = None;
    stop_loss = None;
  }

(* ========================================================================== *)
(* Calendar Spread *)
(* ========================================================================== *)

let build_calendar_spread vol_surface underlying_data ~rate ~expiries:(near, far) ~strike ~option_type ~notional =
  let spot = underlying_data.spot_price in
  let dividend = underlying_data.dividend_yield in

  let near_iv = get_iv_from_surface vol_surface ~strike ~expiry:near ~spot in
  let near_price = bs_price ~option_type ~spot ~strike ~expiry:near ~rate ~dividend ~volatility:near_iv in
  let near_greeks = bs_greeks ~option_type ~spot ~strike ~expiry:near ~rate ~dividend ~volatility:near_iv in

  let far_iv = get_iv_from_surface vol_surface ~strike ~expiry:far ~spot in
  let far_price = bs_price ~option_type ~spot ~strike ~expiry:far ~rate ~dividend ~volatility:far_iv in
  let far_greeks = bs_greeks ~option_type ~spot ~strike ~expiry:far ~rate ~dividend ~volatility:far_iv in

  (* Sell near, buy far *)
  let near_qty = -.notional /. near_price in
  let far_qty = notional /. far_price in

  let legs = [|
    {
      option_type;
      strike;
      expiry = near;
      quantity = near_qty;
      entry_price = near_price;
      delta = near_greeks.delta *. near_qty;
      vega = near_greeks.vega *. near_qty;
      gamma = near_greeks.gamma *. near_qty;
    };
    {
      option_type;
      strike;
      expiry = far;
      quantity = far_qty;
      entry_price = far_price;
      delta = far_greeks.delta *. far_qty;
      vega = far_greeks.vega *. far_qty;
      gamma = far_greeks.gamma *. far_qty;
    };
  |] in

  let total_cost = near_price *. near_qty +. far_price *. far_qty in
  let total_delta = near_greeks.delta *. near_qty +. far_greeks.delta *. far_qty in
  let total_vega = near_greeks.vega *. near_qty +. far_greeks.vega *. far_qty in
  let total_gamma = near_greeks.gamma *. near_qty +. far_greeks.gamma *. far_qty in

  {
    ticker = underlying_data.ticker;
    strategy_type = CalendarSpread { near_expiry = near; far_expiry = far; strike; option_type };
    legs;
    entry_date = Unix.time ();
    entry_spot = spot;
    total_cost;
    total_delta;
    total_vega;
    total_gamma;
    target_pnl = None;
    stop_loss = None;
  }

(* ========================================================================== *)
(* Position Management *)
(* ========================================================================== *)

let position_greeks position ~current_spot ~vol_surface ~rate =
  let dividend = 0.0 in  (* Simplified *)

  let delta_sum = ref 0.0 in
  let gamma_sum = ref 0.0 in
  let vega_sum = ref 0.0 in
  let theta_sum = ref 0.0 in
  let rho_sum = ref 0.0 in

  Array.iter (fun (leg : option_leg) ->
    let iv = get_iv_from_surface vol_surface ~strike:leg.strike ~expiry:leg.expiry ~spot:current_spot in
    let greeks = bs_greeks ~option_type:leg.option_type ~spot:current_spot ~strike:leg.strike
      ~expiry:leg.expiry ~rate ~dividend ~volatility:iv in

    delta_sum := !delta_sum +. greeks.delta *. leg.quantity;
    gamma_sum := !gamma_sum +. greeks.gamma *. leg.quantity;
    vega_sum := !vega_sum +. greeks.vega *. leg.quantity;
    theta_sum := !theta_sum +. greeks.theta *. leg.quantity;
    rho_sum := !rho_sum +. greeks.rho *. leg.quantity;
  ) position.legs;

  {
    delta = !delta_sum;
    gamma = !gamma_sum;
    vega = !vega_sum;
    theta = !theta_sum;
    rho = !rho_sum;
  }

let position_pnl position ~current_spot ~current_vol_surface ~rate =
  let dividend = 0.0 in

  let current_value = Array.fold_left (fun acc (leg : option_leg) ->
    let iv = get_iv_from_surface current_vol_surface ~strike:leg.strike ~expiry:leg.expiry ~spot:current_spot in
    let current_price = bs_price ~option_type:leg.option_type ~spot:current_spot ~strike:leg.strike
      ~expiry:leg.expiry ~rate ~dividend ~volatility:iv in
    acc +. current_price *. leg.quantity
  ) 0.0 position.legs in

  current_value -. position.total_cost

let delta_hedge position ~current_spot ~vol_surface ~rate =
  (* Add stock hedge to neutralize delta *)
  let _current_greeks = position_greeks position ~current_spot ~vol_surface ~rate in

  (* Delta hedge would require adding underlying position - simplified for now *)
  position

let check_risk_limits position ~config =
  abs_float position.total_vega <= config.target_vega_notional *. 1.5 &&
  abs_float position.total_gamma <= config.max_gamma_risk

(* Portfolio-Level Greeks Analysis *)

open Types

(* Helper: Get volatility from vol surface
   This will be implemented properly in vol_surface.ml
   For now, use a simple placeholder
*)
let get_vol_from_surface (vol_surface : vol_surface) ~strike ~expiry ~spot =
  (* TODO: This will be replaced with actual SVI/SABR interpolation *)
  match vol_surface with
  | SVI params ->
      (* Find closest expiry *)
      if Array.length params = 0 then
        failwith "Greeks.get_vol_from_surface: empty SVI params"
      else
        (* For now, just use the first param's implied vol calculation *)
        (* This is a placeholder - will be replaced by proper SVI formula *)
        let param = params.(0) in
        let log_moneyness = log (strike /. spot) in
        let delta_k = log_moneyness -. param.m in
        let sqrt_term = sqrt (delta_k *. delta_k +. param.sigma *. param.sigma) in
        let total_var = param.a +. param.b *. (param.rho *. delta_k +. sqrt_term) in
        sqrt (total_var /. expiry)
  | SABR params ->
      (* Placeholder for SABR *)
      if Array.length params = 0 then
        failwith "Greeks.get_vol_from_surface: empty SABR params"
      else
        params.(0).alpha  (* Very crude placeholder *)

(* Compute Greeks for a single option position *)
let option_greeks (spec : option_spec) ~underlying_data ~volatility ~rate =
  Black_scholes.calculate_greeks
    spec.option_type
    ~spot:underlying_data.spot_price
    ~strike:spec.strike
    ~expiry:spec.expiry
    ~rate
    ~dividend:underlying_data.dividend_yield
    ~volatility

(* Greeks for a single hedge strategy *)
let strategy_greeks strategy_type ~underlying_data ~vol_surface ~rate ~contracts =
  let spot = underlying_data.spot_price in
  let contracts_float = float_of_int contracts in

  match strategy_type with
  | ProtectivePut { put_strike } ->
      (* Long put position *)
      let put_spec = {
        ticker = underlying_data.ticker;
        option_type = Put;
        strike = put_strike;
        expiry = 0.25;  (* Placeholder - will come from strategy *)
        exercise_style = European;
      } in
      let vol = get_vol_from_surface vol_surface ~strike:put_strike ~expiry:0.25 ~spot in
      let greeks = option_greeks put_spec ~underlying_data ~volatility:vol ~rate in
      scale_greeks greeks contracts_float

  | Collar { put_strike; call_strike } ->
      (* Long put + short call *)
      let put_spec = {
        ticker = underlying_data.ticker;
        option_type = Put;
        strike = put_strike;
        expiry = 0.25;
        exercise_style = European;
      } in
      let call_spec = {
        ticker = underlying_data.ticker;
        option_type = Call;
        strike = call_strike;
        expiry = 0.25;
        exercise_style = European;
      } in

      let put_vol = get_vol_from_surface vol_surface ~strike:put_strike ~expiry:0.25 ~spot in
      let call_vol = get_vol_from_surface vol_surface ~strike:call_strike ~expiry:0.25 ~spot in

      let put_greeks = option_greeks put_spec ~underlying_data ~volatility:put_vol ~rate in
      let call_greeks = option_greeks call_spec ~underlying_data ~volatility:call_vol ~rate in

      (* Long put + short call *)
      let combined = add_greeks put_greeks (scale_greeks call_greeks (-1.0)) in
      scale_greeks combined contracts_float

  | VerticalSpread { long_strike; short_strike } ->
      (* Long put at long_strike + short put at short_strike *)
      let long_spec = {
        ticker = underlying_data.ticker;
        option_type = Put;
        strike = long_strike;
        expiry = 0.25;
        exercise_style = European;
      } in
      let short_spec = {
        ticker = underlying_data.ticker;
        option_type = Put;
        strike = short_strike;
        expiry = 0.25;
        exercise_style = European;
      } in

      let long_vol = get_vol_from_surface vol_surface ~strike:long_strike ~expiry:0.25 ~spot in
      let short_vol = get_vol_from_surface vol_surface ~strike:short_strike ~expiry:0.25 ~spot in

      let long_greeks = option_greeks long_spec ~underlying_data ~volatility:long_vol ~rate in
      let short_greeks = option_greeks short_spec ~underlying_data ~volatility:short_vol ~rate in

      (* Long - short *)
      let combined = add_greeks long_greeks (scale_greeks short_greeks (-1.0)) in
      scale_greeks combined contracts_float

  | CoveredCall { call_strike } ->
      (* Short call position (negative Greeks) *)
      let call_spec = {
        ticker = underlying_data.ticker;
        option_type = Call;
        strike = call_strike;
        expiry = 0.25;
        exercise_style = European;
      } in
      let vol = get_vol_from_surface vol_surface ~strike:call_strike ~expiry:0.25 ~spot in
      let greeks = option_greeks call_spec ~underlying_data ~volatility:vol ~rate in
      (* Short position: negate the Greeks *)
      scale_greeks greeks (-. contracts_float)

(* Portfolio Greeks: sum of all strategies *)
let portfolio_greeks (strategies : hedge_strategy list) =
  List.fold_left
    (fun acc strategy -> add_greeks acc strategy.greeks)
    zero_greeks
    strategies

(* Check if portfolio is delta-neutral *)
let is_delta_neutral greeks ~tolerance =
  abs_float greeks.delta <= tolerance

(* Check if portfolio is gamma-neutral *)
let is_gamma_neutral greeks ~tolerance =
  abs_float greeks.gamma <= tolerance

(* Greeks sensitivity analysis via finite differences *)
let greeks_bumps (spec : option_spec) ~underlying_data ~vol_surface ~rate ~bump_size =
  let spot = underlying_data.spot_price in
  let vol = get_vol_from_surface vol_surface ~strike:spec.strike ~expiry:spec.expiry ~spot in

  (* Base Greeks *)
  let base_greeks = option_greeks spec ~underlying_data ~volatility:vol ~rate in

  (* Spot bump *)
  let spot_up_data = { underlying_data with spot_price = spot *. (1.0 +. bump_size) } in
  let spot_up_greeks = option_greeks spec ~underlying_data:spot_up_data ~volatility:vol ~rate in

  let spot_down_data = { underlying_data with spot_price = spot *. (1.0 -. bump_size) } in
  let spot_down_greeks = option_greeks spec ~underlying_data:spot_down_data ~volatility:vol ~rate in

  (* Vol bump *)
  let vol_up = vol *. (1.0 +. bump_size) in
  let vol_up_greeks = option_greeks spec ~underlying_data ~volatility:vol_up ~rate in

  let vol_down = vol *. (1.0 -. bump_size) in
  let vol_down_greeks = option_greeks spec ~underlying_data ~volatility:vol_down ~rate in

  (* Rate bump *)
  let rate_up = rate +. bump_size in
  let rate_up_greeks = option_greeks spec ~underlying_data ~volatility:vol ~rate:rate_up in

  let rate_down = rate -. bump_size in
  let rate_down_greeks = option_greeks spec ~underlying_data ~volatility:vol ~rate:rate_down in

  (* Time bump (reduce expiry) *)
  let time_down_spec = { spec with expiry = spec.expiry -. bump_size } in
  let time_down_greeks =
    if time_down_spec.expiry > 0.0 then
      option_greeks time_down_spec ~underlying_data ~volatility:vol ~rate
    else
      zero_greeks
  in

  [
    ("base", base_greeks);
    ("spot_up", spot_up_greeks);
    ("spot_down", spot_down_greeks);
    ("vol_up", vol_up_greeks);
    ("vol_down", vol_down_greeks);
    ("rate_up", rate_up_greeks);
    ("rate_down", rate_down_greeks);
    ("time_down", time_down_greeks);
  ]

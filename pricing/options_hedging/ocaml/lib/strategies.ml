(* Hedge Strategy Construction and Pricing *)

open Types

(* Compute strategy payoff at expiry *)
let strategy_payoff strategy_type ~underlying_position ~spot_at_expiry =
  let stock_value = underlying_position *. spot_at_expiry in

  match strategy_type with
  | ProtectivePut { put_strike } ->
      (* Long stock + long put *)
      (* Payoff = max(S, K) × position_size *)
      underlying_position *. max spot_at_expiry put_strike

  | Collar { put_strike; call_strike } ->
      (* Long stock + long put + short call *)
      (* Payoff is bounded: put_strike <= payoff <= call_strike *)
      let clamped_spot = max put_strike (min spot_at_expiry call_strike) in
      underlying_position *. clamped_spot

  | VerticalSpread { long_strike; short_strike } ->
      (* Long stock + long put @ long_strike + short put @ short_strike *)
      (* Protection between short_strike and long_strike *)
      let put_long_payoff = max 0.0 (long_strike -. spot_at_expiry) in
      let put_short_payoff = max 0.0 (short_strike -. spot_at_expiry) in
      stock_value +. underlying_position *. (put_long_payoff -. put_short_payoff)

  | CoveredCall { call_strike } ->
      (* Long stock + short call *)
      (* Upside capped at call_strike *)
      let call_payoff = max 0.0 (spot_at_expiry -. call_strike) in
      stock_value -. underlying_position *. call_payoff

(* Price individual option *)
let price_option option_type ~strike ~expiry ~underlying_data ~vol_surface ~rate =
  let spot = underlying_data.spot_price in
  let dividend = underlying_data.dividend_yield in
  let vol = Vol_surface.interpolate_vol vol_surface ~strike ~expiry ~spot in

  Black_scholes.price_european_option
    ~option_type
    ~spot
    ~strike
    ~expiry
    ~rate
    ~dividend
    ~volatility:vol

(* Price all options in a strategy *)
let price_strategy_options strategy_type ~expiry ~underlying_data ~vol_surface ~rate ~contracts =
  let contracts_float = float_of_int contracts in

  match strategy_type with
  | ProtectivePut { put_strike } ->
      (* Buy put: positive cost *)
      let put_price = price_option Put ~strike:put_strike ~expiry ~underlying_data ~vol_surface ~rate in
      put_price *. contracts_float *. 100.0  (* × 100 shares per contract *)

  | Collar { put_strike; call_strike } ->
      (* Buy put, sell call: net cost (can be negative if call premium > put premium) *)
      let put_price = price_option Put ~strike:put_strike ~expiry ~underlying_data ~vol_surface ~rate in
      let call_price = price_option Call ~strike:call_strike ~expiry ~underlying_data ~vol_surface ~rate in
      (put_price -. call_price) *. contracts_float *. 100.0

  | VerticalSpread { long_strike; short_strike } ->
      (* Buy put @ long_strike, sell put @ short_strike *)
      let long_price = price_option Put ~strike:long_strike ~expiry ~underlying_data ~vol_surface ~rate in
      let short_price = price_option Put ~strike:short_strike ~expiry ~underlying_data ~vol_surface ~rate in
      (long_price -. short_price) *. contracts_float *. 100.0

  | CoveredCall { call_strike } ->
      (* Sell call: negative cost (income) *)
      let call_price = price_option Call ~strike:call_strike ~expiry ~underlying_data ~vol_surface ~rate in
      -. call_price *. contracts_float *. 100.0

(* Simulate payoff distribution using Monte Carlo *)
let strategy_payoff_distribution strategy ~underlying_data ~vol_surface ~rate ~num_paths =
  let spot = underlying_data.spot_price in
  let dividend = underlying_data.dividend_yield in
  let expiry = strategy.expiry in

  (* Get average volatility for the strategy *)
  let vol = match strategy.strategy_type with
  | ProtectivePut { put_strike } ->
      Vol_surface.interpolate_vol vol_surface ~strike:put_strike ~expiry ~spot
  | Collar { put_strike; _ } ->
      Vol_surface.interpolate_vol vol_surface ~strike:put_strike ~expiry ~spot
  | VerticalSpread { long_strike; _ } ->
      Vol_surface.interpolate_vol vol_surface ~strike:long_strike ~expiry ~spot
  | CoveredCall { call_strike } ->
      Vol_surface.interpolate_vol vol_surface ~strike:call_strike ~expiry ~spot
  in

  (* Simulate terminal stock prices *)
  let num_steps = 50 in  (* Fine enough for terminal distribution *)
  let paths = Monte_carlo.simulate_price_paths
    ~spot ~rate ~dividend ~volatility:vol ~expiry ~num_steps ~num_paths
  in

  (* Compute payoff for each path *)
  let payoffs = Array.init num_paths (fun i ->
    let terminal_price = paths.(i).(num_steps) in
    let underlying_position = float_of_int strategy.contracts *. 100.0 in
    strategy_payoff strategy.strategy_type ~underlying_position ~spot_at_expiry:terminal_price
  ) in

  payoffs

(* Compute protection level from payoff distribution *)
let compute_protection_level ~payoff_distribution ~confidence =
  (* Sort payoffs *)
  let sorted = Array.copy payoff_distribution in
  Array.sort Float.compare sorted;

  (* Find percentile (lower tail for protection) *)
  let idx = int_of_float ((1.0 -. confidence) *. float_of_int (Array.length sorted)) in
  let idx = max 0 (min idx (Array.length sorted - 1)) in

  sorted.(idx)

(* Protective Put Strategy *)
let protective_put ~underlying_position ~put_strike ~expiry ~underlying_data ~vol_surface ~rate =
  let contracts = int_of_float (underlying_position /. 100.0) in  (* Round to contracts *)
  let strategy_type = ProtectivePut { put_strike } in

  (* Price the options *)
  let cost = price_strategy_options strategy_type ~expiry ~underlying_data ~vol_surface ~rate ~contracts in

  (* Compute Greeks *)
  let greeks = Greeks.strategy_greeks strategy_type ~underlying_data ~vol_surface ~rate ~contracts in

  (* Estimate protection level *)
  let payoff_dist = strategy_payoff_distribution
    { strategy_type; expiry; contracts; cost; greeks; protection_level = 0.0 }
    ~underlying_data ~vol_surface ~rate ~num_paths:1000
  in
  let protection_level = compute_protection_level ~payoff_distribution:payoff_dist ~confidence:0.95 in

  {
    strategy_type;
    expiry;
    contracts;
    cost;
    greeks;
    protection_level;
  }

(* Collar Strategy *)
let collar ~underlying_position ~put_strike ~call_strike ~expiry ~underlying_data ~vol_surface ~rate =
  let contracts = int_of_float (underlying_position /. 100.0) in
  let strategy_type = Collar { put_strike; call_strike } in

  let cost = price_strategy_options strategy_type ~expiry ~underlying_data ~vol_surface ~rate ~contracts in
  let greeks = Greeks.strategy_greeks strategy_type ~underlying_data ~vol_surface ~rate ~contracts in

  let payoff_dist = strategy_payoff_distribution
    { strategy_type; expiry; contracts; cost; greeks; protection_level = 0.0 }
    ~underlying_data ~vol_surface ~rate ~num_paths:1000
  in
  let protection_level = compute_protection_level ~payoff_distribution:payoff_dist ~confidence:0.95 in

  {
    strategy_type;
    expiry;
    contracts;
    cost;
    greeks;
    protection_level;
  }

(* Vertical Put Spread *)
let vertical_put_spread ~underlying_position ~long_put_strike ~short_put_strike ~expiry ~underlying_data ~vol_surface ~rate =
  let contracts = int_of_float (underlying_position /. 100.0) in
  let strategy_type = VerticalSpread { long_strike = long_put_strike; short_strike = short_put_strike } in

  let cost = price_strategy_options strategy_type ~expiry ~underlying_data ~vol_surface ~rate ~contracts in
  let greeks = Greeks.strategy_greeks strategy_type ~underlying_data ~vol_surface ~rate ~contracts in

  let payoff_dist = strategy_payoff_distribution
    { strategy_type; expiry; contracts; cost; greeks; protection_level = 0.0 }
    ~underlying_data ~vol_surface ~rate ~num_paths:1000
  in
  let protection_level = compute_protection_level ~payoff_distribution:payoff_dist ~confidence:0.95 in

  {
    strategy_type;
    expiry;
    contracts;
    cost;
    greeks;
    protection_level;
  }

(* Covered Call *)
let covered_call ~underlying_position ~call_strike ~expiry ~underlying_data ~vol_surface ~rate =
  let contracts = int_of_float (underlying_position /. 100.0) in
  let strategy_type = CoveredCall { call_strike } in

  let cost = price_strategy_options strategy_type ~expiry ~underlying_data ~vol_surface ~rate ~contracts in
  let greeks = Greeks.strategy_greeks strategy_type ~underlying_data ~vol_surface ~rate ~contracts in

  let payoff_dist = strategy_payoff_distribution
    { strategy_type; expiry; contracts; cost; greeks; protection_level = 0.0 }
    ~underlying_data ~vol_surface ~rate ~num_paths:1000
  in
  let protection_level = compute_protection_level ~payoff_distribution:payoff_dist ~confidence:0.95 in

  {
    strategy_type;
    expiry;
    contracts;
    cost;
    greeks;
    protection_level;
  }

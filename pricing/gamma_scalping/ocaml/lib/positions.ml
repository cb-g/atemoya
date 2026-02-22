(* Position builders for gamma scalping strategies *)

open Types

(** Helper functions for Greeks manipulation **)

(* Zero Greeks *)
let zero_greeks = {
  delta = 0.0;
  gamma = 0.0;
  theta = 0.0;
  vega = 0.0;
  rho = 0.0;
}

(* Add two Greeks structures *)
let add_greeks g1 g2 = {
  delta = g1.delta +. g2.delta;
  gamma = g1.gamma +. g2.gamma;
  theta = g1.theta +. g2.theta;
  vega = g1.vega +. g2.vega;
  rho = g1.rho +. g2.rho;
}

(* Scale Greeks by a factor *)
let scale_greeks greeks factor = {
  delta = greeks.delta *. factor;
  gamma = greeks.gamma *. factor;
  theta = greeks.theta *. factor;
  vega = greeks.vega *. factor;
  rho = greeks.rho *. factor;
}

(** Position constructors **)

(* Build a single option position *)
let build_single_option ~spot ~option_type ~strike ~expiry ~volatility ~rate ~dividend ~contracts =
  let contracts_float = float_of_int contracts in

  (* Price the option *)
  let premium = Pricing.price_option
    ~option_type
    ~spot
    ~strike
    ~expiry
    ~rate
    ~dividend
    ~volatility
  in

  (* Calculate Greeks *)
  let greeks = Pricing.compute_greeks
    ~option_type
    ~spot
    ~strike
    ~expiry
    ~rate
    ~dividend
    ~volatility
  in

  (* Scale by number of contracts *)
  let total_premium = premium *. contracts_float in
  let scaled_greeks = scale_greeks greeks contracts_float in

  (total_premium, scaled_greeks)

(* Build a straddle: long ATM call + long ATM put

   Characteristics:
   - Maximum gamma near ATM
   - High theta decay
   - Delta-neutral at inception
   - Profits from realized volatility > implied volatility
*)
let build_straddle ~spot ~strike ~expiry ~volatility ~rate ~dividend ~contracts =
  let contracts_float = float_of_int contracts in

  (* Price and calculate Greeks for call *)
  let call_premium = Pricing.price_option
    ~option_type:Call
    ~spot
    ~strike
    ~expiry
    ~rate
    ~dividend
    ~volatility
  in
  let call_greeks = Pricing.compute_greeks
    ~option_type:Call
    ~spot
    ~strike
    ~expiry
    ~rate
    ~dividend
    ~volatility
  in

  (* Price and calculate Greeks for put *)
  let put_premium = Pricing.price_option
    ~option_type:Put
    ~spot
    ~strike
    ~expiry
    ~rate
    ~dividend
    ~volatility
  in
  let put_greeks = Pricing.compute_greeks
    ~option_type:Put
    ~spot
    ~strike
    ~expiry
    ~rate
    ~dividend
    ~volatility
  in

  (* Combine: long call + long put *)
  let total_premium = (call_premium +. put_premium) *. contracts_float in
  let combined_greeks = add_greeks call_greeks put_greeks in
  let scaled_greeks = scale_greeks combined_greeks contracts_float in

  (total_premium, scaled_greeks)

(* Build a strangle: long OTM call + long OTM put

   Characteristics:
   - Lower gamma than straddle (OTM options)
   - Lower theta decay (cheaper entry)
   - Requires larger moves to profit
   - Better risk/reward for big directional moves
*)
let build_strangle ~spot ~call_strike ~put_strike ~expiry ~volatility ~rate ~dividend ~contracts =
  let contracts_float = float_of_int contracts in

  (* Validate strikes: call should be OTM (above spot), put should be OTM (below spot) *)
  if call_strike <= spot then
    Printf.printf "Warning: call_strike (%.2f) should be > spot (%.2f) for OTM strangle\n" call_strike spot;
  if put_strike >= spot then
    Printf.printf "Warning: put_strike (%.2f) should be < spot (%.2f) for OTM strangle\n" put_strike spot;

  (* Price and calculate Greeks for OTM call *)
  let call_premium = Pricing.price_option
    ~option_type:Call
    ~spot
    ~strike:call_strike
    ~expiry
    ~rate
    ~dividend
    ~volatility
  in
  let call_greeks = Pricing.compute_greeks
    ~option_type:Call
    ~spot
    ~strike:call_strike
    ~expiry
    ~rate
    ~dividend
    ~volatility
  in

  (* Price and calculate Greeks for OTM put *)
  let put_premium = Pricing.price_option
    ~option_type:Put
    ~spot
    ~strike:put_strike
    ~expiry
    ~rate
    ~dividend
    ~volatility
  in
  let put_greeks = Pricing.compute_greeks
    ~option_type:Put
    ~spot
    ~strike:put_strike
    ~expiry
    ~rate
    ~dividend
    ~volatility
  in

  (* Combine: long call + long put *)
  let total_premium = (call_premium +. put_premium) *. contracts_float in
  let combined_greeks = add_greeks call_greeks put_greeks in
  let scaled_greeks = scale_greeks combined_greeks contracts_float in

  (total_premium, scaled_greeks)

(* Generic position Greeks calculator *)
let position_greeks ~position_type ~spot ~expiry ~volatility ~rate ~dividend ~contracts =
  match position_type with
  | Straddle { strike } ->
      build_straddle ~spot ~strike ~expiry ~volatility ~rate ~dividend ~contracts

  | Strangle { call_strike; put_strike } ->
      build_strangle ~spot ~call_strike ~put_strike ~expiry ~volatility ~rate ~dividend ~contracts

  | SingleOption { option_type; strike } ->
      build_single_option ~spot ~option_type ~strike ~expiry ~volatility ~rate ~dividend ~contracts

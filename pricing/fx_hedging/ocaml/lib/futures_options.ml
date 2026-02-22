(* Futures Options Pricing - Black-76 Model *)

open Types

(* Mathematical constants *)
let pi = 4.0 *. atan 1.0
let sqrt_2 = sqrt 2.0
let sqrt_2pi = sqrt (2.0 *. pi)

(* Error function approximation (Abramowitz and Stegun) *)
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

(* Standard normal CDF *)
let normal_cdf x =
  0.5 *. (1.0 +. erf (x /. sqrt_2))

(* Standard normal PDF *)
let normal_pdf x =
  exp (-0.5 *. x *. x) /. sqrt_2pi

(* Compute d1 and d2 from Black's model

   d₁ = [ln(F/K) + (σ²/2)T] / (σ√T)
   d₂ = d₁ - σ√T

   Note: No interest rate differential term (already in F)
*)
let compute_d1_d2 ~futures_price ~strike ~expiry ~volatility =
  if expiry <= 0.0 then
    failwith "Futures_options.compute_d1_d2: expiry must be positive"
  else if volatility <= 0.0 then
    failwith "Futures_options.compute_d1_d2: volatility must be positive"
  else if futures_price <= 0.0 then
    failwith "Futures_options.compute_d1_d2: futures_price must be positive"
  else if strike <= 0.0 then
    failwith "Futures_options.compute_d1_d2: strike must be positive"
  else
    let vol_sqrt_t = volatility *. sqrt expiry in
    let d1 =
      (log (futures_price /. strike) +. 0.5 *. volatility *. volatility *. expiry)
      /. vol_sqrt_t
    in
    let d2 = d1 -. vol_sqrt_t in
    (d1, d2)

(* Black-76 option pricing

   Call: C = e^(-rT) [F·N(d₁) - K·N(d₂)]
   Put:  P = e^(-rT) [K·N(-d₂) - F·N(-d₁)]

   Key differences from Black-Scholes:
   1. Uses futures price F instead of spot S
   2. No dividend/foreign rate term (already in futures)
   3. Both call and put discounted by e^(-rT)
*)
let black_price ~option_type ~futures_price ~strike ~expiry ~rate ~volatility =
  if expiry <= 0.0 then
    (* Option expired - return intrinsic value *)
    match option_type with
    | Call -> max 0.0 (futures_price -. strike)
    | Put -> max 0.0 (strike -. futures_price)
  else
    let (d1, d2) = compute_d1_d2 ~futures_price ~strike ~expiry ~volatility in
    let discount = exp (-. rate *. expiry) in

    match option_type with
    | Call ->
        discount *. (futures_price *. normal_cdf d1 -. strike *. normal_cdf d2)
    | Put ->
        discount *. (strike *. normal_cdf (-. d2) -. futures_price *. normal_cdf (-. d1))

(* Delta: ∂V/∂F

   Δ_call = e^(-rT) · N(d₁)
   Δ_put = -e^(-rT) · N(-d₁) = e^(-rT) · (N(d₁) - 1)

   Note: Delta is with respect to FUTURES price, not spot!
*)
let delta ~option_type ~futures_price ~strike ~expiry ~rate ~volatility =
  if expiry <= 0.0 then
    (* At expiry: delta is 0 or 1 (or -1 for puts) *)
    match option_type with
    | Call -> if futures_price > strike then 1.0 else 0.0
    | Put -> if futures_price < strike then -1.0 else 0.0
  else
    let (d1, _) = compute_d1_d2 ~futures_price ~strike ~expiry ~volatility in
    let discount = exp (-. rate *. expiry) in

    match option_type with
    | Call -> discount *. normal_cdf d1
    | Put -> discount *. (normal_cdf d1 -. 1.0)

(* Gamma: ∂²V/∂F² = ∂Δ/∂F

   Γ = e^(-rT) · n(d₁) / (F · σ · √T)

   Same for both calls and puts
*)
let gamma ~futures_price ~strike ~expiry ~rate ~volatility =
  if expiry <= 0.0 then
    0.0  (* No gamma at expiry *)
  else
    let (d1, _) = compute_d1_d2 ~futures_price ~strike ~expiry ~volatility in
    let discount = exp (-. rate *. expiry) in
    let vol_sqrt_t = volatility *. sqrt expiry in

    discount *. normal_pdf d1 /. (futures_price *. vol_sqrt_t)

(* Vega: ∂V/∂σ

   ν = F · e^(-rT) · n(d₁) · √T

   Same for both calls and puts
   Note: Returns vega per 1% change in volatility (divide by 100)
*)
let vega ~futures_price ~strike ~expiry ~rate ~volatility =
  if expiry <= 0.0 then
    0.0  (* No vega at expiry *)
  else
    let (d1, _) = compute_d1_d2 ~futures_price ~strike ~expiry ~volatility in
    let discount = exp (-. rate *. expiry) in
    let sqrt_t = sqrt expiry in

    (* Vega per 1% change in vol *)
    futures_price *. discount *. normal_pdf d1 *. sqrt_t /. 100.0

(* Theta: ∂V/∂T (negative of ∂V/∂t)

   Θ_call = -F · n(d₁) · σ · e^(-rT) / (2√T) + r · C
   Θ_put = -F · n(d₁) · σ · e^(-rT) / (2√T) + r · P

   Note: Different from Black-Scholes! Includes +rC or +rP term

   Returns theta per day (divide annual by 365)
*)
let theta ~option_type ~futures_price ~strike ~expiry ~rate ~volatility =
  if expiry <= 0.0 then
    0.0  (* No theta at expiry *)
  else
    let (d1, _) = compute_d1_d2 ~futures_price ~strike ~expiry ~volatility in
    let discount = exp (-. rate *. expiry) in
    let sqrt_t = sqrt expiry in
    let n_d1 = normal_pdf d1 in

    (* Common term for both calls and puts *)
    let term1 = -. futures_price *. n_d1 *. volatility *. discount /. (2.0 *. sqrt_t) in

    (* Option value (for +rV term) *)
    let option_value = black_price ~option_type ~futures_price ~strike ~expiry ~rate ~volatility in

    let theta_annual = term1 +. rate *. option_value in

    (* Convert to theta per day *)
    theta_annual /. 365.0

(* Rho: ∂V/∂r

   For futures options, rho only affects discounting:

   ρ_call = T · C
   ρ_put = -T · P

   Note: VERY different from Black-Scholes!
         In Black-Scholes, rho has K·T·e^(-rT)·N(d₂) term

   Returns rho per 1% change in interest rate (divide by 100)
*)
let rho ~option_type ~premium ~expiry =
  if expiry <= 0.0 then
    0.0
  else
    let rho_annual = match option_type with
      | Call -> expiry *. premium
      | Put -> -. expiry *. premium
    in
    (* Rho per 1% change in rate *)
    rho_annual /. 100.0

(* Calculate all Greeks at once (more efficient) *)
let black_greeks ~option_type ~futures_price ~strike ~expiry ~rate ~volatility =
  if expiry <= 0.0 then
    (* At expiry: only delta matters *)
    {
      delta = (match option_type with
               | Call -> if futures_price > strike then 1.0 else 0.0
               | Put -> if futures_price < strike then -1.0 else 0.0);
      gamma = 0.0;
      theta = 0.0;
      vega = 0.0;
      rho = 0.0;
    }
  else
    let (d1, _d2) = compute_d1_d2 ~futures_price ~strike ~expiry ~volatility in
    let discount = exp (-. rate *. expiry) in
    let sqrt_t = sqrt expiry in
    let vol_sqrt_t = volatility *. sqrt_t in
    let n_d1 = normal_pdf d1 in

    (* Delta *)
    let delta_value = match option_type with
    | Call -> discount *. normal_cdf d1
    | Put -> discount *. (normal_cdf d1 -. 1.0)
    in

    (* Gamma (same for calls and puts) *)
    let gamma_value = discount *. n_d1 /. (futures_price *. vol_sqrt_t) in

    (* Vega (same for calls and puts, per 1% vol change) *)
    let vega_value = futures_price *. discount *. n_d1 *. sqrt_t /. 100.0 in

    (* Theta (per day) *)
    let term1 = -. futures_price *. n_d1 *. volatility *. discount /. (2.0 *. sqrt_t) in
    let option_value = black_price ~option_type ~futures_price ~strike ~expiry ~rate ~volatility in
    let theta_annual = term1 +. rate *. option_value in
    let theta_value = theta_annual /. 365.0 in

    (* Rho (per 1% rate change) *)
    let rho_annual = match option_type with
      | Call -> expiry *. option_value
      | Put -> -. expiry *. option_value
    in
    let rho_value = rho_annual /. 100.0 in

    {
      delta = delta_value;
      gamma = gamma_value;
      theta = theta_value;
      vega = vega_value;
      rho = rho_value;
    }

(** Helper functions **)

(* Build futures option *)
let build_futures_option ~(futures : futures_contract) ~option_type ~strike ~expiry ~rate ~volatility =
  let premium = black_price
    ~option_type
    ~futures_price:futures.futures_price
    ~strike
    ~expiry
    ~rate
    ~volatility
  in
  ({
    underlying_futures = futures;
    option_type;
    strike;
    expiry;
    premium;
    volatility;
  } : futures_option)

(* Intrinsic value *)
let intrinsic_value ~option_type ~futures_price ~strike =
  match option_type with
  | Call -> max 0.0 (futures_price -. strike)
  | Put -> max 0.0 (strike -. futures_price)

(* Time value *)
let time_value ~option_type ~futures_price ~strike ~expiry ~rate ~volatility =
  let total_value = black_price ~option_type ~futures_price ~strike ~expiry ~rate ~volatility in
  let intrinsic = intrinsic_value ~option_type ~futures_price ~strike in
  total_value -. intrinsic

(* Moneyness classification *)
let moneyness ~option_type ~futures_price ~strike =
  let tolerance = 0.001 in  (* 0.1% tolerance for ATM *)
  let ratio = futures_price /. strike in

  match option_type with
  | Call ->
      if ratio > 1.0 +. tolerance then "ITM"
      else if ratio < 1.0 -. tolerance then "OTM"
      else "ATM"
  | Put ->
      if ratio < 1.0 -. tolerance then "ITM"
      else if ratio > 1.0 +. tolerance then "OTM"
      else "ATM"

(* Implied volatility using Newton-Raphson *)
let implied_volatility ~option_type ~futures_price ~strike ~expiry ~rate ~market_price =
  let max_iterations = 100 in
  let tolerance = 1e-6 in

  (* Initial guess: ATM volatility approximation *)
  let initial_vol = 0.20 in

  let rec newton_raphson vol iteration =
    if iteration >= max_iterations then
      None  (* Failed to converge *)
    else
      let price = black_price ~option_type ~futures_price ~strike ~expiry ~rate ~volatility:vol in
      let vega_value = vega ~futures_price ~strike ~expiry ~rate ~volatility:vol in

      let diff = price -. market_price in

      if abs_float diff < tolerance then
        Some vol  (* Converged *)
      else if abs_float vega_value < 1e-10 then
        None  (* Vega too small, cannot converge *)
      else
        (* Newton-Raphson update: vol_new = vol_old - f(vol)/f'(vol) *)
        let vol_new = vol -. diff /. (vega_value *. 100.0) in  (* vega is per 1% *)

        (* Ensure vol stays positive *)
        let vol_new = max 0.01 (min 5.0 vol_new) in

        newton_raphson vol_new (iteration + 1)
  in

  newton_raphson initial_vol 0

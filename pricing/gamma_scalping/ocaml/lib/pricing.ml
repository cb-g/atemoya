(* Black-Scholes-Merton Option Pricing and Greeks *)

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

(* Standard normal cumulative distribution function *)
let normal_cdf x =
  0.5 *. (1.0 +. erf (x /. sqrt_2))

(* Standard normal probability density function *)
let normal_pdf x =
  exp (-0.5 *. x *. x) /. sqrt_2pi

(* Compute d1 and d2 from Black-Scholes formula

   d1 = [ln(S/K) + (r - q + σ²/2)T] / (σ√T)
   d2 = d1 - σ√T

   where:
   - S = spot price
   - K = strike price
   - T = time to expiry (years)
   - r = risk-free rate
   - q = dividend yield
   - σ = volatility
*)
let compute_d1_d2 ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  if expiry <= 0.0 then
    failwith "Pricing.compute_d1_d2: expiry must be positive"
  else if volatility <= 0.0 then
    failwith "Pricing.compute_d1_d2: volatility must be positive"
  else if spot <= 0.0 then
    failwith "Pricing.compute_d1_d2: spot price must be positive"
  else if strike <= 0.0 then
    failwith "Pricing.compute_d1_d2: strike must be positive"
  else
    let vol_sqrt_t = volatility *. sqrt expiry in
    let d1 =
      (log (spot /. strike) +. (rate -. dividend +. 0.5 *. volatility *. volatility) *. expiry)
      /. vol_sqrt_t
    in
    let d2 = d1 -. vol_sqrt_t in
    (d1, d2)

(* Black-Scholes formula for European options

   Call: C = S·e^(-qT)·N(d1) - K·e^(-rT)·N(d2)
   Put:  P = K·e^(-rT)·N(-d2) - S·e^(-qT)·N(-d1)
*)
let price_option ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  if expiry <= 0.0 then
    (* Option expired - return intrinsic value *)
    match option_type with
    | Call -> max 0.0 (spot -. strike)
    | Put -> max 0.0 (strike -. spot)
  else
    let (d1, d2) = compute_d1_d2 ~spot ~strike ~expiry ~rate ~dividend ~volatility in
    let discount_spot = spot *. exp (-. dividend *. expiry) in
    let discount_strike = strike *. exp (-. rate *. expiry) in

    match option_type with
    | Call ->
        discount_spot *. normal_cdf d1 -. discount_strike *. normal_cdf d2
    | Put ->
        discount_strike *. normal_cdf (-. d2) -. discount_spot *. normal_cdf (-. d1)

(* Delta: ∂V/∂S

   Call: Δ = e^(-qT)·N(d1)
   Put:  Δ = -e^(-qT)·N(-d1) = e^(-qT)·(N(d1) - 1)
*)
let delta ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  if expiry <= 0.0 then
    (* At expiry: delta is 0 or 1 (or -1 for puts) *)
    match option_type with
    | Call -> if spot > strike then 1.0 else 0.0
    | Put -> if spot < strike then -1.0 else 0.0
  else
    let (d1, _) = compute_d1_d2 ~spot ~strike ~expiry ~rate ~dividend ~volatility in
    let discount = exp (-. dividend *. expiry) in

    match option_type with
    | Call -> discount *. normal_cdf d1
    | Put -> discount *. (normal_cdf d1 -. 1.0)

(* Gamma: ∂²V/∂S² = ∂Δ/∂S

   Γ = e^(-qT)·n(d1) / (S·σ·√T)

   Same for both calls and puts
*)
let gamma ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  if expiry <= 0.0 then
    0.0  (* No gamma at expiry *)
  else
    let (d1, _) = compute_d1_d2 ~spot ~strike ~expiry ~rate ~dividend ~volatility in
    let discount = exp (-. dividend *. expiry) in
    let vol_sqrt_t = volatility *. sqrt expiry in

    discount *. normal_pdf d1 /. (spot *. vol_sqrt_t)

(* Vega: ∂V/∂σ

   ν = S·e^(-qT)·n(d1)·√T

   Same for both calls and puts
   Note: Returns vega per 1% change in volatility (divide by 100)
*)
let vega ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  if expiry <= 0.0 then
    0.0  (* No vega at expiry *)
  else
    let (d1, _) = compute_d1_d2 ~spot ~strike ~expiry ~rate ~dividend ~volatility in
    let discount = exp (-. dividend *. expiry) in
    let sqrt_t = sqrt expiry in

    (* Vega per 1% change in vol *)
    spot *. discount *. normal_pdf d1 *. sqrt_t /. 100.0

(* Theta: ∂V/∂T (negative of ∂V/∂t)

   Call: Θ = -S·n(d1)·σ·e^(-qT)/(2√T) - r·K·e^(-rT)·N(d2) + q·S·e^(-qT)·N(d1)
   Put:  Θ = -S·n(d1)·σ·e^(-qT)/(2√T) + r·K·e^(-rT)·N(-d2) - q·S·e^(-qT)·N(-d1)

   Note: Returns theta per day (divide by 365)
*)
let theta ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  if expiry <= 0.0 then
    0.0  (* No theta at expiry *)
  else
    let (d1, d2) = compute_d1_d2 ~spot ~strike ~expiry ~rate ~dividend ~volatility in
    let discount_spot = exp (-. dividend *. expiry) in
    let discount_strike = exp (-. rate *. expiry) in
    let sqrt_t = sqrt expiry in

    (* First term: same for both calls and puts *)
    let term1 = -. spot *. normal_pdf d1 *. volatility *. discount_spot /. (2.0 *. sqrt_t) in

    let theta_annual = match option_type with
    | Call ->
        term1 -. rate *. strike *. discount_strike *. normal_cdf d2
             +. dividend *. spot *. discount_spot *. normal_cdf d1
    | Put ->
        term1 +. rate *. strike *. discount_strike *. normal_cdf (-. d2)
             -. dividend *. spot *. discount_spot *. normal_cdf (-. d1)
    in

    (* Convert to theta per day *)
    theta_annual /. 365.0

(* Rho: ∂V/∂r

   Call: ρ = K·T·e^(-rT)·N(d2)
   Put:  ρ = -K·T·e^(-rT)·N(-d2)

   Note: Returns rho per 1% change in interest rate (divide by 100)
*)
let rho ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  if expiry <= 0.0 then
    0.0  (* No rho at expiry *)
  else
    let (_, d2) = compute_d1_d2 ~spot ~strike ~expiry ~rate ~dividend ~volatility in
    let discount_strike = exp (-. rate *. expiry) in

    let rho_annual = match option_type with
    | Call -> strike *. expiry *. discount_strike *. normal_cdf d2
    | Put -> -. strike *. expiry *. discount_strike *. normal_cdf (-. d2)
    in

    (* Rho per 1% change in rate *)
    rho_annual /. 100.0

(* Calculate all Greeks at once (more efficient than calling individually) *)
let compute_greeks ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  if expiry <= 0.0 then
    (* At expiry: only delta matters *)
    {
      delta = (match option_type with
               | Call -> if spot > strike then 1.0 else 0.0
               | Put -> if spot < strike then -1.0 else 0.0);
      gamma = 0.0;
      theta = 0.0;
      vega = 0.0;
      rho = 0.0;
    }
  else
    let (d1, d2) = compute_d1_d2 ~spot ~strike ~expiry ~rate ~dividend ~volatility in
    let discount_spot = exp (-. dividend *. expiry) in
    let discount_strike = exp (-. rate *. expiry) in
    let sqrt_t = sqrt expiry in
    let vol_sqrt_t = volatility *. sqrt_t in
    let n_d1 = normal_pdf d1 in

    (* Delta *)
    let delta_value = match option_type with
    | Call -> discount_spot *. normal_cdf d1
    | Put -> discount_spot *. (normal_cdf d1 -. 1.0)
    in

    (* Gamma (same for calls and puts) *)
    let gamma_value = discount_spot *. n_d1 /. (spot *. vol_sqrt_t) in

    (* Vega (same for calls and puts, per 1% vol change) *)
    let vega_value = spot *. discount_spot *. n_d1 *. sqrt_t /. 100.0 in

    (* Theta (per day) *)
    let term1 = -. spot *. n_d1 *. volatility *. discount_spot /. (2.0 *. sqrt_t) in
    let theta_annual = match option_type with
    | Call ->
        term1 -. rate *. strike *. discount_strike *. normal_cdf d2
             +. dividend *. spot *. discount_spot *. normal_cdf d1
    | Put ->
        term1 +. rate *. strike *. discount_strike *. normal_cdf (-. d2)
             -. dividend *. spot *. discount_spot *. normal_cdf (-. d1)
    in
    let theta_value = theta_annual /. 365.0 in

    (* Rho (per 1% rate change) *)
    let rho_annual = match option_type with
    | Call -> strike *. expiry *. discount_strike *. normal_cdf d2
    | Put -> -. strike *. expiry *. discount_strike *. normal_cdf (-. d2)
    in
    let rho_value = rho_annual /. 100.0 in

    {
      delta = delta_value;
      gamma = gamma_value;
      theta = theta_value;
      vega = vega_value;
      rho = rho_value;
    }

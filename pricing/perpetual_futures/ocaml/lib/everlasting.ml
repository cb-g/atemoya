(** Everlasting options pricing.

    Implements the closed-form pricing formulas from Section 8 of:
    Ackerer, Hugonnier, Jermann (2025) "Perpetual Futures Pricing"

    Everlasting options track phi(x) instead of x itself.
    Price: f_o = E[phi(x_{t+tau})] where tau ~ Exponential(kappa)

    For calls and puts in Black-Scholes setting:
    - Put-call parity: c - p = f(x) - K where f(x) is the perpetual futures
    - Closed-form via solution to ODE (108)
*)

open Types

(** Solve the quadratic equation for everlasting option exponents.

    (r_a - r_b) * xi + 0.5 * xi * (xi - 1) * sigma^2 - kappa = 0

    Returns (Pi, Theta) where Pi < 0 and Theta > 1.
*)
let quadratic_roots ~r_a ~r_b ~sigma ~kappa =
  let mu = r_a -. r_b in
  let v2 = sigma *. sigma in

  (* Quadratic: 0.5 * v2 * xi^2 + (mu - 0.5 * v2) * xi - kappa = 0 *)
  let a = 0.5 *. v2 in
  let b = mu -. 0.5 *. v2 in
  let c = -. kappa in

  let discriminant = b *. b -. 4.0 *. a *. c in
  if discriminant < 0.0 then
    failwith "No real roots for quadratic equation"
  else
    let sqrt_disc = sqrt discriminant in
    let xi1 = (-. b +. sqrt_disc) /. (2.0 *. a) in
    let xi2 = (-. b -. sqrt_disc) /. (2.0 *. a) in

    (* Pi < 0 and Theta > 1 *)
    let pi_val = min xi1 xi2 in
    let theta_val = max xi1 xi2 in
    (pi_val, theta_val)

(** Perpetual futures price (for put-call parity).

    f(x) = kappa * x / (kappa - r_a + r_b)
*)
let perpetual_futures ~kappa ~r_a ~r_b ~spot =
  let denom = kappa -. r_a +. r_b in
  if denom <= 0.0 then
    failwith "Invalid parameters: kappa - r_a + r_b must be positive"
  else
    kappa *. spot /. denom

(** Everlasting call option price (Proposition 6).

    c(x) = {
      x^Theta * K^(1-Theta) * (Pi*(r_a-r_b)-kappa) / ((Pi-Theta)*(kappa-r_a+r_b)),  x <= K
      x^Pi * K^(1-Pi) * (Theta*(r_a-r_b)-kappa) / ((Pi-Theta)*(kappa-r_a+r_b)) + f(x) - K,  x > K
    }
*)
let price_everlasting_call ~kappa ~r_a ~r_b ~sigma ~strike ~spot =
  let (pi_val, theta_val) = quadratic_roots ~r_a ~r_b ~sigma ~kappa in
  let mu = r_a -. r_b in
  let denom = (pi_val -. theta_val) *. (kappa -. r_a +. r_b) in

  if spot <= strike then
    let coef = (pi_val *. mu -. kappa) /. denom in
    (spot ** theta_val) *. (strike ** (1.0 -. theta_val)) *. coef
  else
    let coef = (theta_val *. mu -. kappa) /. denom in
    let f_x = perpetual_futures ~kappa ~r_a ~r_b ~spot in
    (spot ** pi_val) *. (strike ** (1.0 -. pi_val)) *. coef +. f_x -. strike

(** Everlasting put option price.

    Using put-call parity: p = c + K - f(x)
*)
let price_everlasting_put ~kappa ~r_a ~r_b ~sigma ~strike ~spot =
  let call_price = price_everlasting_call ~kappa ~r_a ~r_b ~sigma ~strike ~spot in
  let f_x = perpetual_futures ~kappa ~r_a ~r_b ~spot in
  call_price +. strike -. f_x

(** Everlasting call delta.

    Delta = dc/dx computed from the closed-form formula.
*)
let delta_everlasting_call ~kappa ~r_a ~r_b ~sigma ~strike ~spot =
  let (pi_val, theta_val) = quadratic_roots ~r_a ~r_b ~sigma ~kappa in
  let mu = r_a -. r_b in
  let denom = (pi_val -. theta_val) *. (kappa -. r_a +. r_b) in

  if spot <= strike then
    let coef = (pi_val *. mu -. kappa) /. denom in
    theta_val *. (spot ** (theta_val -. 1.0)) *. (strike ** (1.0 -. theta_val)) *. coef
  else
    let coef = (theta_val *. mu -. kappa) /. denom in
    let f_delta = kappa /. (kappa -. r_a +. r_b) in
    pi_val *. (spot ** (pi_val -. 1.0)) *. (strike ** (1.0 -. pi_val)) *. coef +. f_delta

(** Everlasting put delta.

    Delta_put = Delta_call - f'(x) = Delta_call - kappa/(kappa - r_a + r_b)
*)
let delta_everlasting_put ~kappa ~r_a ~r_b ~sigma ~strike ~spot =
  let call_delta = delta_everlasting_call ~kappa ~r_a ~r_b ~sigma ~strike ~spot in
  let f_delta = kappa /. (kappa -. r_a +. r_b) in
  call_delta -. f_delta

(** Price everlasting option with full result *)
let price_option (opt : everlasting_option) ~spot : option_result =
  let { opt_type; strike; kappa; r_a; r_b; sigma } = opt in

  let (option_price, delta) = match opt_type with
    | Call ->
        let p = price_everlasting_call ~kappa ~r_a ~r_b ~sigma ~strike ~spot in
        let d = delta_everlasting_call ~kappa ~r_a ~r_b ~sigma ~strike ~spot in
        (p, d)
    | Put ->
        let p = price_everlasting_put ~kappa ~r_a ~r_b ~sigma ~strike ~spot in
        let d = delta_everlasting_put ~kappa ~r_a ~r_b ~sigma ~strike ~spot in
        (p, d)
  in

  let intrinsic = match opt_type with
    | Call -> max 0.0 (spot -. strike)
    | Put -> max 0.0 (strike -. spot)
  in

  {
    option_price;
    delta;
    underlying = spot;
    intrinsic;
    time_value = option_price -. intrinsic;
  }

(** Everlasting option price grid for plotting *)
let option_price_grid ~kappa ~r_a ~r_b ~sigma ~strike ~spots : (float * float * float) list =
  List.map (fun spot ->
    let call = price_everlasting_call ~kappa ~r_a ~r_b ~sigma ~strike ~spot in
    let put = price_everlasting_put ~kappa ~r_a ~r_b ~sigma ~strike ~spot in
    (spot, call, put)
  ) spots

(** Perpetual futures pricing formulas.

    Implements the no-arbitrage pricing formulas from:
    Ackerer, Hugonnier, Jermann (2025) "Perpetual Futures Pricing"

    Key formulas:
    - Linear:  f_t = (kappa - iota)(1 + r_b) / (r_b - r_a + kappa(1 + r_b)) * x_t
    - Inverse: f_I = (r_a - r_b + kappa_I(1 + r_a)) / ((kappa_I - iota_I)(1 + r_a)) * x_t
    - Quanto:  f_q = (kappa - iota) / (r_c - sigma_x * sigma_z - r_a + kappa) * z_t
*)

open Types

(** Linear perpetual futures price.

    Proposition 1 (discrete) / Proposition 3 (continuous):
    f_t = (kappa - iota)(1 + r_b) / (r_b - r_a + kappa(1 + r_b)) * x_t

    For continuous-time (annual rates):
    f_t = (kappa - iota) / (kappa + r_b - r_a) * x_t
*)
let price_linear_discrete ~kappa ~iota ~r_a ~r_b ~spot =
  let numerator = (kappa -. iota) *. (1.0 +. r_b) in
  let denominator = r_b -. r_a +. kappa *. (1.0 +. r_b) in
  if denominator <= 0.0 then
    failwith "Invalid parameters: denominator must be positive"
  else
    (numerator /. denominator) *. spot

let price_linear_continuous ~kappa ~iota ~r_a ~r_b ~spot =
  let numerator = kappa -. iota in
  let denominator = kappa +. r_b -. r_a in
  if denominator <= 0.0 then
    failwith "Invalid parameters: kappa + r_b - r_a must be positive"
  else
    (numerator /. denominator) *. spot

(** Inverse perpetual futures price.

    Proposition 2 (discrete) / Proposition 4 (continuous):
    f_I = (r_a - r_b + kappa_I(1 + r_a)) / ((kappa_I - iota_I)(1 + r_a)) * x_t

    For continuous-time:
    f_I = (kappa_I + r_a - r_b) / (kappa_I - iota_I) * x_t
*)
let price_inverse_discrete ~kappa ~iota ~r_a ~r_b ~spot =
  let numerator = r_a -. r_b +. kappa *. (1.0 +. r_a) in
  let denominator = (kappa -. iota) *. (1.0 +. r_a) in
  if denominator <= 0.0 then
    failwith "Invalid parameters: (kappa - iota)(1 + r_a) must be positive"
  else
    (numerator /. denominator) *. spot

let price_inverse_continuous ~kappa ~iota ~r_a ~r_b ~spot =
  let numerator = kappa +. r_a -. r_b in
  let denominator = kappa -. iota in
  if denominator <= 0.0 then
    failwith "Invalid parameters: kappa - iota must be positive"
  else
    (numerator /. denominator) *. spot

(** Quanto perpetual futures price (continuous-time, Black-Scholes).

    Proposition 5:
    f_q = (kappa - iota) / (r_c - sigma_x * sigma_z * rho - r_a + kappa) * z_t

    where rho is the correlation and sigma_x * sigma_z * rho is the
    covariance term (convexity adjustment).
*)
let price_quanto ~kappa ~iota ~r_a ~r_c ~sigma_x ~sigma_z ~rho ~spot_z =
  let cov_adjustment = sigma_x *. sigma_z *. rho in
  let numerator = kappa -. iota in
  let denominator = r_c -. cov_adjustment -. r_a +. kappa in
  if denominator <= 0.0 then
    failwith "Invalid parameters: r_c - cov - r_a + kappa must be positive"
  else
    (numerator /. denominator) *. spot_z

(** Perfect anchoring interest factor.

    Corollary 1 (linear): iota = (r_a - r_b) / (1 + r_b)
    Corollary 2 (inverse): iota_I = (r_b - r_a) / (1 + r_a)

    Continuous-time:
    Linear: iota = r_a - r_b
    Inverse: iota_I = r_b - r_a
*)
let perfect_iota_linear_discrete ~r_a ~r_b =
  (r_a -. r_b) /. (1.0 +. r_b)

let perfect_iota_inverse_discrete ~r_a ~r_b =
  (r_b -. r_a) /. (1.0 +. r_a)

let perfect_iota_linear_continuous ~r_a ~r_b =
  r_a -. r_b

let perfect_iota_inverse_continuous ~r_a ~r_b =
  r_b -. r_a

(** Futures-to-spot ratio.

    Linear (iota = 0):  f/x = kappa(1 + r_b) / (kappa(1 + r_b) - delta)
    where delta = r_a - r_b
*)
let futures_spot_ratio_linear ~kappa ~r_a ~r_b =
  let delta = r_a -. r_b in
  let denom = kappa *. (1.0 +. r_b) -. delta in
  if denom <= 0.0 then
    failwith "Invalid parameters for ratio calculation"
  else
    kappa *. (1.0 +. r_b) /. denom

(** Implied funding rate from observed futures and spot prices.

    Given f_t / x_t = (kappa - iota) / (kappa + r_b - r_a), solve for iota:
    iota = kappa - (f/x) * (kappa + r_b - r_a)
*)
let implied_iota ~kappa ~r_a ~r_b ~futures ~spot =
  let ratio = futures /. spot in
  kappa -. ratio *. (kappa +. r_b -. r_a)

(** Annualized funding rate from 8-hour funding rate.

    Most exchanges use 8-hour funding periods (3 per day).
*)
let annualize_funding_rate ~funding_8h =
  funding_8h *. 3.0 *. 365.0

let funding_rate_8h ~annualized =
  annualized /. (3.0 *. 365.0)

(** Convert period rates to annual rates and vice versa.

    The paper uses Δ = 1/(3*360) to convert annual to 8h period rates.
*)
let annual_to_period ~annual_rate ~periods_per_year =
  annual_rate /. periods_per_year

let period_to_annual ~period_rate ~periods_per_year =
  period_rate *. periods_per_year

(** Full pricing computation for a contract *)
let price_contract (contract : perpetual_contract) ~spot : pricing_result =
  let kappa = contract.funding.kappa in
  let iota = contract.funding.iota in
  let r_a = contract.rates.r_a in
  let r_b = contract.rates.r_b in

  let futures_price = match contract.contract_type with
    | Linear -> price_linear_continuous ~kappa ~iota ~r_a ~r_b ~spot
    | Inverse -> price_inverse_continuous ~kappa ~iota ~r_a ~r_b ~spot
    | Quanto ->
        (* For quanto, need additional parameters *)
        match contract.volatility, contract.rates.r_c with
        | Some vol, Some r_c ->
            let sigma_x = vol.sigma_x in
            let sigma_z = Option.value ~default:vol.sigma_x vol.sigma_z in
            let rho = Option.value ~default:1.0 vol.rho_xz in
            price_quanto ~kappa ~iota ~r_a ~r_c ~sigma_x ~sigma_z ~rho ~spot_z:spot
        | _ -> failwith "Quanto requires volatility and r_c parameters"
  in

  let basis = futures_price -. spot in
  let basis_pct = (basis /. spot) *. 100.0 in

  let perfect_iota = match contract.contract_type with
    | Linear -> perfect_iota_linear_continuous ~r_a ~r_b
    | Inverse -> perfect_iota_inverse_continuous ~r_a ~r_b
    | Quanto -> r_a -. (Option.value ~default:0.0 contract.rates.r_c)
  in

  (* Fair funding rate: the rate that would make f = x *)
  let fair_funding_rate = perfect_iota in

  {
    spot_price = spot;
    futures_price;
    basis;
    basis_pct;
    fair_funding_rate;
    perfect_iota;
  }

(** Random maturity parameter.

    The perpetual futures price can be represented as E[x_{t+theta}]
    where theta ~ Geometric(kappa) in discrete time or
    theta ~ Exponential(kappa) in continuous time.

    Mean random maturity = 1/kappa
*)
let mean_random_maturity ~kappa =
  if kappa <= 0.0 then
    failwith "kappa must be positive"
  else
    1.0 /. kappa

(** The market-implied readout (36): the risk-neutral distribution of the price at one
    expiry, read from an end-of-day option chain and placed beside the declared belief.
    Pure and deterministic; the headline never depends on it.

    Contract. Input: an [option_chain] (the store format), the record's risk-free rate,
    the required return used ([ke]), the fair value, and the growth-then-terminal
    evaluator when the model has one. Output: [Ok market_implied], every price in the
    chain's quote currency, every probability risk-neutral, or [Error reason] with exactly
    one of the reasons the chart names: ["no expiry >= 365 days with >= 8 quoted strikes on
    each side"] or ["smile fit failed: <why>"]. ["no options data"] is the caller's, when
    there is no chain for the name.

    Method. The expiry is the longest at least 365 calendar days out with at least eight
    out-of-the-money strikes quoted with a positive bid on each side of spot. The forward
    is put-call parity at the straddle strike nearest spot. Out-of-the-money mids invert
    to total implied variance under Black's formula on the forward; the SVI smile
    [w(k) = a + b (rho (k - m) + sqrt((k - m)^2 + sigma^2))] in log-moneyness [k = ln(K/F)]
    is fitted by the quasi-explicit method (linear least squares in [a, b rho sigma, b sigma]
    for fixed [m, sigma], Nelder-Mead over [m, sigma]), then checked for butterfly
    arbitrage ([g(k) >= 0] on [-3, 3] in steps of 0.02) and Lee's wing bound ([b (1 + |rho|) <= 2]);
    both are hard constraints of the fit as well, so the fitted smile is the best
    arbitrage-free SVI through the quotes, never a better fit bought by an arbitrageable wing.
    Breeden-Litzenberger on the fitted smile is in closed form: the risk-neutral CDF of
    the price at expiry is [1 - N(d-) + n(d-) w'(k) / (2 sqrt w)], the density in [k] is
    [g(k) / sqrt(2 pi w) exp(-d-^2 / 2)]. Quantiles invert the CDF by bisection.
    [p_below_anchor_path] is the CDF at [V (1 + ke)^T]. Each price quantile discounted at
    [ke] to today is inverted through the implied-terminal-growth solver, labelled
    approximate: a horizon of a few years stands in for the long run. *)

type svi = { a : float; b : float; rho : float; m : float; sigma : float }

val norm_cdf : float -> float

val black_call : forward:float -> strike:float -> w:float -> float
(** Black's undiscounted call on the forward at total variance [w]. *)

val implied_total_variance :
  right:[ `Call | `Put ] -> forward:float -> strike:float -> price:float -> float option
(** The total variance at which Black's undiscounted price equals [price]; [None] when the
    price is at or below intrinsic or at or above its upper bound. *)

val total_variance : svi -> float -> float
val g : svi -> float -> float
(** Gatheral's butterfly function; the smile is free of butterfly arbitrage where [g >= 0]. *)

val fit : (float * float) list -> svi
(** The SVI smile through [(k, w)] points; [rmse] is [fit_rmse]. *)

val fit_rmse : svi -> (float * float) list -> float

val check : svi -> (unit, string) result
(** [Error why] on non-positive total variance, butterfly arbitrage on [-3, 3], or a wing
    slope beyond Lee's bound. *)

val cdf : svi -> float -> float
(** The risk-neutral probability that [ln(S_T / F)] is at or below [k]. *)

val density : svi -> float -> float
(** The risk-neutral density of [ln(S_T / F)] at [k]. *)

val quantile : svi -> float -> float
(** The [k] at which [cdf] equals [p], by bisection on [-4, 4]. *)

val select_expiry :
  Boundary_t.option_quote list -> spot:float -> snapshot_date:string ->
  (string * int * int * int, string) result
(** [(expiry, days, otm_quoted_below, otm_quoted_above)] for the longest expiry at least
    365 days out with at least eight OTM strikes quoted with a positive bid on each side
    of spot; else the reason. *)

val min_days : int
val min_strikes_each_side : int
val quantile_levels : float list

val of_chain :
  Boundary_t.option_chain ->
  rf:float ->
  ke:float ->
  fair_value:float ->
  growth:(float * (float -> float), string) result ->
  (Boundary_t.market_implied, string) result
(** [growth] is [Ok (rate, f)] with [f] the fair value at a long-run growth for the
    growth inversion, or [Error reason] on a path without a terminal growth. *)

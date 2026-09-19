(** The implied readouts: what the price needs to be true, solved on the
    record's own inputs by bisection with everything else held at its recorded value.
    Pure and deterministic; the headline fair value never depends on this module.

    [dcf_fair_value] and [residual_income_fair_value] reproduce the model's fair value
    at the recorded g0 (ROE0) and lambda, and re-evaluate it at any other pair; both are
    the arithmetic of [Dcf] and [Residual_income] on the inputs, nothing else. *)

type outcome =
  | Root of float
  | Beyond_high  (** the target lies past the top of the domain *)
  | Beyond_low  (** the target lies past the bottom of the domain *)
  | Flat  (** the function does not vary over the domain: nothing to solve *)

val bisect :
  f:(float -> float) -> target:float -> lo:float -> hi:float -> tolerance:float -> outcome
(** The x in [lo, hi] with [f x = target] to within [tolerance] on x, for [f] monotone in
    either direction; [Beyond_high]/[Beyond_low] say which end the answer lies past. *)

val level_domain : float * float
(** [-0.50, 3.00] for the dcf's implied_g0. *)

val roe_domain : float * float
(** [-0.50, 1.00] for the residual-income implied_roe0. *)

val lambda_domain : float * float
(** [0.01, 5.0]: half-lives from about 69 years down to about 0.14. *)

val tolerance : float

val max_horizon : int
(** 40: the longest explicit period the horizon scan tries. *)

val dcf_fair_value :
  ?projection_years:int -> ?fcff:float -> ?wacc:float -> ?terminal_growth_rate:float ->
  Boundary_t.inputs -> g0:float -> lambda:float -> float
val residual_income_fair_value :
  ?projection_years:int -> ?book_equity:float -> ?cost_of_equity:float ->
  Boundary_t.residual_income_inputs -> roe_0:float -> lambda:float -> float
(** [projection_years] defaults to the recorded horizon; the risk-free rate stays the
    recorded one whatever the horizon. The other optional arguments override one held
    input at a time for the sensitivity block (23); absent, the recorded value holds. *)

val reit_fair_value :
  ?projection_years:int -> ?dividend_per_share:float -> ?cost_of_equity:float -> ?terminal_growth_rate:float ->
  Boundary_t.reit_inputs -> g0:float -> lambda:float -> float
(** The REIT model's fair value per share at any starting growth and lambda. *)

val rf_tenor_note : string

val dcf_block : Boundary_t.inputs -> price:float -> Boundary_t.implied
(** The dcf readouts on the engine's inputs; the mid-cycle model (22) reads the same
    block on its own fcff and g0. *)

val of_inputs : Boundary_t.model_inputs -> price:float -> Boundary_t.implied
(** The three readouts for an Ok record (level and half-life by bisection, the horizon by
    an integer scan over 1..40 under the same guard), every null with its reason, the
    three-way rule that picked the meaningful one, and the inputs held fixed. *)

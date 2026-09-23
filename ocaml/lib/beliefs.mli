(** Declared beliefs on the parameter each model's long run turns on (24): long-run growth
    on the DCF-shaped paths and (58) the long-run return on equity on the residual-income
    path. A belief is six fields and nothing else:
    mean, sd, floor, ceiling, why, as_of, a truncated normal. The loaders are strict
    (an unknown or missing field, a non-positive sd, a floor at or above the ceiling,
    an empty why or a malformed as_of is an [Error] naming the entry), and nothing here
    estimates a field from history. Values in the files are percentage points: the
    tracked table holds class offsets around an anchor -- the country's settled terminal
    growth for the DCF-shaped classes, the name's cost of equity for Bank and Insurer --
    and, beside them, per-name absolute beliefs; a further per-name file (--beliefs) holds
    the same absolute form and overrides them; [resolve] turns either into decimal
    fractions on the record.

    The parameter is fixed on the merits: what the model observes stays observed (starting
    growth, roe_0), the reversion speed stays a structural assumption with its sensitivity
    shown, and the belief sits on the long-run level, which is the question an investor can
    answer. On the residual-income path a zero offset is the cost of equity, which is brief
    15's anchor and grants no franchise value; only the width and the ceiling say a
    franchise might hold above it. Either choice may be revisited only on an argument about
    the model, never on what it does to a number. *)

val load_classes_string : string -> (Reference_t.class_beliefs, string) result
(** Also checks the optional [correlation] section (35): exactly common, why, as_of and
    pairs of exactly a, b, rho, why, as_of; common in [0, 1), rho in (-1, 1). *)

val load_classes : string -> (Reference_t.class_beliefs, string) result
val load_names_string : string -> (Reference_t.name_beliefs, string) result
val load_names : string -> (Reference_t.name_beliefs, string) result

val surplus_curve : Boundary_t.belief -> f:(float -> float) -> price:float -> Boundary_t.surplus_point list
(** (35) The value surplus [(f x - price) / price] at 41 evenly spaced values of the
    belief's parameter, from its floor to its ceiling: long-run growth on the DCF-shaped
    paths and (58) the long-run return on equity on the residual-income path. *)

type outcome = Solved | Above | Below | Flat
(** (58) Which end a bisection came out of, so the probability mapping reads a tag rather
    than comparing reason strings. *)

val growth_axis : string
val roe_axis : string
(** The two values of the record's [belief_parameter]. *)

val resolve :
  classes:Reference_t.class_beliefs ->
  ?names:Reference_t.name_beliefs ->
  ticker:string ->
  entity_class:string ->
  anchor:float ->
  anchor_name:string ->
  unit ->
  (Boundary_t.belief * string) option
(** The per-name entry when there is one (absolute; a [names] file given as --beliefs
    first, then the tracked names section), else the class default (offsets in percentage
    points around [anchor], which [anchor_name] names in the source text: the country's
    terminal growth on the DCF-shaped paths and (58) the cost of equity on the
    residual-income path), else [None]; with the source text. *)

val version : Boundary_t.belief -> source_kind:string -> string
(** [as_of-<7 hex of the six fields>-<class|name>]: changes when any field changes. *)

val cdf : Boundary_t.belief -> float -> float
(** The truncated normal's CDF: 0 at or below the floor, 1 at or above the ceiling,
    [(Phi((x-m)/s) - Phi((a-m)/s)) / (Phi((b-m)/s) - Phi((a-m)/s))] between, Phi via
    [Float.erf]; a degenerate belief (the mass outside the bounds) is a step at the
    mean held into the bounds. *)

val implied_terminal_growth :
  f:(float -> float) -> price:float -> rate:float -> Boundary_t.readout * float list * outcome
(** Bisection on long-run growth in [-0.10, rate - 0.0005] of [f], the fair value at a
    terminal growth with everything else held; null with reason past either end. Also
    the domain and which end it came out of. *)

val implied_roe_target :
  f:(float -> float) -> price:float -> cost_of_equity:float -> Boundary_t.readout * float list * outcome
(** (58) The same in the long-run return on equity, over [Implied.roe_target_domain]. *)

val readout :
  Boundary_t.belief -> source:string -> source_kind:string -> axis:string ->
  implied:Boundary_t.readout -> implied_domain:float list -> outcome:outcome ->
  price:float -> fair_value:float -> Boundary_t.belief_readout
(** The belief block: the declaration, its version, the implied value of its parameter and
    the probability the parameter falls below it. [Solved] takes the CDF there; [Below] is
    0, [Above] is 1, and [Flat] is 1 or 0 by whether fair value is under the price. *)

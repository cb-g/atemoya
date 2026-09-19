(** Declared beliefs on long-run growth (24). A belief is six fields and nothing else:
    mean, sd, floor, ceiling, why, as_of, a truncated normal. The loaders are strict
    (an unknown or missing field, a non-positive sd, a floor at or above the ceiling,
    an empty why or a malformed as_of is an [Error] naming the entry), and nothing here
    estimates a field from history. Values in the files are percentage points: the
    tracked table holds class offsets around the country's settled terminal growth and,
    beside them, per-name absolute beliefs; a further per-name file (--beliefs) holds the
    same absolute form and overrides them; [resolve] turns
    either into decimal fractions on the record.

    The belief parameter is terminal growth, fixed on the merits: starting growth is
    observed, the reversion speed is a structural assumption with its sensitivity shown,
    long-run growth is the question every investor can answer. This choice may be
    revisited only on an argument about the model, never on what it does to a number. *)

val load_classes_string : string -> (Reference_t.class_beliefs, string) result
(** Also checks the optional [correlation] section (35): exactly common, why, as_of and
    pairs of exactly a, b, rho, why, as_of; common in [0, 1), rho in (-1, 1). *)

val load_classes : string -> (Reference_t.class_beliefs, string) result
val load_names_string : string -> (Reference_t.name_beliefs, string) result
val load_names : string -> (Reference_t.name_beliefs, string) result

val surplus_curve : Boundary_t.belief -> f:(float -> float) -> price:float -> Boundary_t.surplus_point list
(** (35) The value surplus [(f g - price) / price] at 41 evenly spaced long-run growths
    from the belief's floor to its ceiling. *)

val resolve :
  classes:Reference_t.class_beliefs ->
  ?names:Reference_t.name_beliefs ->
  ticker:string ->
  entity_class:string ->
  terminal_growth_rate:float ->
  unit ->
  (Boundary_t.belief * string) option
(** The per-name entry when there is one (absolute; a [names] file given as --beliefs
    first, then the tracked names section), else the class default (offsets around
    [terminal_growth_rate]), else [None]; with the source text. *)

val version : Boundary_t.belief -> source_kind:string -> string
(** [as_of-<7 hex of the six fields>-<class|name>]: changes when any field changes. *)

val cdf : Boundary_t.belief -> float -> float
(** The truncated normal's CDF: 0 at or below the floor, 1 at or above the ceiling,
    [(Phi((x-m)/s) - Phi((a-m)/s)) / (Phi((b-m)/s) - Phi((a-m)/s))] between, Phi via
    [Float.erf]; a degenerate belief (the mass outside the bounds) is a step at the
    mean held into the bounds. *)

val implied_terminal_growth :
  f:(float -> float) -> price:float -> rate:float -> Boundary_t.readout * float list
(** Bisection on long-run growth in [-0.10, rate - 0.0005] of [f], the fair value at a
    terminal growth with everything else held; null with reason past either end. Also
    the domain. *)

val readout :
  Boundary_t.belief -> source:string -> source_kind:string ->
  f:(float -> float) -> price:float -> rate:float -> fair_value:float -> Boundary_t.belief_readout

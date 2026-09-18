(** Assembles the per-ticker output contract: the declared entity class checked
    against the statement signatures, the admissibility decision, parameter
    resolution, the model, sanity checks, signal, floor, and the
    [`Failed]-with-nulls shape.

    Order: declaration and class check -> admissibility -> country -> resolve
    parameters -> value. No declaration, or a signature contradicting a declared
    [`OperatingCompany], is [`Failed] before anything else. A class the table
    does not admit the dcf for is [`Failed] with the lens named, so the reader
    learns what the right measurement is. Nothing here moves a number: the
    arithmetic is [Dcf.value], unchanged. [floor] is always populated and gates
    nothing. *)

type thresholds = {
  buy_above : float;  (** margin of safety at or above which the signal is [`Buy] *)
  sell_below : float;  (** margin of safety at or below which the signal is [`Sell] *)
  sanity_bound : float;  (** a margin of safety above this is [`Failed] *)
}

val default_thresholds : thresholds

val signal : thresholds -> float -> Boundary_t.signal

(** A human's declaration of what the company is, from the universe file or the
    command line. *)
type declaration = {
  entity_class : Boundary_t.entity_class;
  lens_note : string;
  scope_limits : string list;
}

val run :
  ?thresholds:thresholds ->
  Params.t ->
  today:string ->
  declaration:declaration option ->
  Boundary_t.financials ->
  Boundary_t.valuation
(** [today] is the ISO 8601 date parameter ages are measured at; it is echoed
    as [valued_on]. *)

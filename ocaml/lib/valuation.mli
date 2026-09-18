(** Assembles the per-ticker output contract: the declared entity class checked
    against the statement signatures, the admissibility decision, the currency
    gate, parameter resolution, the routed model, sanity checks, signal, floor,
    and the [`Failed]-with-nulls shape.

    Order: declaration and class check -> admissibility -> country -> currency
    gate -> resolve parameters -> the first admissible model -> sanity bound ->
    record. The currency gate: with both currencies present and equal the
    same-currency path runs exactly as before; otherwise the record's statement
    totals are converted at one recorded FX rate into the trading currency, the
    parameters come from [Params.resolve_cross], the same model runs on the
    converted record, and the conversion rides on its inputs. A missing currency
    field or FX pair is [`Failed] naming it. Each model's arithmetic lives in its
    own module. [floor] is always populated and gates nothing. *)

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

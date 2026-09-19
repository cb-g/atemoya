(** Assembles the per-ticker output contract: the declared entity class checked
    against the statement signatures, the admissibility decision, the currency
    gate, parameter resolution, the routed model, sanity checks, signal, floor,
    and the [`Failed]-with-nulls shape.

    Order: declaration and class check -> admissibility -> country -> currency
    agreement (a filing's unit against the vendor's statement currency) -> field
    definitions -> filing age -> currency gate -> resolve parameters -> the first
    admissible model -> sanity bound -> record. The field-definitions gate: a
    record whose periods carry a composition naming another definition than
    [reference/field_definitions.json] (or an ebit recipe it does not list) is
    [`Failed] naming both, so statements fetched under one definition are never
    valued under another; a record naming none passes. The currency gate: with both currencies present and equal the
    same-currency path runs exactly as before; otherwise the record's statement
    totals are converted at one recorded FX rate into the trading currency, the
    parameters come from [Params.resolve_cross], the same model runs on the
    converted record, and the conversion rides on its inputs. A missing currency
    field or FX pair is [`Failed] naming it. On the dcf path a derived ebit (any
    recipe but operating income) runs only when the record's cross-check found it
    within threshold of the vendor's operating income; otherwise the
    [refinement_policy.on_miss] [`Failed]. Each model's arithmetic lives in its own
    module. [floor] is always populated and gates nothing. An [`Ok] record carries
    the implied readouts ([Implied]); the headline never depends on them. *)

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

val currency_agreement : Boundary_t.financials -> (unit, string) result
(** [`Failed] naming both when the filing's currency and the vendor's disagree. *)

val definitions_check :
  Reference_t.field_definitions -> Boundary_t.financials -> (unit, string) result
(** The field-definitions gate on every period of the record. *)

val run :
  ?thresholds:thresholds ->
  Params.t ->
  today:string ->
  declaration:declaration option ->
  Boundary_t.financials ->
  Boundary_t.valuation
(** [today] is the ISO 8601 date parameter ages are measured at; it is echoed
    as [valued_on]. *)

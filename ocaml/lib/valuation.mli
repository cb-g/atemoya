(** Assembles the per-ticker output contract: classification, parameter
    resolution, model dispatch, sanity checks, signal, and the
    [`Failed]-with-nulls shape.

    Order: classify -> country -> resolve parameters -> value. A [`Bank] or
    [`Insurer] is [`Failed] with "model not implemented" before any parameter is
    resolved, so it never reaches the generic arithmetic and its reason is not
    masked by a stale rate. An unresolved classification, a fetch without a
    country, a country missing from the reference tables, a stale parameter, a
    non-positive fair value, or a margin of safety beyond [sanity_bound] is
    [`Failed] with the reason. When the arithmetic completed first, [inputs] is
    kept for audit. *)

type thresholds = {
  buy_above : float;  (** margin of safety at or above which the signal is [`Buy] *)
  sell_below : float;  (** margin of safety at or below which the signal is [`Sell] *)
  sanity_bound : float;  (** a margin of safety above this is [`Failed] *)
}

val default_thresholds : thresholds

val signal : thresholds -> float -> Boundary_t.signal

val run :
  ?thresholds:thresholds ->
  Params.t ->
  today:string ->
  Boundary_t.financials ->
  Boundary_t.valuation
(** [today] is the ISO 8601 date parameter ages are measured at; it is echoed
    as [valued_on]. *)

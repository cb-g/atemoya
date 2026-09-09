(** Assembles the per-ticker output contract: classification, model dispatch,
    sanity checks, signal, and the [`Failed]-with-nulls shape.

    A non-positive fair value or a margin of safety beyond [sanity_bound] is
    [`Failed] with the reason and, since the arithmetic completed, with
    [inputs] populated for audit. *)

type thresholds = {
  buy_above : float;  (** margin of safety at or above which the signal is [`Buy] *)
  sell_below : float;  (** margin of safety at or below which the signal is [`Sell] *)
  sanity_bound : float;  (** a margin of safety above this is [`Failed] *)
}

val default_thresholds : thresholds

val signal : thresholds -> float -> Boundary_t.signal

val run :
  ?assumptions:Dcf.assumptions ->
  ?thresholds:thresholds ->
  Boundary_t.financials ->
  Boundary_t.valuation

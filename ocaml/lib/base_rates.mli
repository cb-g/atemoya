(** The base rate beside the record's growth: how often companies of the same starting size
    grew their revenue as fast, over five years, as the record's own growth path assumes and
    as the price needs. The outside view from filed history (python/base_rates.py builds the
    table from SEC's frames); a frequency, never a belief and never an input to a fair value.

    Contract. [of_inputs] returns the block, or the reason there is none: no table fetched,
    a record not in dollars, no revenue on the latest period, no table for the size class.
    The record's own path is always there on a completed DCF; the path the price needs comes
    from [implied_g0], and where that readout is null its reason is carried and the headline
    side stands alone. A share is the fraction of the class's percentiles at or above the
    growth, linear between percentile points and held to [0.01, 0.99], since the table has
    no finer resolution. *)

val horizon : int
(** 5 *)

val compound : float list -> years:int -> float option
(** The compound annual rate over the first [years] entries of a growth path; [None] when
    the path is shorter. *)

val share_at_or_above : float list -> float -> float
(** [percentiles] are the 1st to 99th, ascending. *)

val scope_limits : string list

val of_inputs :
  Reference_t.base_rates option ->
  currency:string option ->
  revenue:float option ->
  inputs:Boundary_t.inputs ->
  implied:(Boundary_t.implied, string) result ->
  Boundary_t.base_rate option * string option

(** The four-quarter shadow: the generic DCF on the statements' trailing period, the last four
    filed quarters as one period, the annual periods behind it as history. Beside the headline,
    never the headline: nothing here moves a fair value, a margin or a signal.

    Contract: [value] returns [Ok shadow] with the shadow's complete inputs, or [Error reason]
    when the statements carry no trailing period (the fetcher's reason), when the trailing
    period's ebit is derived and so unchecked, or when the DCF refuses the trailing base (the
    DCF's reason, prefixed). [base_limits] is the one sentence on every Ok record with a
    recency block saying which annual period the models read, how far the quarters have moved
    on, which way the fair value leans for it, and whether a shadow stands beside it. *)

val rule : string
val no_trailing : string
val scope_limits : string list

val value :
  ?declared:string ->
  Dcf.assumptions ->
  country:string ->
  Boundary_t.financials ->
  fair_value:float ->
  (Boundary_t.four_quarter_shadow, string) result
(** [fair_value] is the headline's, recorded on the block for the comparison. *)

val base_limits :
  recency:Boundary_t.recency option ->
  generic:bool ->
  shadow:(Boundary_t.four_quarter_shadow, string) result option ->
  string list
(** [generic] is whether the record's model is the generic DCF, the one path a shadow runs on. *)

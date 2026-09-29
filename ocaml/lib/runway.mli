(** The runway readout (76) for the Unprofitable class: cash against the burn as this tool
    reads it, and the releases the earnings calendar puts inside it. A state, not a
    forecast; never a fair value, a floor or a signal; the record stays [Failed] with the
    class's own reason and this rides beside it. *)

val free_cash_flow : Boundary_t.fiscal_period -> float option
(** operating cash flow less capex when both are present: the cash-flow statement's own lines. *)

val releases_within :
  years:float -> days_to_next:int -> cadence_days:float -> int
(** How many releases fall inside [years] from today at the calendar's cadence, counting the
    next one when it has not passed: zero when the next lies beyond the runway or the
    cadence is not positive. *)

val of_record :
  entity_class:Boundary_t.entity_class option ->
  periods:Boundary_t.fiscal_period list ->
  calendar:Boundary_t.earnings_calendar option ->
  calendar_reason:string option ->
  valued_on:string ->
  Boundary_t.runway option * string option
(** [(None, None)] for every class but Unprofitable: the question is not the record's.
    On an Unprofitable record, the block, or the reason there is none. *)

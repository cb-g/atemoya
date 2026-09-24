(** (68) The earnings gate: what the option market charges for the next results release.

    The calendar — the filed 8-K item 2.02 dates or the vendor's, the next date and its
    source, and the realised moves — is built at the fetch and carried on the financials.
    This module adds the one thing the fetch cannot see, because it needs the options store:
    the implied event move.

    The event's variance is the later expiry's total variance less the earlier's, both read
    at the forward on the fitted smile. SVI parameterises TOTAL implied variance, so [w(0)]
    is the brief's "implied volatility squared times years" exactly, with no round trip
    through a volatility; and both legs take one forward convention, because the event
    variance is a difference of two close numbers and mixing conventions between them is
    noise exactly where the answer is.

    It never fails a record, adds no [Failed] string, and nothing downstream reads it. *)

val bracket : Boundary_t.option_chain -> next:string -> (string * string, string) result
(** The two listed expiries bracketing [next]: the latest strictly before it and the
    earliest on or after it. An expiry ON the release date is the later leg, because a
    release is dated by its filing day and an option expiring that day is still exposed to
    one made before the open. [Error] names which side is missing. *)

val implied_of :
  Boundary_t.option_chain -> rf:float -> next:string ->
  (Boundary_t.earnings_implied, string) result
(** The implied event move, or the reason there is none: no expiry on one side, a smile that
    would not fit at one of them, or a term structure whose later total variance is below
    the earlier's — no event premium, which is a reading and not a gap. *)

val spans : expiry:string -> next:string -> bool
(** Whether an expiry lies at or after the next release, so a structure held to it carries
    the event. Nothing is excluded or re-ranked by this; it is a mark. *)

val block_of :
  calendar:Boundary_t.earnings_calendar -> valued_on:string ->
  implied:(Boundary_t.earnings_implied, string) result -> Boundary_t.earnings
(** The calendar with the implied half and the days to the release from [valued_on], which
    is negative when the calendar has aged past it. *)

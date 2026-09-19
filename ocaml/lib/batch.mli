(** The human-readable summary of a batch of valuations: counts by status,
    entity class and failure reason, one line per ticker, and, when the
    universe is given, whether each ticker met its expected outcome. Pure and
    deterministic for a given input order. *)

val reason_key : string -> string
(** A failure reason with its parenthesised specifics and any named lens
    dropped, for grouping: inadmissible refusals group by class. *)

val meets_expectation :
  Reference_t.universe_entry -> Boundary_t.valuation -> bool
(** Status matches, and when the entry names an expected reason, the record's
    reason starts with it. *)

val summary :
  ?universe:Reference_t.universe -> Boundary_t.valuation list -> string
(** Includes a cross-check line: how many records with a cross-check had any
    field beyond threshold, and which fields most often. *)

val provider_diff : (Boundary_t.valuation * Boundary_t.valuation option) list -> string
(** One block per record whose statements provider is not the vendor, given
    the vendor-statement shadow valuation of the same name when there is one:
    old fair value, new fair value, the delta, and the three fields whose
    values differ most between the providers, with both numbers; every other
    record is listed as unchanged. A moved number without a field-level
    explanation here is a bug. *)

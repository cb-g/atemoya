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
  ?universe:Reference_t.universe ->
  ?definitions:Reference_t.field_definitions ->
  Boundary_t.valuation list ->
  string
(** Includes the field definitions in force when given, and a cross-check
    section: how many records with a cross-check had any field beyond
    threshold, which fields most often, then every such record with each
    disagreeing field's two values and the universe entry's characterisation
    of the gap when it has one. *)

val drivers : Boundary_t.model_inputs -> (string * float * string) list
(** Every input a fair value can move with, by model: the statement fields,
    price, market cap and effective shares, and each parameter's value; the
    third element describes the recipe or composition behind a composed field,
    empty otherwise. Intermediates (nopat, wacc, growth) are not listed: they
    are functions of these. *)

val run_diff :
  baseline:Boundary_t.valuation list -> Boundary_t.valuation list -> string
(** This run against a baseline run, every record: status and fair value on
    both sides, the delta, and for a moved fair value every driver whose value
    differs, old and new, with the composition behind it. A moved fair value
    with no differing driver is printed as such: the arithmetic itself changed,
    or it is a bug. Records only one side has are listed. *)

val provider_diff : (Boundary_t.valuation * Boundary_t.valuation option) list -> string
(** One block per record whose statements provider is not the vendor, given
    the vendor-statement shadow valuation of the same name when there is one:
    old fair value, new fair value, the delta, and the three fields whose
    values differ most between the providers, with both numbers; every other
    record is listed as unchanged. A moved number without a field-level
    explanation here is a bug. *)

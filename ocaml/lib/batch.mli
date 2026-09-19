(** The human-readable summary of a batch of valuations: counts by status,
    entity class and failure reason, one line per ticker, and, when the
    universe is given, which of its names were not run. Pure and deterministic
    for a given input order. Whether anything changed since the last run, and
    why, is the baseline diff ([run_diff]), never a stored expectation. *)

val reason_key : string -> string
(** A failure reason with its parenthesised specifics and any named lens
    dropped, for grouping: inadmissible refusals group by class. *)

val summary :
  ?universe:Reference_t.universe ->
  ?definitions:Reference_t.field_definitions ->
  ?stability_line:string ->
  Boundary_t.valuation list ->
  string
(** Includes the field definitions in force when given, the universe-level
    implied line (median and range of the solved half-lives, the counts beyond
    range each way, the count where level is the meaningful readout), and a
    cross-check section: how many records with a cross-check had any field beyond
    threshold, which fields most often, then every such record with each
    disagreeing field's two values and their relative difference, and
    nothing else: a finding, never explained by the run. *)

val drivers : Boundary_t.model_inputs -> (string * float * string) list
(** Every input a fair value can move with, by model: the statement fields,
    price, market cap and effective shares, and each parameter's value; the
    third element describes the recipe or composition behind a composed field,
    empty otherwise. Intermediates (nopat, wacc, growth) are not listed: they
    are functions of these. *)

val run_diff :
  ?baseline_raw:(string * Yojson.Safe.t) list ->
  baseline:Boundary_t.valuation list ->
  Boundary_t.valuation list ->
  string
(** This run against a baseline run, every record: status and fair value on
    both sides, the delta, and for a moved fair value every driver whose value
    differs, old and new, with the composition behind it, and, given the
    baseline's raw JSON per ticker, every input field the baseline carried that
    the model no longer has, with its value (a removed term is a driver). A
    moved fair value with no differing driver and nothing removed is printed
    as such: the arithmetic itself changed, or it is a bug. Status lines carry
    the signal. Records only one side has are listed. *)

val provider_diff : (Boundary_t.valuation * Boundary_t.valuation option) list -> string
(** One block per record whose statements provider is not the vendor, given
    the vendor-statement shadow valuation of the same name when there is one:
    old fair value, new fair value, the delta, and the three fields whose
    values differ most between the providers, with both numbers; every other
    record is listed as unchanged. A moved number without a field-level
    explanation here is a bug. *)

(** {1 Stability (16): the same name on two snapshots} *)

type stability_class = Price | New_filing | Restated | Vendor_row | Rate_or_fx | Unexplained
(** Why an input moved between two fetches: the market price or cap; a newer filing
    (the accession changed); the same filing's value changed; a vendor-path value
    moved with no filing behind it; a rate, FX or curve parameter; anything else. *)

val class_name : stability_class -> string

type moved_input = { name : string; old_value : float; new_value : float; klass : stability_class }

val moved_inputs :
  old:Boundary_t.valuation * Boundary_t.financials option ->
  now:Boundary_t.valuation * Boundary_t.financials option ->
  moved_input list
(** Every input that moved between the two records of one ticker, classified; the
    financials supply the accession of the fiscal period valued. A record whose
    status, model or provider differs is one [Unexplained] item naming it. *)

val stability :
  snapshot_old:string ->
  snapshot_new:string ->
  old:(Boundary_t.valuation * Boundary_t.financials option) list ->
  now:(Boundary_t.valuation * Boundary_t.financials option) list ->
  string * string
(** The report and the one-line count per class for the summary. Says whether
    rates or FX were refreshed between the runs (the risk-free as_of differs). *)

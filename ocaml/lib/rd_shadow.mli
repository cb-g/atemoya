(** The R&D shadow: the generic DCF's value with research and development read as an
    investment, beside the headline and never replacing it.

    Contract. [of_dcf] is called on a record whose generic DCF completed. It returns the
    block, or the reason there is none; it never moves the record's fair value, margin of
    safety or signal. The expense of the latest fiscal year and of the [life] years before
    it must all be filed, one per consecutive fiscal year: a gap, or fewer years, is a
    reason and never a shorter schedule, since a research asset built from part of its
    history is an understated one that looks exact. Money is in the currency of the
    statements the DCF saw.

    The arithmetic, straight-line over [life] = N years with the latest year unamortised:
    research asset = sum over k = 0..N-1 of expense(t-k) * (N-k)/N; amortisation = sum over
    k = 1..N of expense(t-k) / N. The latest period is then restated: operating profit gains
    (expense - amortisation) / (1 - tax rate), so that after-tax operating profit gains the
    net investment untaxed (the expense stays deductible); capital spending gains the
    expense; depreciation gains the amortisation; book equity gains the asset. Free cash
    flow is unchanged by construction and the block records both sides as the check. The
    same [Dcf.value] then runs on the restated statements. *)

type schedule = {
  rd_latest : float;
  rd_tag : string;
  rd_years : string list;  (** the latest year end and the [life] before it, newest first *)
  research_asset : float;
  amortization : float;
}

val schedule : life:int -> latest:string -> Boundary_t.rd_year list -> (schedule, string) result
(** The schedule for the fiscal year ending [latest], or why there is none. *)

val restate : tax_rate:float -> schedule -> Boundary_t.fiscal_period -> Boundary_t.fiscal_period option
(** The period with research and development capitalised; [None] when a line it restates is absent. *)

val scope_limits : string list

val of_dcf :
  ?declared:string ->
  life:Reference_t.int_scalar option ->
  Dcf.assumptions ->
  country:string ->
  Boundary_t.financials ->
  headline:Boundary_t.inputs * float ->
  Boundary_t.rd_shadow option * string option
(** [fin] is the statements the headline DCF ran on (converted when cross-currency);
    [headline] its inputs and fair value. Exactly one side of the pair is [Some]. *)

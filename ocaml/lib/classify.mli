(** Which valuation model applies to a company, decided from its statements.

    [Boundary_t.model] is a closed variant, so every caller must handle every
    constructor: a model that does not exist yet is a compile-time case, never
    a silent fall-through to the generic one.

    Contract: [classify] reads the latest fiscal period. Bank iff
    [net_interest_income / total_revenue >= threshold] (a materiality ratio; the
    vendor reports a net interest income row for every company, so a sign test
    is wrong). Insurer iff [premiums_earned > 0]. Bank takes precedence. Only
    when the statements give no signature is the vendor's industry string
    consulted, and it can only produce [Unresolved]: it never classifies. With
    no signature and no hint, the company is [`Generic]. The returned
    [Boundary_t.classification] is the evidence, always populated. *)

type outcome = Classified of Boundary_t.model | Unresolved of string

val classify :
  threshold:Boundary_t.parameter ->
  Boundary_t.financials ->
  outcome * Boundary_t.classification

val model_name : Boundary_t.model -> string

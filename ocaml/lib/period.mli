(** The fiscal period a valuation or classification reads: the most recent by
    [period_end], regardless of the order the vendor delivered them in. *)

val latest : Boundary_t.financials -> Boundary_t.fiscal_period option

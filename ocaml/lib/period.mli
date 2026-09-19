(** The fiscal period a valuation or classification reads: the most recent by
    [period_end], regardless of the order the vendor delivered them in. *)

val latest : Boundary_t.financials -> Boundary_t.fiscal_period option

val value : Boundary_t.fiscal_period -> string -> float option
(** A statement field by the name the reference uses for it (ebit, net_income,
    interest_expense, depreciation_amortization, capex, delta_nwc, cash, total_debt,
    book_equity, pretax_income, tax_provision, total_revenue, dividends_paid, ffo,
    aoci, premiums_earned); [None] when absent. @raise Invalid_argument on a name
    the period has no field for. *)

val missing : Boundary_t.fiscal_period -> string list -> string list
(** The names in the list the period lacks, in the list's order. *)

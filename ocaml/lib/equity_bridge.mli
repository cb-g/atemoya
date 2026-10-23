(** The equity bridge: what stands between the enterprise value a cash flow supports and the
    common equity the share count divides, beyond net debt
    ([reference/field_definitions.json], equity_bridge).

    Contract. [of_period] reads ten items from the valued period and the financials, in the
    record's currency, and applies each only where the cash flow it pairs with leaves it out:
    minority interests, redeemable ones included, are deducted, and associates and long-term
    financial investments added at their carrying value, where the cash flow starts from
    consolidated operating income (associates not where the filing shows their earnings
    inside it, nor on IFRS statements where its subtotals do not place them below), none of them where it is built from the parent's net
    income, and minority interests not where the share count is declared to hold the units
    already; the defined-benefit plans' net liability is deducted after tax at the statutory
    rate, a surplus added, where the cash flow starts from operating income, not on the
    parent's net income; litigation accrued on US GAAP statements is deducted on every cash
    flow, less the filer's deferred tax asset on it where filed, else after tax, and IFRS
    decommissioning and legal provisions, else the noncurrent provisions, after tax where the
    cash flow starts from operating income; lease liabilities outside the debt rows are deducted on IFRS
    statements and on the vendor's statements of a filer outside the United States;
    contingent consideration and preferred stock wherever filed; what went to shareholders
    since the annual base, from the latest 10-Q, where the valued period is that base, and
    beside the minority interest, where it is deducted, what was paid since the base to buy
    minority interests out above the book they removed. Every item is on the block, applied or
    not, with why; an item not read has a null value and deducts nothing. [total] is the sum
    of the deductions, so [equity_value = enterprise_value - net_debt - total]. Nothing here
    moves the cash flow, the discount rate or the share count. *)

val definition : string
(** The definition's name in [reference/field_definitions.json]. *)

type cash_flow =
  | Consolidated_operating_income  (** the generic DCF, and the mid-cycle path on filed operating income *)
  | Parent_net_income  (** the mid-cycle path built bottom-up from net income attributable to the parent *)

val leases_outside_debt : Boundary_t.financials -> bool
(** IFRS statements, or the vendor's statements of a filer outside the United States. *)

val of_period :
  cash_flow:cash_flow ->
  statutory_tax_rate:float ->
  ?share_count_includes_minority:string ->
  Boundary_t.financials ->
  Boundary_t.fiscal_period ->
  Boundary_t.equity_bridge

val total : Boundary_t.inputs -> float
(** The block's total, or 0 on inputs written before it. *)

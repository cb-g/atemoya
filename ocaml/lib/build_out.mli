(** The build-out readout (60): for a name whose reported cash flow is negative because it
    is investing more than it earns, and whose earning history at scale is too short for the
    mid-cycle window, the surface of value across what the new capital earns and how long it
    takes to earn it, with the price drawn as a contour.

    It is a map of what the price requires, not a value. The record stays [Failed] with its
    own reason; this block carries no fair value, no margin of safety and no signal, and
    nothing downstream reads it. *)

val returns_axis : float -> float list
(** Thirty-one returns, the declared one in the middle, from fifteen points under it to
    fifteen over in one-point steps. *)

val lags : int list
(** [0 .. 6] whole years from spend to first earning. *)

val growth_capex : capex:float -> depreciation_amortization:float -> float
(** Capex less depreciation where positive, else zero: depreciation is the proxy for
    maintenance because no filer discloses the split. *)

val cash_return : accounting_return:float -> depreciation_to_capital:float -> float
(** (63) The declaration is an after-tax return on capital AFTER depreciation, the units a
    filing and a reader use; this is the cash yield before the maintenance the readout
    charges, which is the same ratio. Both figures go on the record. *)

val value_per_share :
  standing:float ->
  tranches:Boundary_t.build_out_tranche list ->
  depreciation_to_capital:float ->
  wacc:float ->
  net_debt:float ->
  shares:float ->
  build_out_return:float ->
  lag_years:int ->
  float
(** The standing business plus the build-out, less net debt, per effective share.
    [build_out_return] is the accounting return, as declared (63): each tranche earns the
    cash yield it converts to on its cost from [lag_years] after the year it was spent,
    less its own maintenance at [depreciation_to_capital], as a flat perpetuity discounted
    at [wacc]; a tranche whose earning year has already arrived is not discounted further. *)

val of_record :
  declared_return:Reference_t.declared_build_out ->
  declared_lag_years:Reference_t.declared_build_out ->
  periods:Boundary_t.fiscal_period list ->
  price:float ->
  market_cap:float ->
  cash:float ->
  total_debt:float ->
  book_equity:float ->
  wacc:float ->
  tax_rate:float ->
  terminal_growth_rate:float ->
  scope_limits:string list ->
  (Boundary_t.build_out, string) result
(** The whole block from one record's latest periods, or the reason there is none.
    [declared_return] is the accounting return (63); the block carries the cash return it
    converts to beside it, and the return axis and the price contour are in accounting
    terms, as the declaration is. *)

val gate :
  entity_class:Boundary_t.entity_class option ->
  failed_reason:string ->
  periods:Boundary_t.fiscal_period list ->
  (unit, string) result option
(** Whether the readout applies. [None] is out of scope and carries no finding: the class is
    not [Cyclical] or [OperatingCompany], or the record failed for a reason that says nothing
    about a build-out, and neither field appears on it. [Some (Error why)] is a record the
    readout is about that cannot be drawn — the latest capex does not exceed depreciation,
    the latest operating income is not positive, or a field is missing — and [why] goes on
    the record. It is never a [Failed] string: the record's own reason stands. *)

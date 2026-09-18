(** Deterministic single-currency free-cash-flow-to-firm DCF.

    Contract: [value] returns [Ok (inputs, fair_value)] with every field of
    [inputs] and [fair_value] finite, or [Error reason]. It never substitutes a
    value for a missing statement field or missing market data; that is an
    [Error]. The only fallback is the country's statutory tax rate when no sane
    effective rate is derivable, and then [inputs.tax_rate_source] says so.

    Every rate and horizon arrives as a [Boundary_t.parameter] carrying its
    provenance, which [value] copies into [inputs] untouched. Nothing here is
    hardcoded; [Params.resolve] builds [assumptions] from [reference/]. *)

type assumptions = {
  risk_free_rate : Boundary_t.parameter;
  equity_risk_premium : Boundary_t.parameter;
  beta : Boundary_t.parameter;
  beta_source : Boundary_t.beta_source;
  debt_spread : Boundary_t.parameter;
      (** pre-tax cost of debt = risk_free_rate + debt_spread *)
  growth_rate : Boundary_t.parameter;  (** explicit projection, per year *)
  terminal_growth_rate : Boundary_t.parameter;
  projection_years : Boundary_t.int_parameter;
  statutory_tax_rate : Boundary_t.parameter;
      (** used when no effective rate in [0, max_effective_tax_rate] is derivable *)
}

val max_effective_tax_rate : float

val fcff :
  ebit:float ->
  tax_rate:float ->
  depreciation_amortization:float ->
  capex:float ->
  delta_nwc:float ->
  float
(** [ebit * (1 - tax_rate) + depreciation_amortization - capex - delta_nwc]. *)

val wacc :
  cost_of_equity:float ->
  cost_of_debt:float ->
  tax_rate:float ->
  market_cap:float ->
  total_debt:float ->
  float
(** Market-cap and book-debt weighted; [cost_of_debt] is pre-tax. *)

val enterprise_value :
  fcff:float ->
  wacc:float ->
  growth_rate:float ->
  terminal_growth_rate:float ->
  projection_years:int ->
  float
(** Present value of [projection_years] of [fcff] growing at [growth_rate], plus a
    Gordon terminal value at [terminal_growth_rate]. Requires
    [wacc > terminal_growth_rate] and [projection_years >= 0]; [value] checks
    both before calling. *)

val tax_rate :
  statutory:float ->
  pretax_income:float option ->
  tax_provision:float option ->
  float * Boundary_t.tax_rate_source
(** Effective rate [tax_provision / pretax_income] when [pretax_income > 0] and the
    result lies in [0, max_effective_tax_rate]; otherwise [statutory]. *)

val value :
  assumptions ->
  country:string ->
  Boundary_t.financials ->
  (Boundary_t.inputs * float, string) result
(** Values the most recent fiscal period. [country] is the fetched string,
    recorded in [inputs] as is. See the module contract. *)

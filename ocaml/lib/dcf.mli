(** Deterministic single-currency free-cash-flow-to-firm DCF.

    Contract: [value] returns [Ok (inputs, fair_value)] with every field of
    [inputs] and [fair_value] finite, or [Error reason]. It never substitutes a
    value for a missing statement field or missing market data; that is an
    [Error]. The only assumption it may fall back to is the statutory tax rate,
    and then [inputs.tax_rate_source] says so. *)

type assumptions = {
  risk_free_rate : float;
  equity_risk_premium : float;
  beta : float;
  debt_spread : float;  (** pre-tax cost of debt = risk_free_rate + debt_spread *)
  growth_rate : float;  (** explicit projection, per year *)
  terminal_growth_rate : float;
  projection_years : int;
  statutory_tax_rate : float;
      (** used when no effective rate in [0, max_effective_tax_rate] is derivable *)
}

val us_defaults : assumptions
(** Hardcoded US assumptions for this first version; layer 1 parameterises them. *)

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
  assumptions ->
  pretax_income:float option ->
  tax_provision:float option ->
  float * Boundary_t.tax_rate_source
(** Effective rate [tax_provision / pretax_income] when [pretax_income > 0] and the
    result lies in [0, max_effective_tax_rate]; otherwise the statutory rate. *)

val value :
  assumptions ->
  Boundary_t.financials ->
  (Boundary_t.inputs * float, string) result
(** Values the most recent fiscal period. See the module contract. *)

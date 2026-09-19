(** Deterministic single-currency free-cash-flow-to-firm DCF.

    Contract: [value] returns [Ok (inputs, fair_value)] with every field of
    [inputs] and [fair_value] finite, or [Error reason]. It never substitutes a
    value for a missing statement field or missing market data; that is an
    [Error]. The only fallback is the country's statutory tax rate when no sane
    effective rate is derivable, and then [inputs.tax_rate_source] says so.

    Growth comes from the statements through [Growth] and is never a constant:
    the base FCFF uses the mean change in working capital over at least two
    fiscal periods, the starting growth is selected and clamped, and the
    explicit years mean-revert toward the country's terminal growth. Every
    rate, horizon and knob arrives as a [Boundary_t.parameter] carrying its
    provenance, which [value] copies into [inputs] untouched. *)

type assumptions = {
  risk_free_rate : Boundary_t.parameter;
  equity_risk_premium : Boundary_t.parameter;
  country_risk_premium : Boundary_t.parameter option;
      (** cross-currency only: added to the cost of equity outside beta *)
  beta : Boundary_t.parameter;
  beta_source : Boundary_t.beta_source;
  debt_spread : Boundary_t.parameter;
      (** pre-tax cost of debt = risk_free_rate + debt_spread *)
  growth_clamp_lower : Boundary_t.parameter;
  growth_clamp_upper : Boundary_t.parameter;
  mean_reversion_lambda : Boundary_t.parameter;
  terminal_growth_rate : Boundary_t.parameter;
  projection_years : Boundary_t.int_parameter;
  statutory_tax_rate : Boundary_t.parameter;
      (** used when no effective rate in [0, max_effective_tax_rate] is derivable *)
  midcycle_window_years : Boundary_t.int_parameter;
      (** the mid-cycle DCF's window (22); unused by this module *)
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
  growth_path:float list ->
  terminal_growth_rate:float ->
  float
(** Present value of [fcff] compounded year by year along [growth_path], plus
    a Gordon terminal value at [terminal_growth_rate] on the last year's cash
    flow. Requires [wacc > terminal_growth_rate]; [value] checks it first. *)

val tax_rate :
  statutory:float ->
  pretax_income:float option ->
  tax_provision:float option ->
  float * Boundary_t.tax_rate_source
(** Effective rate [tax_provision / pretax_income] when [pretax_income > 0] and the
    result lies in [0, max_effective_tax_rate]; otherwise [statutory]. *)

val cost_of_equity : assumptions -> float
(** [risk_free_rate + beta * equity_risk_premium (+ country_risk_premium)]. *)

val missing_report : Boundary_t.financials -> Boundary_t.fiscal_period -> nwc_periods:int -> string
(** "missing market data: ...; missing statement fields for fiscal period ending D: ...". *)

val value :
  ?declared:string ->
  assumptions ->
  country:string ->
  Boundary_t.financials ->
  (Boundary_t.inputs * float, string) result
(** Values the most recent fiscal period. [country] is the fetched string,
    recorded in [inputs] as is; [declared] names the class in the non-positive
    free-cash-flow refusal (31): a base FCFF at or below zero is an [Error], since
    the DCF is meaningless on it, not conservative. See the module contract. *)

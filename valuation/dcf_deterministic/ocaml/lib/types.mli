(** Core types for deterministic DCF valuation model *)

(** Basic identifiers *)
type ticker = string [@@deriving show]
type currency = string [@@deriving show]
type country = string [@@deriving show]
type industry = string [@@deriving show]

(** Market data for a security *)
type market_data = {
  ticker : ticker;
  price : float;
  mve : float;  (** Market value of equity *)
  mvb : float;  (** Market value of debt *)
  shares_outstanding : float;
  currency : currency;
  country : country;
  industry : industry;
}
[@@deriving show]

(** Financial statement data *)
type financial_data = {
  ebit : float;
  net_income : float;
  interest_expense : float;
  taxes : float;
  capex : float;
  depreciation : float;
  delta_wc : float;  (** Change in working capital *)
  book_value_equity : float;
  invested_capital : float;
  is_bank : bool;  (** Flag for special bank handling *)
}
[@@deriving show]

(** Cost of capital components *)
type cost_of_capital = {
  ce : float;  (** Cost of equity (CAPM) *)
  cb : float;  (** Cost of borrowing *)
  wacc : float;  (** Weighted average cost of capital *)
  leveraged_beta : float;
  risk_free_rate : float;
  equity_risk_premium : float;
}
[@@deriving show]

(** Valuation parameters *)
type valuation_params = {
  projection_years : int;
  terminal_growth_rate : float;
  growth_clamp_upper : float;
  growth_clamp_lower : float;
  rfr_duration : int;  (** Risk-free rate duration in years (e.g., 7) *)
}
[@@deriving show]

(** Configuration data (loaded from JSON files) *)
type config = {
  risk_free_rates : (country * (int * float) list) list;  (** country -> [(duration, rate)] *)
  equity_risk_premiums : (country * float) list;
  industry_betas : (industry * float) list;  (** Unlevered betas *)
  tax_rates : (country * float) list;  (** Corporate tax rates *)
  params : valuation_params;
}
[@@deriving show]

(** Cash flow projection over multiple years *)
type cash_flow_projection = {
  fcfe : float array;  (** Free cash flow to equity, indexed by year 1..h *)
  fcff : float array;  (** Free cash flow to firm, indexed by year 1..h *)
  growth_rate_fcfe : float;  (** ROE-based growth rate *)
  growth_rate_fcff : float;  (** ROIC-based growth rate *)
  growth_clamped_fcfe : bool;  (** Was FCFE growth rate clamped? *)
  growth_clamped_fcff : bool;  (** Was FCFF growth rate clamped? *)
}
[@@deriving show]

(** Investment signal categories *)
type investment_signal =
  | StrongBuy  (** Both FCFE and FCFF > price *)
  | Buy  (** FCFF > price, FCFE ≈ price *)
  | BuyEquityUpside  (** FCFE > price, FCFF ≈ price *)
  | CautionLong  (** FCFF > price, FCFE < price *)
  | Hold  (** Both ≈ price *)
  | CautionLeverage  (** FCFE > price, FCFF < price *)
  | SpeculativeHighLeverage  (** FCFE < price, FCFF ≈ price *)
  | SpeculativeExecutionRisk  (** FCFE ≈ price, FCFF < price *)
  | Avoid  (** Both < price *)
[@@deriving show]

(** Complete valuation result *)
type valuation_result = {
  ticker : ticker;
  price : float;
  pve : float;  (** Present value of equity via FCFE *)
  pvf_minus_debt : float;  (** Present value of firm via FCFF, minus debt *)
  ivps_fcfe : float;  (** Intrinsic value per share (FCFE method) *)
  ivps_fcff : float;  (** Intrinsic value per share (FCFF method) *)
  margin_of_safety_fcfe : float;  (** (IVPS_FCFE - Price) / Price *)
  margin_of_safety_fcff : float;  (** (IVPS_FCFF - Price) / Price *)
  implied_growth_fcfe : float option;  (** Growth rate implied by market price (FCFE) *)
  implied_growth_fcff : float option;  (** Growth rate implied by market price (FCFF) *)
  signal : investment_signal;
  cost_of_capital : cost_of_capital;
  projection : cash_flow_projection;
}
[@@deriving show]

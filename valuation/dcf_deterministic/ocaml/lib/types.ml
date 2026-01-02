(** Core types for deterministic DCF valuation model *)

type ticker = string [@@deriving show]
type currency = string [@@deriving show]
type country = string [@@deriving show]
type industry = string [@@deriving show]

type market_data = {
  ticker : ticker;
  price : float;
  mve : float;
  mvb : float;
  shares_outstanding : float;
  currency : currency;
  country : country;
  industry : industry;
}
[@@deriving show]

type financial_data = {
  ebit : float;
  net_income : float;
  interest_expense : float;
  taxes : float;
  capex : float;
  depreciation : float;
  delta_wc : float;
  book_value_equity : float;
  invested_capital : float;
  is_bank : bool;
}
[@@deriving show]

type cost_of_capital = {
  ce : float;
  cb : float;
  wacc : float;
  leveraged_beta : float;
  risk_free_rate : float;
  equity_risk_premium : float;
}
[@@deriving show]

type valuation_params = {
  projection_years : int;
  terminal_growth_rate : float;
  growth_clamp_upper : float;
  growth_clamp_lower : float;
  rfr_duration : int;
}
[@@deriving show]

type config = {
  risk_free_rates : (country * (int * float) list) list;
  equity_risk_premiums : (country * float) list;
  industry_betas : (industry * float) list;
  tax_rates : (country * float) list;
  params : valuation_params;
}
[@@deriving show]

type cash_flow_projection = {
  fcfe : float array;
  fcff : float array;
  growth_rate_fcfe : float;
  growth_rate_fcff : float;
  growth_clamped_fcfe : bool;
  growth_clamped_fcff : bool;
}
[@@deriving show]

type investment_signal =
  | StrongBuy
  | Buy
  | BuyEquityUpside
  | CautionLong
  | Hold
  | CautionLeverage
  | SpeculativeHighLeverage
  | SpeculativeExecutionRisk
  | Avoid
[@@deriving show]

type valuation_result = {
  ticker : ticker;
  price : float;
  pve : float;
  pvf_minus_debt : float;
  ivps_fcfe : float;
  ivps_fcff : float;
  margin_of_safety_fcfe : float;
  margin_of_safety_fcff : float;
  implied_growth_fcfe : float option;
  implied_growth_fcff : float option;
  signal : investment_signal;
  cost_of_capital : cost_of_capital;
  projection : cash_flow_projection;
}
[@@deriving show]

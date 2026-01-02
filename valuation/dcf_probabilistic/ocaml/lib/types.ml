(** Core types for probabilistic DCF valuation model *)

type ticker = string [@@deriving show]
type currency = string [@@deriving show]
type country = string [@@deriving show]
type sector = string [@@deriving show]
type industry = string [@@deriving show]

type time_series = {
  ebit : float array;
  net_income : float array;
  capex : float array;
  depreciation : float array;
  current_assets : float array;
  current_liabilities : float array;
  book_value_equity : float array;
  dividend_payout : float array;
  invested_capital : float array;
}
[@@deriving show]

type market_data = {
  ticker : ticker;
  price : float;
  mve : float;
  mvb : float;
  shares_outstanding : float;
  currency : currency;
  country : country;
  sector : sector;
  industry : industry;
}
[@@deriving show]

type regime_parameters = {
  rfr_volatility : float;
  erp_volatility : float;
  beta_volatility : float;
  correlation : float array array;
}
[@@deriving show]

type regime_config = {
  crisis_probability : float;  (** Probability of being in crisis regime (e.g., 0.10 = 10%) *)
  normal_regime : regime_parameters;
  crisis_regime : regime_parameters;
}
[@@deriving show]

type simulation_config = {
  num_simulations : int;
  projection_years : int;
  terminal_growth_rate : float;
  growth_clamp_upper : float;
  growth_clamp_lower : float;
  rfr_duration : int;
  use_bayesian_priors : bool;
  prior_weight : float;
  use_stochastic_discount_rates : bool;  (** Enable stochastic RFR, beta, ERP *)
  rfr_volatility : float;  (** Std dev for RFR sampling (e.g., 0.005 = 50 bps) - used if NOT regime-switching *)
  beta_volatility : float;  (** Std dev for beta sampling (e.g., 0.1) - used if NOT regime-switching *)
  erp_volatility : float;  (** Std dev for ERP sampling (e.g., 0.01 = 1%) - used if NOT regime-switching *)
  use_time_varying_growth : bool;  (** Enable time-varying growth rates *)
  growth_mean_reversion_speed : float;  (** λ parameter for mean reversion (default: 0.3) *)
  use_growth_rate_sampling : bool;  (** Use growth-rate sampling (RECOMMENDED) vs legacy level-based sampling *)
  use_correlated_discount_rates : bool;  (** Use multivariate normal for correlated RFR/ERP/Beta (RECOMMENDED) *)
  discount_rate_correlation : float array array;  (** 3×3 correlation matrix [RFR, ERP, Beta] - used if NOT regime-switching *)
  use_regime_switching : bool;  (** Use regime-switching model (RECOMMENDED for fat tails) *)
  regime_config : regime_config option;  (** Regime parameters (required if use_regime_switching=true) *)
  use_copula_financials : bool;  (** Use Gaussian copula for correlated financial metrics (RECOMMENDED) *)
  financials_correlation : float array array;  (** 6×6 correlation matrix [NI, EBIT, CapEx, Depr, CA, CL] *)
}
[@@deriving show]

type beta_prior = {
  alpha : float;
  beta : float;
  lower_bound : float;
  upper_bound : float;
}
[@@deriving show]

type sector_priors = {
  roe_prior : beta_prior;
  retention_prior : beta_prior;
  roic_prior : beta_prior;
}
[@@deriving show]

type distribution_params = {
  mean : float;
  std : float;
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

type simulation_sample = {
  fcfe : float array;
  fcff : float array;
  growth_rate_fcfe : float;
  growth_rate_fcff : float;
  pve : float;
  pvf : float;
  ivps_fcfe : float;
  ivps_fcff : float;
}
[@@deriving show]

type valuation_statistics = {
  mean : float;
  std : float;
  min : float;
  max : float;
  percentile_5 : float;
  percentile_25 : float;
  percentile_50 : float;
  percentile_75 : float;
  percentile_95 : float;
}
[@@deriving show]

type probability_metrics = {
  prob_undervalued : float;
  prob_overvalued : float;
  expected_surplus : float;
  expected_surplus_pct : float;
}
[@@deriving show]

(** Tail risk metrics for hedge-fund-quality reporting *)
type tail_risk_metrics = {
  var_1 : float;        (** 1% Value-at-Risk (99th percentile loss) *)
  var_5 : float;        (** 5% Value-at-Risk (95th percentile loss) *)
  cvar_1 : float;       (** 1% Conditional VaR (expected loss in worst 1%) *)
  cvar_5 : float;       (** 5% Conditional VaR (expected loss in worst 5%) *)
  max_drawdown : float; (** Maximum drawdown from median *)
  downside_deviation : float;  (** Std dev of returns below median *)
}
[@@deriving show]

(** Stress test scenario result *)
type stress_scenario = {
  name : string;
  description : string;
  ivps_fcfe : float;
  ivps_fcff : float;
  discount_rate_ce : float;
  discount_rate_wacc : float;
}
[@@deriving show]

type valuation_class =
  | Undervalued
  | FairlyValued
  | Overvalued
[@@deriving show]

type investment_signal =
  | StrongBuy
  | Buy
  | Hold
  | Avoid
[@@deriving show]

type valuation_result = {
  ticker : ticker;
  price : float;
  num_simulations : int;
  fcfe_stats : valuation_statistics;
  fcfe_metrics : probability_metrics;
  fcfe_class : valuation_class;
  fcfe_tail_risk : tail_risk_metrics;
  fcff_stats : valuation_statistics;
  fcff_metrics : probability_metrics;
  fcff_class : valuation_class;
  fcff_tail_risk : tail_risk_metrics;
  signal : investment_signal;
  cost_of_capital : cost_of_capital;
  simulations_fcfe : float array;
  simulations_fcff : float array;
  stress_scenarios : stress_scenario list;
}
[@@deriving show]

type config = {
  risk_free_rates : (country * (int * float) list) list;
  equity_risk_premiums : (country * float) list;
  industry_betas : (industry * float) list;
  tax_rates : (country * float) list;
  simulation_config : simulation_config;
  industry_priors : (sector * sector_priors) list;
}
[@@deriving show]

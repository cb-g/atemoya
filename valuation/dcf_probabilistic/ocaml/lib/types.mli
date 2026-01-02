(** Core types for probabilistic DCF valuation model *)

(** Basic identifiers *)
type ticker = string [@@deriving show]
type currency = string [@@deriving show]
type country = string [@@deriving show]
type sector = string [@@deriving show]
type industry = string [@@deriving show]

(** Time series data (4-year historical) *)
type time_series = {
  ebit : float array;  (** Operating income time series *)
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

(** Market data for a security *)
type market_data = {
  ticker : ticker;
  price : float;
  mve : float;  (** Market value of equity *)
  mvb : float;  (** Market value of debt *)
  shares_outstanding : float;
  currency : currency;
  country : country;
  sector : sector;
  industry : industry;
}
[@@deriving show]

(** Regime-specific parameters for discount rate sampling *)
type regime_parameters = {
  rfr_volatility : float;
  erp_volatility : float;
  beta_volatility : float;
  correlation : float array array;
}
[@@deriving show]

(** Configuration for regime-switching model *)
type regime_config = {
  crisis_probability : float;  (** Probability of being in crisis regime (e.g., 0.10 = 10%) *)
  normal_regime : regime_parameters;
  crisis_regime : regime_parameters;
}
[@@deriving show]

(** Configuration for Monte Carlo simulation *)
type simulation_config = {
  num_simulations : int;  (** Number of Monte Carlo iterations *)
  projection_years : int;  (** Forecast horizon *)
  terminal_growth_rate : float;
  growth_clamp_upper : float;
  growth_clamp_lower : float;
  rfr_duration : int;
  use_bayesian_priors : bool;  (** Enable Bayesian smoothing *)
  prior_weight : float;  (** Weight for prior (0.0-1.0, typically 0.5) *)
  use_stochastic_discount_rates : bool;  (** Enable stochastic RFR, beta, ERP *)
  rfr_volatility : float;  (** Std dev for RFR sampling - used if NOT regime-switching *)
  beta_volatility : float;  (** Std dev for beta sampling - used if NOT regime-switching *)
  erp_volatility : float;  (** Std dev for ERP sampling - used if NOT regime-switching *)
  use_time_varying_growth : bool;  (** Enable time-varying growth rates *)
  growth_mean_reversion_speed : float;  (** Mean reversion speed parameter *)
  use_growth_rate_sampling : bool;  (** Use growth-rate sampling (RECOMMENDED) vs legacy level-based sampling *)
  use_correlated_discount_rates : bool;  (** Use multivariate normal for correlated RFR/ERP/Beta (RECOMMENDED) *)
  discount_rate_correlation : float array array;  (** 3×3 correlation matrix [RFR, ERP, Beta] - used if NOT regime-switching *)
  use_regime_switching : bool;  (** Use regime-switching model (RECOMMENDED for fat tails) *)
  regime_config : regime_config option;  (** Regime parameters (required if use_regime_switching=true) *)
  use_copula_financials : bool;  (** Use Gaussian copula for correlated financial metrics (RECOMMENDED) *)
  financials_correlation : float array array;  (** 6×6 correlation matrix [NI, EBIT, CapEx, Depr, CA, CL] *)
}
[@@deriving show]

(** Bayesian prior parameters for Beta distribution *)
type beta_prior = {
  alpha : float;
  beta : float;
  lower_bound : float;
  upper_bound : float;
}
[@@deriving show]

(** Sector-specific priors (bundles ROE, retention, ROIC priors) *)
type sector_priors = {
  roe_prior : beta_prior;
  retention_prior : beta_prior;
  roic_prior : beta_prior;
}
[@@deriving show]

(** Distribution parameters *)
type distribution_params = {
  mean : float;
  std : float;
}
[@@deriving show]

(** Cost of capital components *)
type cost_of_capital = {
  ce : float;  (** Cost of equity (CAPM) *)
  cb : float;  (** Cost of borrowing *)
  wacc : float;
  leveraged_beta : float;
  risk_free_rate : float;
  equity_risk_premium : float;
}
[@@deriving show]

(** Simulation results for one iteration *)
type simulation_sample = {
  fcfe : float array;  (** Projected FCFE for h years *)
  fcff : float array;  (** Projected FCFF for h years *)
  growth_rate_fcfe : float;
  growth_rate_fcff : float;
  pve : float;  (** Present value of equity *)
  pvf : float;  (** Present value of firm *)
  ivps_fcfe : float;  (** Intrinsic value per share (FCFE) *)
  ivps_fcff : float;  (** Intrinsic value per share (FCFF) *)
}
[@@deriving show]

(** Statistical summary of simulation results *)
type valuation_statistics = {
  mean : float;
  std : float;
  min : float;
  max : float;
  percentile_5 : float;
  percentile_25 : float;
  percentile_50 : float;  (** Median *)
  percentile_75 : float;
  percentile_95 : float;
}
[@@deriving show]

(** Probability metrics *)
type probability_metrics = {
  prob_undervalued : float;  (** P(intrinsic > price) *)
  prob_overvalued : float;  (** P(intrinsic < price) *)
  expected_surplus : float;  (** E[intrinsic - price] *)
  expected_surplus_pct : float;  (** E[(intrinsic - price) / price] *)
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

(** Classification of valuation relationship *)
type valuation_class =
  | Undervalued
  | FairlyValued
  | Overvalued
[@@deriving show]

(** Investment signal based on probabilistic analysis *)
type investment_signal =
  | StrongBuy  (** Both FCFE and FCFF undervalued with high confidence *)
  | Buy  (** One method undervalued, other fairly valued *)
  | Hold  (** Mixed or fairly valued signals *)
  | Avoid  (** Both methods overvalued *)
[@@deriving show]

(** Complete probabilistic valuation result *)
type valuation_result = {
  ticker : ticker;
  price : float;
  num_simulations : int;

  (** FCFE method statistics *)
  fcfe_stats : valuation_statistics;
  fcfe_metrics : probability_metrics;
  fcfe_class : valuation_class;
  fcfe_tail_risk : tail_risk_metrics;

  (** FCFF method statistics *)
  fcff_stats : valuation_statistics;
  fcff_metrics : probability_metrics;
  fcff_class : valuation_class;
  fcff_tail_risk : tail_risk_metrics;

  (** Overall assessment *)
  signal : investment_signal;
  cost_of_capital : cost_of_capital;

  (** Raw simulation data (for visualization and further analysis) *)
  simulations_fcfe : float array;  (** All IVPS_FCFE samples *)
  simulations_fcff : float array;  (** All IVPS_FCFF samples *)

  (** Stress test scenarios *)
  stress_scenarios : stress_scenario list;
}
[@@deriving show]

(** Configuration data (loaded from JSON files) *)
type config = {
  risk_free_rates : (country * (int * float) list) list;
  equity_risk_premiums : (country * float) list;
  industry_betas : (industry * float) list;
  tax_rates : (country * float) list;
  simulation_config : simulation_config;

  (** Industry-specific Bayesian priors (sector -> priors mapping) *)
  industry_priors : (sector * sector_priors) list;
}
[@@deriving show]

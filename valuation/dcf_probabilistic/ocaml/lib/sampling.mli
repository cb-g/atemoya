(** Sampling module for probabilistic DCF *)

(** Random number generation *)

(** Sample from standard normal distribution (mean=0, std=1) using Box-Muller *)
val standard_normal_sample : unit -> float

(** Sample from Gaussian distribution *)
val gaussian_sample : mean:float -> std:float -> float

(** Sample from lognormal distribution
    If X ~ Normal(μ_log, σ_log²), then exp(X) ~ Lognormal *)
val lognormal_sample : mean:float -> std:float -> float

(** Sample from Beta distribution using gamma functions *)
val beta_sample : alpha:float -> beta_param:float -> float

(** Bayesian smoothing *)

(** Scale Beta sample to [lower, upper] range *)
val scale_beta_sample : sample:float -> lower:float -> upper:float -> float

(** Mix empirical value with prior-based value
    result = (1 - weight) * empirical + weight * prior *)
val bayesian_smooth : empirical:float -> prior:float -> weight:float -> float

(** Growth rate sampling *)

(** Sample FCFE growth rate from time series with Bayesian priors
    Uses ROE and retention ratio with Beta priors *)
val sample_growth_rate_fcfe :
  time_series:Types.time_series ->
  roe_prior:Types.beta_prior ->
  retention_prior:Types.beta_prior ->
  config:Types.simulation_config ->
  float

(** Sample FCFF growth rate from time series with Bayesian priors
    Uses ROIC and reinvestment rate with Beta priors *)
val sample_growth_rate_fcff :
  time_series:Types.time_series ->
  roic_prior:Types.beta_prior ->
  config:Types.simulation_config ->
  float

(** Financial metric sampling *)

(** LEGACY: Level-based lognormal sampling - INFERIOR to growth-rate approach
    Kept for backward compatibility. Use sample_from_growth_rates instead. *)
val sample_from_time_series_LEGACY : float array -> float

(** Compute period-over-period growth rates from time series *)
val compute_growth_rates : float array -> float array

(** Sample growth rate with economic bounds (RECOMMENDED)
    Samples from historical growth rate distribution, clamped to [-30%, +50%] *)
val sample_growth_rate : float array -> float

(** Sample financial metric using growth rate approach (RECOMMENDED)
    Takes most recent value and applies sampled growth rate *)
val sample_from_growth_rates : float array -> float

(** Main sampling function that uses growth-rate approach
    Computes empirical mean/std and samples *)
val sample_from_time_series : float array -> float

(** Sample financial metric with safeguards (capping, squashing)
    Prevents extreme outliers from dominating *)
val sample_financial_metric :
  time_series:float array ->
  cap:float option ->
  float

(** Utility functions *)

(** Compute mean of array *)
val mean : float array -> float

(** Compute standard deviation of array *)
val std : float array -> float

(** Remove NaN and zero values from array *)
val clean_array : float array -> float array

(** Clamp value to [lower, upper] *)
val clamp : value:float -> lower:float -> upper:float -> float

(** Squash function to prevent extreme outliers
    For x < threshold: returns x
    For x >= threshold: returns threshold + log(1 + (x - threshold)) *)
val squash : value:float -> threshold:float -> float

(** Stochastic discount rate sampling *)

(** LEGACY: Independent sampling - INFERIOR to correlated approach
    Kept for backward compatibility. Use sample_discount_rates_correlated instead. *)
val sample_risk_free_rate :
  base_rfr:float ->
  volatility:float ->
  float

(** LEGACY: Independent sampling - INFERIOR to correlated approach
    Kept for backward compatibility. Use sample_discount_rates_correlated instead. *)
val sample_beta :
  base_beta:float ->
  volatility:float ->
  float

(** LEGACY: Independent sampling - INFERIOR to correlated approach
    Kept for backward compatibility. Use sample_discount_rates_correlated instead. *)
val sample_equity_risk_premium :
  base_erp:float ->
  volatility:float ->
  float

(** Cholesky decomposition of covariance matrix
    Automatically fixes non-positive-definite matrices using eigenvalue regularization
    Returns lower triangular matrix L such that Σ = L × L^T *)
val cholesky_decomposition : float array array -> float array array

(** Sample from multivariate normal distribution N(μ, Σ)
    Automatically handles non-positive-definite covariance matrices via adaptive regularization *)
val multivariate_gaussian_sample :
  mean:float array ->
  cov:float array array ->
  float array

(** Convert correlation matrix to covariance matrix
    Σ[i,j] = ρ[i,j] × σ[i] × σ[j] *)
val correlation_to_covariance :
  corr:float array array ->
  std_devs:float array ->
  float array array

(** Sample discount rate components with correlation (RECOMMENDED)
    Returns (rfr, erp, beta) sampled from multivariate normal with correlation *)
val sample_discount_rates_correlated :
  base_rfr:float ->
  base_erp:float ->
  base_beta:float ->
  rfr_vol:float ->
  erp_vol:float ->
  beta_vol:float ->
  correlation:float array array ->
  float * float * float

(** Sample discount rates with regime-switching (RECOMMENDED for fat tails)
    Returns (rfr, erp, beta, is_crisis) with regime-dependent parameters *)
val sample_discount_rates_regime_switching :
  base_rfr:float ->
  base_erp:float ->
  base_beta:float ->
  regime_config:Types.regime_config ->
  float * float * float * bool

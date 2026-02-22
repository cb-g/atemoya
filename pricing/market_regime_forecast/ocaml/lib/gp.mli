(** Gaussian Process Regime Detection

    Uses GP regression to model return dynamics with uncertainty quantification.
    The posterior mean indicates trend, posterior variance indicates regime stability.
*)

(** GP kernel types *)
type kernel_type =
  | RBF           (** Squared Exponential / Radial Basis Function *)
  | Matern32      (** Matern 3/2 - less smooth *)
  | Matern52      (** Matern 5/2 - moderately smooth *)
  | RationalQuadratic of float  (** RQ with alpha parameter *)

(** GP hyperparameters *)
type gp_params = {
  kernel: kernel_type;
  length_scale: float;
  signal_var: float;
  noise_var: float;
}

(** GP configuration *)
type gp_config = {
  kernel_type: kernel_type;
  optimize_hyperparams: bool;
  max_opt_iter: int;
  lookback_days: int;
  forecast_horizon: int;
}

val default_gp_config : gp_config

(** GP posterior *)
type gp_posterior = {
  mean: float array;
  var: float array;
  log_marginal_likelihood: float;
}

(** GP regression result *)
type gp_result = {
  params: gp_params;
  posterior: gp_posterior;
  trend_forecast: float array;
  uncertainty: float array;
  current_trend: float;
  current_uncertainty: float;
  anomaly_score: float;
}

(** Full GP classification result *)
type gp_classification = {
  result: gp_result;
  trend: Types.trend_regime;
  volatility: Types.vol_regime;
  regime_confidence: float;
  forecast_mean: float;
  forecast_std: float;
}

(** Fit GP to returns *)
val fit : returns:float array -> config:gp_config -> gp_result

(** Run full GP analysis *)
val analyze : returns:float array -> config:gp_config -> gp_classification

(** Classify trend based on GP posterior *)
val classify_trend : result:gp_result -> Types.trend_regime

(** Classify volatility based on GP uncertainty *)
val classify_volatility : result:gp_result -> historical_returns:float array -> Types.vol_regime

(** String representation of kernel type *)
val string_of_kernel : kernel_type -> string

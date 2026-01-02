(** Core types for the regime-aware benchmark-relative downside optimization model *)

type ticker = string

type weights = {
  assets : (ticker * float) list;
  cash : float;
}

type return_series = {
  ticker : ticker;
  dates : string array;
  returns : float array;
}

type benchmark = {
  dates : string array;
  returns : float array;
}

type active_returns = float array

type risk_metrics = {
  lpm1 : float;
  cvar_95 : float;
  portfolio_beta : float;
}

type regime = {
  volatility : float;
  stress_weight : float;
  is_stress : bool;
}

type asset_betas = (ticker * float) list

type opt_params = {
  lambda_lpm1 : float;
  lambda_cvar : float;
  transaction_cost_bps : float;
  turnover_penalty : float;
  beta_penalty : float;
  target_beta : float;
  lpm1_threshold : float;
  rebalance_threshold : float;
}

type rebalance_decision = {
  should_rebalance : bool;
  reason : string;
  objective_improvement : float;
  current_objective : float;
  proposed_objective : float;
}

type optimization_result = {
  weights : weights;
  objective_value : float;
  risk_metrics : risk_metrics;
  turnover : float;
  transaction_costs : float;
}

type dual_optimization_result = {
  frictionless : optimization_result;
  constrained : optimization_result;
  gap_distance : float;
  gap_lpm1 : float;
  gap_cvar : float;
  gap_beta : float;
}

type log_entry = {
  date : string;
  regime : regime;
  asset_betas : asset_betas;
  current_weights : weights;
  proposed_weights : weights;
  risk_current : risk_metrics;
  risk_proposed : risk_metrics;
  decision : rebalance_decision;
  turnover : float;
  costs : float;
}

val pp_weights : Format.formatter -> weights -> unit
val pp_return_series : Format.formatter -> return_series -> unit
val pp_benchmark : Format.formatter -> benchmark -> unit
val pp_risk_metrics : Format.formatter -> risk_metrics -> unit
val pp_regime : Format.formatter -> regime -> unit
val pp_opt_params : Format.formatter -> opt_params -> unit
val pp_rebalance_decision : Format.formatter -> rebalance_decision -> unit
val pp_optimization_result : Format.formatter -> optimization_result -> unit
val pp_log_entry : Format.formatter -> log_entry -> unit

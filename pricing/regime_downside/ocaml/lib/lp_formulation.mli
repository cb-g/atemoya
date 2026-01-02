(** LP formulation per specification *)

open Types

(** LP problem data structure *)
type lp_problem = {
  n_assets : int;
  n_scenarios : int;
  asset_scenarios : float array array;
  benchmark_scenarios : float array;
  cash_scenarios : float array;
  prev_weights : float array;
  prev_cash : float;
  asset_betas : float array;
  stress_weight : float;
  lambda_lpm1 : float;
  lambda_cvar : float;
  lambda_beta : float;
  kappa : float;
  lpm_threshold : float;
  cvar_alpha : float;
  beta_target : float;
}

(** LP solution *)
type lp_solution = {
  asset_weights : float array;
  cash_weight : float;
  objective_value : float;
  lpm1_value : float;
  cvar_value : float;
  turnover : float;
  beta_penalty : float;
}

(** Build LP problem from current state *)
val build_problem :
  asset_returns_list:return_series list ->
  benchmark_returns:float array ->
  current_weights:weights ->
  asset_betas:asset_betas ->
  params:opt_params ->
  stress_weight:float ->
  lp_problem

(** Solve LP problem *)
val solve_lp : lp_problem -> lp_solution

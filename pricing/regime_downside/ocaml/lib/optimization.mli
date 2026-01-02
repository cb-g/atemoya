(** Portfolio optimization using convex optimization *)

open Types

(** Calculate turnover between two portfolios *)
val calculate_turnover : current_weights:weights -> new_weights:weights -> float

(** Calculate transaction costs *)
val calculate_transaction_costs :
  current_weights:weights ->
  new_weights:weights ->
  cost_bps:float ->
  float

(** Calculate portfolio returns from weights and asset returns *)
val calculate_portfolio_returns :
  weights:weights ->
  asset_returns_list:return_series list ->
  float array

(** Optimize portfolio weights using spec-compliant LP solver *)
val optimize :
  params:opt_params ->
  current_weights:weights ->
  asset_returns_list:return_series list ->
  benchmark_returns:float array ->
  asset_betas:asset_betas ->
  regime:regime ->
  ?n_random_starts:int ->
  ?n_gradient_refine:int ->
  unit ->
  optimization_result

(** Optimize portfolio twice: frictionless and constrained *)
val optimize_dual :
  params:opt_params ->
  current_weights:weights ->
  asset_returns_list:return_series list ->
  benchmark_returns:float array ->
  asset_betas:asset_betas ->
  regime:regime ->
  ?n_random_starts:int ->
  ?n_gradient_refine:int ->
  unit ->
  dual_optimization_result

(** Decide whether to rebalance *)
val should_rebalance :
  current_result:optimization_result ->
  proposed_result:optimization_result ->
  threshold:float ->
  rebalance_decision

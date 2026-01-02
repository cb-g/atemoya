(** Core types for the regime-aware benchmark-relative downside optimization model *)

(** Asset identifier *)
type ticker = string
[@@deriving show, eq]

(** Portfolio weights *)
type weights = {
  assets : (ticker * float) list;  (** Asset weights: ticker -> weight *)
  cash : float;                     (** Cash weight *)
}
[@@deriving show]

(** Time-series return data *)
type return_series = {
  ticker : ticker;
  dates : string array;             (** Date strings *)
  returns : float array;            (** Return values *)
}
[@@deriving show]

(** Benchmark data (S&P 500) *)
type benchmark = {
  dates : string array;
  returns : float array;
}
[@@deriving show]

(** Active returns (portfolio return - benchmark return) *)
type active_returns = float array

(** Risk measures *)
type risk_metrics = {
  lpm1 : float;                     (** Lower Partial Moment of order 1 *)
  cvar_95 : float;                  (** Conditional Value at Risk at 95% *)
  portfolio_beta : float;           (** Portfolio beta to benchmark *)
}
[@@deriving show]

(** Regime state *)
type regime = {
  volatility : float;               (** Current annualized volatility *)
  stress_weight : float;            (** Stress regime weight [0,1] *)
  is_stress : bool;                 (** Convenience flag *)
}
[@@deriving show]

(** Asset beta estimates *)
type asset_betas = (ticker * float) list
[@@deriving show]

(** Optimization parameters *)
type opt_params = {
  lambda_lpm1 : float;              (** LPM1 weight *)
  lambda_cvar : float;              (** CVaR weight *)
  transaction_cost_bps : float;     (** Transaction cost in bps *)
  turnover_penalty : float;         (** Turnover aversion gamma *)
  beta_penalty : float;             (** Beta penalty lambda_beta *)
  target_beta : float;              (** Target beta in stress (default 0.65) *)
  lpm1_threshold : float;           (** LPM1 threshold tau (negative) *)
  rebalance_threshold : float;      (** Objective improvement threshold delta *)
}
[@@deriving show]

(** Rebalancing decision *)
type rebalance_decision = {
  should_rebalance : bool;
  reason : string;
  objective_improvement : float;
  current_objective : float;
  proposed_objective : float;
}
[@@deriving show]

(** Optimization result *)
type optimization_result = {
  weights : weights;
  objective_value : float;
  risk_metrics : risk_metrics;
  turnover : float;
  transaction_costs : float;
}
[@@deriving show]

(** Dual optimization result (frictionless and constrained) *)
type dual_optimization_result = {
  frictionless : optimization_result;
  constrained : optimization_result;
  gap_distance : float;
  gap_lpm1 : float;
  gap_cvar : float;
  gap_beta : float;
}
[@@deriving show]

(** Log entry for a single evaluation *)
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
[@@deriving show]

(** Types for systematic risk early-warning signals module.

    Based on: "An early-warning risk signals framework to capture
    systematic risk in financial markets" (Ciciretti et al. 2025)

    Four risk signals from covariance matrices and graph theory:
    1. Variance explained by largest eigenvalue
    2. Variance explained by eigenvalues 2-5
    3. Mean eigenvector centrality from MST
    4. Std dev of eigenvector centrality from MST
*)

(** Asset return data *)
type asset_returns = {
  ticker : string;
  returns : float array;
  dates : string array;
}

(** Covariance matrix with metadata *)
type covariance_matrix = {
  matrix : float array array;
  tickers : string array;
  n_assets : int;
}

(** Eigenvalue decomposition results *)
type eigen_decomposition = {
  eigenvalues : float array;  (** Sorted descending *)
  eigenvectors : float array array;
}

(** Graph edge for MST construction *)
type edge = {
  from_idx : int;
  to_idx : int;
  weight : float;  (** Distance = sqrt(1 - rho^2) *)
}

(** Minimum Spanning Tree representation *)
type mst = {
  edges : edge list;
  n_vertices : int;
  total_weight : float;
}

(** Eigenvector centrality results *)
type centrality_result = {
  centralities : float array;  (** One per asset *)
  mean_centrality : float;
  std_centrality : float;
}

(** The four early-warning risk signals *)
type risk_signals = {
  var_explained_first : float;      (** λ₁ / Σλⱼ *)
  var_explained_2_to_5 : float;     (** Σ(j=2→5) λⱼ / Σλⱼ *)
  mean_eigenvector_centrality : float;
  std_eigenvector_centrality : float;
  timestamp : string;
}

(** Risk regime classification *)
type risk_regime =
  | LowRisk
  | NormalRisk
  | ElevatedRisk
  | HighRisk
  | CrisisRisk

(** Time series of risk signals *)
type signal_series = {
  signals : risk_signals array;
  regime_history : risk_regime array;
  current_regime : risk_regime;
  transition_probability : float;  (** P(high risk | current signals) *)
}

(** Input configuration *)
type config = {
  tickers : string list;
  lookback_days : int;
  rolling_window : int;
  data_dir : string;
  output_dir : string;
}

(** Full analysis result *)
type analysis_result = {
  config : config;
  latest_signals : risk_signals;
  signal_history : risk_signals array;
  current_regime : risk_regime;
  transition_prob : float;
  mst : mst;
  centralities : centrality_result;
  timestamp : string;
}

(** Convert regime to human-readable string *)
val regime_to_string : risk_regime -> string

(** Get ANSI color code for regime *)
val regime_to_color : risk_regime -> string

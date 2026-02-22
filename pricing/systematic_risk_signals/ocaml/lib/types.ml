(** Types for systematic risk early-warning signals module. *)

type asset_returns = {
  ticker : string;
  returns : float array;
  dates : string array;
}

type covariance_matrix = {
  matrix : float array array;
  tickers : string array;
  n_assets : int;
}

type eigen_decomposition = {
  eigenvalues : float array;
  eigenvectors : float array array;
}

type edge = {
  from_idx : int;
  to_idx : int;
  weight : float;
}

type mst = {
  edges : edge list;
  n_vertices : int;
  total_weight : float;
}

type centrality_result = {
  centralities : float array;
  mean_centrality : float;
  std_centrality : float;
}

type risk_signals = {
  var_explained_first : float;
  var_explained_2_to_5 : float;
  mean_eigenvector_centrality : float;
  std_eigenvector_centrality : float;
  timestamp : string;
}

type risk_regime =
  | LowRisk
  | NormalRisk
  | ElevatedRisk
  | HighRisk
  | CrisisRisk

type signal_series = {
  signals : risk_signals array;
  regime_history : risk_regime array;
  current_regime : risk_regime;
  transition_probability : float;
}

type config = {
  tickers : string list;
  lookback_days : int;
  rolling_window : int;
  data_dir : string;
  output_dir : string;
}

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

(* Helper functions *)
let regime_to_string = function
  | LowRisk -> "Low Risk"
  | NormalRisk -> "Normal"
  | ElevatedRisk -> "Elevated"
  | HighRisk -> "High Risk"
  | CrisisRisk -> "Crisis"

let regime_to_color = function
  | LowRisk -> "\027[32m"      (* Green *)
  | NormalRisk -> "\027[0m"    (* Default *)
  | ElevatedRisk -> "\027[33m" (* Yellow *)
  | HighRisk -> "\027[31m"     (* Red *)
  | CrisisRisk -> "\027[35m"   (* Magenta *)

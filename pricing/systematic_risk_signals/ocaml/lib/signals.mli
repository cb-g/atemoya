(** Early-warning risk signals computation.

    Combines covariance analysis and graph theory to produce
    the four risk signals from the paper:
    1. Variance explained by largest eigenvalue
    2. Variance explained by eigenvalues 2-5
    3. Mean eigenvector centrality
    4. Std dev of eigenvector centrality
*)

open Types

(** Compute all four risk signals from return data *)
val compute_signals : asset_returns array -> string -> risk_signals

(** Classify current regime based on signals *)
val classify_regime : risk_signals -> risk_regime

(** Estimate probability of transitioning to high-risk regime *)
val transition_probability : risk_signals array -> float

(** Compute rolling signal series *)
val compute_signal_series :
  asset_returns array -> int -> string array -> signal_series

(** Full analysis from return data *)
val full_analysis : config -> asset_returns array -> analysis_result

(** Covariance matrix computation and eigenvalue decomposition.

    Implements realized covariance estimation and eigenvalue extraction
    for the first two risk signals:
    - Variance explained by largest eigenvalue
    - Variance explained by eigenvalues 2-5
*)

open Types

(** Compute realized covariance matrix from returns *)
val compute_covariance : asset_returns array -> covariance_matrix

(** Convert covariance matrix to correlation matrix *)
val to_correlation : covariance_matrix -> float array array

(** Eigenvalue decomposition using power iteration *)
val eigen_decompose : covariance_matrix -> eigen_decomposition

(** Extract variance explained by first eigenvalue: λ₁ / Σλⱼ *)
val var_explained_first : eigen_decomposition -> float

(** Extract variance explained by eigenvalues 2-5: Σ(j=2→5) λⱼ / Σλⱼ *)
val var_explained_2_to_5 : eigen_decomposition -> float

(** Convert correlations to Euclidean distances: d = sqrt(1 - ρ²) *)
val correlation_to_distance : float array array -> float array array

(* Interface for correlation analytics *)

open Types

(** Statistics **)

(* Calculate mean *)
val mean : float array -> float

(* Calculate standard deviation *)
val std : float array -> float

(* Calculate returns from prices *)
val returns : float array -> float array

(** Correlation **)

(* Calculate covariance between two return series *)
val covariance : float array -> float array -> float

(* Calculate correlation between two return series *)
val correlation : float array -> float array -> float

(* Calculate correlation matrix from returns *)
val correlation_matrix : float array array -> float array array

(* Calculate average pairwise correlation *)
val avg_pairwise_correlation : float array array -> float

(* Calculate realized correlation from price history *)
val realized_correlation :
  index_prices:float array ->
  constituent_prices:float array array ->
  weights:float array ->
  float

(* Calculate implied correlation from volatilities *)
val implied_correlation :
  index_vol:float ->
  constituent_vols:float array ->
  weights:float array ->
  float

(* Build full correlation metrics *)
val calculate_correlation_metrics :
  index_prices:float array ->
  index_vol:float ->
  constituent_prices:float array array ->
  constituent_vols:float array ->
  weights:float array ->
  correlation_metrics

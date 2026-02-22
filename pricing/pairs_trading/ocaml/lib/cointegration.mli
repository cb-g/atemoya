(* Interface for cointegration testing *)

open Types

(** Statistics **)

val mean : float array -> float
val std : float array -> float

(** Regression **)

val ols_regression :
  x:float array ->
  y:float array ->
  float * float * float array  (* (alpha, beta, residuals) *)

(** Stationarity tests **)

val adf_test :
  float array ->
  float * float  (* (test_statistic, critical_value) *)

(** Cointegration **)

val test_cointegration :
  prices1:float array ->
  prices2:float array ->
  cointegration_result

val calculate_spread :
  prices1:float array ->
  prices2:float array ->
  hedge_ratio:float ->
  alpha:float ->
  float array

val spread_from_cointegration :
  prices1:float array ->
  prices2:float array ->
  coint_result:cointegration_result ->
  float array

(** Total Least Squares regression **)

val tls_regression :
  x:float array ->
  y:float array ->
  float * float * float array  (* (alpha, beta, residuals) *)

val test_cointegration_tls :
  prices1:float array ->
  prices2:float array ->
  cointegration_result

(** Johansen cointegration test **)

val johansen_test :
  prices1:float array ->
  prices2:float array ->
  cointegration_result

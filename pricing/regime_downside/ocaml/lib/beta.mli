(** Beta estimation using exponentially weighted covariance *)

open Types

(** Calculate exponentially weighted mean *)
val ewm_mean : values:float array -> halflife:float -> float

(** Calculate exponentially weighted covariance *)
val ewm_cov : x:float array -> y:float array -> halflife:float -> float

(** Calculate exponentially weighted variance *)
val ewm_var : values:float array -> halflife:float -> float

(** Estimate beta for a single asset *)
val estimate_beta :
  asset_returns:float array ->
  benchmark_returns:float array ->
  halflife:float ->
  float

(** Estimate betas for all assets (default halflife: 60 days) *)
val estimate_all_betas :
  asset_returns_list:return_series list ->
  benchmark_returns:float array ->
  ?halflife:float ->
  unit ->
  asset_betas

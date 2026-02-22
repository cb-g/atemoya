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

(** Filter arrays to only include downside observations *)
val filter_downside :
  asset_returns:float array ->
  benchmark_returns:float array ->
  threshold:float ->
  float array * float array

(** Estimate downside beta (only considers negative benchmark returns)
    Downside beta captures asset sensitivity during market declines *)
val estimate_downside_beta :
  asset_returns:float array ->
  benchmark_returns:float array ->
  halflife:float ->
  threshold:float ->
  float

(** Estimate upside beta (only considers positive benchmark returns) *)
val estimate_upside_beta :
  asset_returns:float array ->
  benchmark_returns:float array ->
  halflife:float ->
  threshold:float ->
  float

(** Calculate beta asymmetry: (β_down - β_up) / β
    Positive value = asset hurts more in down markets than it helps in up markets *)
val calculate_beta_asymmetry :
  asset_returns:float array ->
  benchmark_returns:float array ->
  halflife:float ->
  threshold:float ->
  float

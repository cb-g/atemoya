(* Interface for dispersion signal generation *)

open Types

(** Dispersion metrics **)

(* Calculate weighted average implied volatility *)
val weighted_avg_iv :
  constituent_vols:float array ->
  weights:float array ->
  float

(* Calculate dispersion level *)
val dispersion_level :
  index_iv:float ->
  constituent_vols:float array ->
  weights:float array ->
  float

(* Calculate z-score of dispersion level *)
val dispersion_zscore :
  current_dispersion:float ->
  historical_dispersion:float array ->
  float

(* Calculate dispersion metrics *)
val calculate_dispersion_metrics :
  index_iv:float ->
  constituent_vols:float array ->
  weights:float array ->
  historical_dispersion:float array ->
  implied_corr:float ->
  dispersion_metrics

(** Position construction **)

val build_index_position :
  ticker:string ->
  spot:float ->
  option:option_contract ->
  notional:float ->
  index_position

val build_single_name :
  ticker:string ->
  weight:float ->
  spot:float ->
  option:option_contract ->
  notional:float ->
  single_name

val build_dispersion_position :
  position_type:dispersion_type ->
  index:index_position ->
  single_names:single_name array ->
  entry_date:float ->
  expiry_date:float ->
  dispersion_position

(** Position Greeks **)

val position_delta : dispersion_position -> float
val position_gamma : dispersion_position -> float
val position_vega : dispersion_position -> float
val position_theta : dispersion_position -> float

(** Position valuation **)

val position_pnl :
  position:dispersion_position ->
  new_index_price:float ->
  new_single_prices:float array ->
  new_index_iv:float ->
  new_single_ivs:float array ->
  float

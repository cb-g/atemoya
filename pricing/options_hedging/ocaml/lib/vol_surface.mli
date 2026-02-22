(* Volatility Surface Modeling - SVI and SABR *)

(* SVI Formula: Total variance as function of log-moneyness
   w(k) = a + b × (ρ(k - m) + √((k - m)² + σ²))
*)
val svi_total_variance :
  Types.svi_params ->
  log_moneyness:float ->
  float

(* Convert SVI total variance to implied volatility *)
val svi_implied_vol :
  Types.svi_params ->
  strike:float ->
  spot:float ->
  float

(* SABR implied volatility formula (Hagan et al. 2002) *)
val sabr_implied_vol :
  Types.sabr_params ->
  forward:float ->
  strike:float ->
  float

(* Interpolate volatility from surface at given strike/expiry *)
val interpolate_vol :
  Types.vol_surface ->
  strike:float ->
  expiry:float ->
  spot:float ->
  float

(* Check SVI parameters for no-arbitrage conditions *)
val check_svi_arbitrage : Types.svi_params -> bool

(* Validate SABR parameter constraints *)
val validate_sabr : Types.sabr_params -> bool

(* Generate full surface grid for visualization
   Returns: (strike, expiry, implied_vol) array
*)
val generate_surface_grid :
  Types.vol_surface ->
  spot:float ->
  strike_range:(float * float) ->
  expiry_range:(float * float) ->
  grid_points:(int * int) ->
  (float * float * float) array

(* Find closest expiry in vol surface params *)
val find_closest_expiry_idx :
  expiry:float ->
  params_array:'a array ->
  get_expiry:('a -> float) ->
  int

(* Interpolate between two SVI param sets *)
val interpolate_svi_params :
  Types.svi_params ->
  Types.svi_params ->
  weight:float ->
  Types.svi_params

(* Interpolate between two SABR param sets *)
val interpolate_sabr_params :
  Types.sabr_params ->
  Types.sabr_params ->
  weight:float ->
  Types.sabr_params

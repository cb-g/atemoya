(* Interface for skew measurement *)

open Types

(** Get implied volatility from SVI surface for given strike and expiry *)
val get_iv_from_surface :
  vol_surface ->
  strike:float ->
  expiry:float ->
  spot:float ->
  float

(** Find strike where option has specified delta
    Uses Newton-Raphson iteration
*)
val find_delta_strike :
  option_type ->
  target_delta:float ->
  spot:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  vol_surface ->
  float option

(** Compute 25-delta risk reversal: IV(25Δ Call) - IV(25Δ Put)
    Negative values indicate put skew (typical for equities)
*)
val compute_rr25 :
  vol_surface ->
  spot:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  float

(** Compute 25-delta butterfly: [IV(25Δ Call) + IV(25Δ Put)] / 2 - IV(ATM)
    Positive values indicate smile (fat tails)
*)
val compute_bf25 :
  vol_surface ->
  spot:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  float

(** Compute skew slope via linear regression across strikes
    Returns slope in %IV per 10% moneyness
*)
val compute_skew_slope :
  vol_surface ->
  spot:float ->
  expiry:float ->
  strike_range:(float * float) ->  (* (low_pct, high_pct) e.g., (0.9, 1.1) *)
  float

(** Compute ATM implied volatility *)
val compute_atm_vol :
  vol_surface ->
  spot:float ->
  expiry:float ->
  float

(** Compute all skew metrics at once *)
val compute_skew_observation :
  vol_surface ->
  underlying_data ->
  rate:float ->
  expiry:float ->
  skew_observation

(** Compute skew time series from historical vol surfaces *)
val compute_skew_time_series :
  vol_surface_data:(float * vol_surface) array ->  (* (timestamp, surface) *)
  underlying_data:underlying_data ->
  rate:float ->
  expiry:float ->
  skew_observation array

(** Historical statistics for a given metric
    Returns (mean, std, p25, p75)
*)
val skew_statistics :
  skew_observation array ->
  metric:string ->  (* "rr25", "bf25", "slope", "atm_vol" *)
  (float * float * float * float)

(** Detect regime changes using rolling statistics
    Returns array of booleans indicating regime shifts
*)
val detect_regime_change :
  skew_observation array ->
  window:int ->
  threshold:float ->
  bool array

(** Compute z-score for current observation vs historical *)
val compute_z_score :
  skew_observation array ->
  current_value:float ->
  metric:string ->
  float

(* Interface for realized volatility estimators *)

open Types

(** Close-to-close volatility estimator (classical method) *)
val close_to_close :
  ohlc_bar array ->
  window_days:int ->
  realized_vol array

(** Parkinson high-low range estimator
    More efficient than close-to-close, uses intraday range information *)
val parkinson :
  ohlc_bar array ->
  window_days:int ->
  realized_vol array

(** Garman-Klass OHLC-based estimator
    Most efficient unbiased estimator using full OHLC information *)
val garman_klass :
  ohlc_bar array ->
  window_days:int ->
  realized_vol array

(** Rogers-Satchell drift-independent estimator
    Robust to price trends *)
val rogers_satchell :
  ohlc_bar array ->
  window_days:int ->
  realized_vol array

(** Yang-Zhang estimator (best overall)
    Combines overnight, open-to-close, and Rogers-Satchell components *)
val yang_zhang :
  ohlc_bar array ->
  window_days:int ->
  realized_vol array

(** Compute intraday realized vol from high-frequency prices *)
val intraday_realized_vol :
  prices:float array ->
  timestamps:float array ->
  window_hours:int ->
  float

(** Compare all estimators on same data *)
val compare_estimators :
  ohlc_bar array ->
  window_days:int ->
  (rv_estimator * float) array

(** Get latest realized vol estimate *)
val get_latest_rv :
  realized_vol array ->
  realized_vol option

(** Convert annualized vol to daily vol *)
val annualized_to_daily : float -> float

(** Convert daily vol to annualized vol *)
val daily_to_annualized : float -> float

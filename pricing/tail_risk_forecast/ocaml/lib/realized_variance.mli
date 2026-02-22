(** Realized Variance computation from intraday returns *)

open Types

(** Compute realized variance for a single day from intraday returns.
    RV_t = sum(r_i^2) where r_i are intraday log returns *)
val compute_daily_rv : date:string -> close_price:float -> intraday_return array -> daily_rv

(** Compute RV series from grouped intraday data *)
val compute_rv_series : intraday_data -> daily_rv array

(** Annualize daily RV (multiply by 252) *)
val annualize_rv : float -> float

(** Convert RV to daily volatility (sqrt) *)
val rv_to_vol : float -> float

(** Compute log returns from price series *)
val log_returns : float array -> float array

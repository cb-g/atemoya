(** HAR-RV (Heterogeneous Autoregressive Realized Volatility) Model

    The HAR-RV model captures volatility persistence at multiple horizons:
    RV_{t+1} = c + β_d * RV_t + β_w * RV_t^(w) + β_m * RV_t^(m) + ε_t

    where:
    - RV_t^(w) = average of past 5 days RV (weekly)
    - RV_t^(m) = average of past 22 days RV (monthly)
*)

open Types

(** Compute weekly (5-day) rolling average of RV *)
val rv_weekly : daily_rv array -> int -> float

(** Compute monthly (22-day) rolling average of RV *)
val rv_monthly : daily_rv array -> int -> float

(** Estimate HAR-RV coefficients using OLS.
    Requires at least 50 observations for meaningful estimation. *)
val estimate_har : daily_rv array -> har_coefficients

(** Forecast next-day RV using HAR model *)
val forecast_rv : har_coefficients -> daily_rv array -> float

(** Minimum observations needed for HAR estimation (30 days) *)
val min_observations : int

(** Core types for tail risk forecasting *)

(** A single intraday return observation *)
type intraday_return = {
  timestamp : string;
  ret : float;  (** Log return *)
}

(** Daily realized variance computed from intraday returns *)
type daily_rv = {
  date : string;
  rv : float;           (** Realized variance (sum of squared returns) *)
  n_obs : int;          (** Number of intraday observations *)
  close_price : float;  (** End-of-day close price *)
}

(** HAR-RV model coefficients *)
type har_coefficients = {
  c : float;      (** Constant *)
  beta_d : float; (** Daily (lag-1) coefficient *)
  beta_w : float; (** Weekly (5-day avg) coefficient *)
  beta_m : float; (** Monthly (22-day avg) coefficient *)
  r_squared : float;
}

(** Jump detection result for a single day *)
type jump_indicator = {
  date : string;
  is_jump : bool;
  rv : float;
  threshold : float;  (** The threshold that was exceeded *)
  z_score : float;    (** How many std devs above mean *)
}

(** VaR/ES forecast for next day *)
type tail_risk_forecast = {
  date : string;           (** Forecast date (next trading day) *)
  rv_forecast : float;     (** Forecasted realized variance *)
  vol_forecast : float;    (** sqrt(rv_forecast) - daily volatility *)
  var_95 : float;          (** 95% VaR (5% worst case loss) *)
  var_99 : float;          (** 99% VaR (1% worst case loss) *)
  es_95 : float;           (** 95% Expected Shortfall *)
  es_99 : float;           (** 99% Expected Shortfall *)
  jump_adjusted : bool;    (** Whether forecast includes jump premium *)
}

(** Full analysis result for a ticker *)
type analysis_result = {
  ticker : string;
  analysis_date : string;
  rv_series : daily_rv array;
  har_model : har_coefficients;
  recent_jumps : jump_indicator array;
  forecast : tail_risk_forecast;
}

(** Input data from Python fetcher *)
type intraday_data = {
  ticker : string;
  start_date : string;
  end_date : string;
  interval : string;  (** e.g., "5m" *)
  bars : intraday_return array array;  (** Grouped by day *)
  daily_closes : (string * float) array;
}

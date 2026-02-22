(** Core types for tail risk forecasting *)

type intraday_return = {
  timestamp : string;
  ret : float;
}

type daily_rv = {
  date : string;
  rv : float;
  n_obs : int;
  close_price : float;
}

type har_coefficients = {
  c : float;
  beta_d : float;
  beta_w : float;
  beta_m : float;
  r_squared : float;
}

type jump_indicator = {
  date : string;
  is_jump : bool;
  rv : float;
  threshold : float;
  z_score : float;
}

type tail_risk_forecast = {
  date : string;
  rv_forecast : float;
  vol_forecast : float;
  var_95 : float;
  var_99 : float;
  es_95 : float;
  es_99 : float;
  jump_adjusted : bool;
}

type analysis_result = {
  ticker : string;
  analysis_date : string;
  rv_series : daily_rv array;
  har_model : har_coefficients;
  recent_jumps : jump_indicator array;
  forecast : tail_risk_forecast;
}

type intraday_data = {
  ticker : string;
  start_date : string;
  end_date : string;
  interval : string;
  bars : intraday_return array array;
  daily_closes : (string * float) array;
}

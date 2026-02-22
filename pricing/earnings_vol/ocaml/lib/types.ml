(** Earnings Volatility Strategy Types *)

(** Earnings event *)
type earnings_event = {
  ticker: string;
  earnings_date: string;
  days_to_earnings: int;
  spot_price: float;
  avg_volume_30d: float;
}

(** IV observation at a specific expiration *)
type iv_observation = {
  expiration_date: string;
  days_to_expiry: int;
  atm_iv: float;
  strike: float;
}

(** Term structure of implied volatility *)
type iv_term_structure = {
  ticker: string;
  observations: iv_observation array;
  front_month_iv: float;
  back_month_iv: float;
  term_structure_slope: float;
  term_structure_ratio: float;
}

(** Realized volatility metrics *)
type realized_vol = {
  ticker: string;
  lookback_days: int;
  rv: float;
  variance: float;
}

(** IV/RV comparison *)
type iv_rv_ratio = {
  ticker: string;
  implied_vol_30d: float;
  realized_vol_30d: float;
  iv_rv_ratio: float;
  iv_minus_rv: float;
}

(** Filter criteria *)
type filter_criteria = {
  min_term_slope: float;
  min_volume: float;
  min_iv_rv_ratio: float;
}

(** Filter result *)
type filter_result = {
  ticker: string;
  passes_term_slope: bool;
  passes_volume: bool;
  passes_iv_rv: bool;
  recommendation: string;
  term_slope: float;
  volume: float;
  iv_rv_ratio: float;
}

(** Position type *)
type position_type = 
  | ShortStraddle
  | LongCalendar

(** Kelly sizing result *)
type kelly_position = {
  position_type: position_type;
  kelly_fraction: float;
  fractional_kelly: float;
  max_position_size: float;
  num_contracts: int;
  expected_return: float;
  expected_std: float;
  max_loss_pct: float;
}

(** Trade recommendation *)
type trade_recommendation = {
  ticker: string;
  earnings_date: string;
  days_to_earnings: int;
  recommendation: string;
  filter_result: filter_result;
  suggested_structure: position_type;
  kelly_sizing: kelly_position;
  term_structure: iv_term_structure;
  iv_rv: iv_rv_ratio;
}

(** Default filter criteria from video *)
let default_criteria = {
  min_term_slope = -0.05;
  min_volume = 1_000_000.0;
  min_iv_rv_ratio = 1.1;
}

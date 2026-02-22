(** Skew-Based Vertical Spreads Types *)

(** Single option data point *)
type option_data = {
  strike: float;
  option_type: string; (* "call" or "put" *)
  implied_vol: float;
  delta: float;
  bid: float;
  ask: float;
  mid_price: float;
}

(** Full options chain *)
type options_chain = {
  ticker: string;
  spot_price: float;
  expiration: string;
  days_to_expiry: int;
  calls: option_data array;
  puts: option_data array;
  atm_strike: float;
}

(** Skew metrics *)
type skew_metrics = {
  ticker: string;
  date: string;

  (* Call skew: (ATM_IV - 25Δ_Call_IV) / ATM_IV *)
  call_skew: float;
  call_skew_zscore: float;

  (* Put skew: (ATM_IV - 25Δ_Put_IV) / ATM_IV *)
  put_skew: float;
  put_skew_zscore: float;

  (* ATM metrics *)
  atm_iv: float;
  atm_call_25delta_iv: float;
  atm_put_25delta_iv: float;

  (* Realized vol *)
  realized_vol_30d: float;

  (* Variance risk premium *)
  vrp: float; (* ATM_IV - RV *)
}

(** Momentum metrics *)
type momentum = {
  ticker: string;

  (* Time series momentum *)
  return_1w: float;
  return_1m: float;
  return_3m: float;

  (* Cross-sectional (rank within universe) *)
  rank_1m: int;
  rank_3m: int;
  percentile: float; (* 0-100 *)

  (* Relative to market *)
  beta: float;
  alpha_1m: float; (* Excess return vs market *)

  (* Proximity to 52-week high *)
  pct_from_52w_high: float;

  (* Overall signal *)
  momentum_score: float; (* -1 to +1 *)
}

(** Vertical spread structure *)
type vertical_spread = {
  ticker: string;
  expiration: string;
  days_to_expiry: int;

  (* Direction *)
  spread_type: string; (* "bull_call" or "bear_put" *)

  (* Long leg (buy) *)
  long_strike: float;
  long_delta: float;
  long_iv: float;
  long_price: float;

  (* Short leg (sell) *)
  short_strike: float;
  short_delta: float;
  short_iv: float;
  short_price: float;

  (* Spread economics *)
  debit: float;
  max_profit: float;
  max_loss: float;
  reward_risk_ratio: float;
  breakeven: float;

  (* Probability estimates *)
  prob_profit: float;
  expected_value: float;
  expected_return_pct: float;
}

(** Trade recommendation *)
type trade_recommendation = {
  ticker: string;
  timestamp: string;

  (* Spread details *)
  spread: vertical_spread;

  (* Why this trade? *)
  skew: skew_metrics;
  momentum: momentum;

  (* Filters *)
  passes_skew_filter: bool; (* z-score < -2 *)
  passes_ivrv_filter: bool; (* RV < OTM_IV and RV >= ATM_IV *)
  passes_momentum_filter: bool; (* Positive for calls, negative for puts *)

  (* Recommendation *)
  recommendation: string; (* "Strong Buy", "Buy", "Pass" *)
  edge_score: float; (* 0-100 *)

  (* Risk warning *)
  expected_win_rate: float;
  notes: string;
}

(** Default filter thresholds *)
let default_thresholds = {|
  {
    "skew_zscore_threshold": -2.0,
    "min_reward_risk": 3.0,
    "min_momentum_score": 0.3,
    "min_expected_value": 0.05,
    "max_days_to_expiry": 30
  }
|}

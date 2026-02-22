(** Pre-Earnings Straddle Types *)

(** Historical earnings event *)
type earnings_event = {
  ticker: string;
  date: string;
  implied_move: float;      (* Implied move % from ATM straddle before earnings *)
  realized_move: float;     (* Actual % move on earnings day *)
}

(** Current straddle opportunity *)
type straddle_opportunity = {
  ticker: string;
  earnings_date: string;
  days_to_earnings: int;

  (* Current straddle data *)
  spot_price: float;
  atm_strike: float;
  atm_call_price: float;
  atm_put_price: float;
  straddle_cost: float;
  current_implied_move: float;

  (* Expiration *)
  expiration: string;
  days_to_expiry: int;
}

(** Four predictive signals *)
type signals = {
  ticker: string;

  (* Signal 1: Current implied / Last implied *)
  implied_vs_last_implied_ratio: float;

  (* Signal 2: Current implied - Last realized *)
  implied_vs_last_realized_gap: float;

  (* Signal 3: Current implied / Average implied *)
  implied_vs_avg_implied_ratio: float;

  (* Signal 4: Current implied - Average realized *)
  implied_vs_avg_realized_gap: float;

  (* For reference *)
  current_implied: float;
  last_implied: float;
  last_realized: float;
  avg_implied: float;
  avg_realized: float;
  num_historical_events: int;
}

(** Linear regression model *)
type model_coefficients = {
  intercept: float;
  coef_implied_vs_last_implied: float;
  coef_implied_vs_last_realized: float;
  coef_implied_vs_avg_implied: float;
  coef_implied_vs_avg_realized: float;
}

(** Trade recommendation *)
type recommendation = {
  ticker: string;
  earnings_date: string;

  (* Opportunity details *)
  opportunity: straddle_opportunity;

  (* Signals *)
  signals: signals;

  (* Model prediction *)
  predicted_return: float;

  (* Recommendation *)
  recommendation: string; (* "Buy", "Pass" *)
  rank_score: float;

  (* Risk info *)
  kelly_fraction: float;
  suggested_size: float; (* As % of portfolio *)
  max_loss: float;

  notes: string;
}

(** Default model coefficients (will be updated from training) *)
let default_coefficients = {
  intercept = 0.033;  (* ~3.3% expected return for good trades *)
  coef_implied_vs_last_implied = -0.05;
  coef_implied_vs_last_realized = -0.04;
  coef_implied_vs_avg_implied = -0.06;
  coef_implied_vs_avg_realized = -0.05;
}

(** Types for Market Regime Forecast Model *)

(** Trend regime - directional market state *)
type trend_regime =
  | Bull      (** Sustained uptrend *)
  | Bear      (** Sustained downtrend *)
  | Sideways  (** Range-bound, no clear direction *)

let string_of_trend_regime = function
  | Bull -> "Bull"
  | Bear -> "Bear"
  | Sideways -> "Sideways"

let trend_regime_of_int = function
  | 0 -> Bull
  | 1 -> Bear
  | 2 -> Sideways
  | _ -> failwith "Invalid trend regime index"

let int_of_trend_regime = function
  | Bull -> 0
  | Bear -> 1
  | Sideways -> 2

(** Volatility regime - market stress level *)
type vol_regime =
  | HighVol    (** Elevated volatility, stress *)
  | NormalVol  (** Typical volatility *)
  | LowVol     (** Compressed volatility, complacency *)

let string_of_vol_regime = function
  | HighVol -> "High Volatility"
  | NormalVol -> "Normal Volatility"
  | LowVol -> "Low Volatility"

(** GARCH(1,1) parameters
    σ²(t) = ω + α·ε²(t-1) + β·σ²(t-1)

    Constraints:
    - ω > 0
    - α >= 0, β >= 0
    - α + β < 1 (stationarity) *)
type garch_params = {
  omega : float;  (** Constant term *)
  alpha : float;  (** ARCH coefficient - shock reaction *)
  beta : float;   (** GARCH coefficient - persistence *)
}

(** GARCH estimation result *)
type garch_result = {
  params : garch_params;
  log_likelihood : float;
  persistence : float;       (** α + β, measures vol clustering *)
  unconditional_vol : float; (** Long-run volatility √(ω / (1 - α - β)) *)
  aic : float;               (** Akaike Information Criterion *)
  bic : float;               (** Bayesian Information Criterion *)
}

(** HMM parameters for 3-state model
    States: Bull (0), Bear (1), Sideways (2) *)
type hmm_params = {
  n_states : int;                        (** Number of hidden states *)
  transition_matrix : float array array; (** P(state_t | state_{t-1}), row-stochastic *)
  emission_means : float array;          (** Mean return per state *)
  emission_vars : float array;           (** Variance per state *)
  initial_probs : float array;           (** Initial state distribution *)
}

(** HMM estimation result *)
type hmm_result = {
  params : hmm_params;
  log_likelihood : float;
  n_iterations : int;  (** Baum-Welch iterations to converge *)
  converged : bool;
}

(** Current regime state - the main output *)
type regime_state = {
  trend : trend_regime;
  volatility : vol_regime;
  trend_probs : float array;  (** [P(Bull), P(Bear), P(Sideways)] *)
  vol_forecast : float;       (** Next-period volatility forecast (annualized) *)
  vol_percentile : float;     (** Current vol vs 5-year history [0,1] *)
  confidence : float;         (** Max of trend_probs *)
  regime_age : int;           (** Days in current trend regime *)
  return_1m : float;          (** Actual 1-month return (annualized) *)
  return_3m : float;          (** Actual 3-month return (annualized) *)
  return_6m : float;          (** Actual 6-month return (annualized) *)
}

(** Time series input data *)
type price_data = {
  ticker : string;
  dates : string array;
  prices : float array;
  returns : float array;  (** Log returns *)
}

(** Full forecast output *)
type regime_forecast = {
  as_of_date : string;
  current_state : regime_state;
  garch_fit : garch_result;
  hmm_fit : hmm_result;
  regime_history : trend_regime array;  (** Historical regime sequence from Viterbi *)
  next_trend_probs : float array;       (** Transition probabilities for next period *)
}

(** Model configuration *)
type config = {
  garch_max_iter : int;        (** Max iterations for GARCH MLE *)
  garch_tolerance : float;     (** Convergence tolerance *)
  hmm_max_iter : int;          (** Max Baum-Welch iterations *)
  hmm_tolerance : float;       (** Convergence tolerance *)
  hmm_lookback_days : int;     (** Days of data to use for HMM fitting *)
  vol_lookback_years : int;    (** Years for vol percentile calculation *)
  vol_high_percentile : float; (** Threshold for HighVol (e.g., 0.80) *)
  vol_low_percentile : float;  (** Threshold for LowVol (e.g., 0.20) *)
}

let default_config = {
  garch_max_iter = 500;
  garch_tolerance = 1e-6;
  hmm_max_iter = 100;
  hmm_tolerance = 1e-4;
  hmm_lookback_days = 504;  (* ~2 years of trading days *)
  vol_lookback_years = 5;
  vol_high_percentile = 0.80;
  vol_low_percentile = 0.20;
}

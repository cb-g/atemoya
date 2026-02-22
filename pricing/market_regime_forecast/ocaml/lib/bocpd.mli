(** Bayesian Online Changepoint Detection (BOCPD)

    Adams & MacKay (2007) algorithm for online regime detection.
    Maintains a distribution over run lengths and detects regime
    changes in real-time as new observations arrive.
*)

(** Sufficient statistics for Normal-Inverse-Gamma conjugate prior *)
type nig_stats = {
  n: float;
  sum_x: float;
  sum_x2: float;
}

(** BOCPD configuration *)
type bocpd_config = {
  hazard_lambda: float;     (** Expected run length (1/hazard rate) *)
  prior_mu: float;          (** Prior mean for returns *)
  prior_kappa: float;       (** Prior precision weight *)
  prior_alpha: float;       (** Prior shape for variance *)
  prior_beta: float;        (** Prior scale for variance *)
  max_run_length: int;      (** Truncate run lengths for efficiency *)
  changepoint_threshold: float;  (** Probability threshold for detecting change *)
}

val default_bocpd_config : bocpd_config

(** BOCPD state maintained across observations *)
type bocpd_state

(** Full BOCPD result *)
type bocpd_result = {
  state: bocpd_state;
  trend: Types.trend_regime;
  volatility: Types.vol_regime;
  run_length: int;
  expected_run_length: float;
  changepoint_prob: float;
  regime_stability: float;
  detected_changepoints: int list;
  regime_mean: float;
  regime_vol: float;
}

(** Initialize BOCPD state *)
val init : config:bocpd_config -> bocpd_state

(** Process one observation, return updated state (online update) *)
val update : bocpd_state -> float -> bocpd_state

(** Process entire return series (batch mode) *)
val run : returns:float array -> config:bocpd_config -> bocpd_state

(** Run full BOCPD analysis *)
val analyze : returns:float array -> config:bocpd_config -> bocpd_result

(** Get most likely current run length *)
val current_run_length : bocpd_state -> int

(** Get expected run length *)
val expected_run_length : bocpd_state -> float

(** Get probability of recent changepoint *)
val recent_changepoint_prob : bocpd_state -> threshold:int -> float

(** Detect changepoints in history *)
val detect_changepoints : bocpd_state -> threshold:float -> int list

(** Get current regime statistics (mean, std) *)
val current_regime_stats : bocpd_state -> (float * float) option

(** Classify current volatility regime *)
val classify_vol_regime : bocpd_state -> vol_thresholds:(float * float) -> Types.vol_regime

(** Classify current trend *)
val classify_trend : bocpd_state -> Types.trend_regime

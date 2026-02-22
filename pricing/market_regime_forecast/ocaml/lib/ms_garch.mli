(** Markov-Switching GARCH model.

    MS-GARCH integrates regime switching directly into the GARCH dynamics.
    Each regime has its own volatility parameters (omega, alpha, beta),
    and regime transitions follow a Markov chain.
*)

type ms_garch_params = {
  n_regimes: int;
  mus: float array;           (** Mean return per regime *)
  omegas: float array;        (** GARCH omega per regime *)
  alphas: float array;        (** GARCH alpha per regime *)
  betas: float array;         (** GARCH beta per regime *)
  transition_matrix: float array array;  (** Regime transition probs *)
  initial_probs: float array; (** Initial regime distribution *)
}

type ms_garch_result = {
  params: ms_garch_params;
  log_likelihood: float;
  aic: float;
  bic: float;
  converged: bool;
  n_iterations: int;
  filtered_probs: float array array;  (** P(s_t = k | r_1, ..., r_t) *)
  smoothed_probs: float array array;  (** P(s_t = k | r_1, ..., r_T) *)
}

(** Fit MS-GARCH model to returns *)
val fit : returns:float array -> config:Types.config -> ms_garch_result

(** Get current regime probabilities (smoothed) *)
val current_regime_probs : ms_garch_result -> float array

(** Get most likely current regime index *)
val current_regime : ms_garch_result -> int

(** Forecast next period regime probabilities *)
val forecast_regime_probs : ms_garch_result -> float array

(** Get unconditional volatility for each regime *)
val regime_volatilities : ms_garch_result -> float array

(** Relabel regimes so that 0 = lowest vol, K-1 = highest vol *)
val relabel_by_volatility : ms_garch_result -> ms_garch_result

(** Convert regime index to vol_regime type *)
val regime_to_vol_regime : n_regimes:int -> int -> Types.vol_regime

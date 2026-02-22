(** Bayesian Online Changepoint Detection (BOCPD)

    Adams & MacKay (2007) algorithm for online regime detection.

    Key idea: Maintain a distribution over "run lengths" (time since last
    changepoint). When probability mass shifts to short run lengths, a
    regime change has occurred.

    Components:
    - Hazard function H(t): Prior probability of changepoint at time t
    - Underlying Predictive Model (UPM): Models observations within a regime
    - Run length posterior: P(r_t | x_{1:t})
*)

open Types

(** Sufficient statistics for Normal-Inverse-Gamma conjugate prior *)
type nig_stats = {
  n: float;           (** Number of observations *)
  sum_x: float;       (** Sum of observations *)
  sum_x2: float;      (** Sum of squared observations *)
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

let default_bocpd_config = {
  hazard_lambda = 100.0;    (* Expect regime to last ~100 days *)
  prior_mu = 0.0;           (* Prior mean return = 0 *)
  prior_kappa = 1.0;        (* Weak prior on mean *)
  prior_alpha = 2.0;        (* Prior shape *)
  prior_beta = 0.0001;      (* Prior scale - corresponds to ~15% annual vol *)
  max_run_length = 300;     (* Truncate for efficiency *)
  changepoint_threshold = 0.5;
}

(** Constant hazard function: P(changepoint) = 1/lambda *)
let hazard ~config _t = 1.0 /. config.hazard_lambda

(** Initialize sufficient statistics *)
let init_stats () = { n = 0.0; sum_x = 0.0; sum_x2 = 0.0 }

(** Update sufficient statistics with new observation *)
let update_stats stats x = {
  n = stats.n +. 1.0;
  sum_x = stats.sum_x +. x;
  sum_x2 = stats.sum_x2 +. x *. x;
}

(** Student-t predictive probability under Normal-Inverse-Gamma prior

    After observing data, the predictive distribution is Student-t:
    p(x_new | x_{1:n}) = St(mu_n, sigma_n^2 * (kappa_n + 1) / kappa_n, 2*alpha_n)
*)
let student_t_logpdf ~mu ~scale ~df x =
  let z = (x -. mu) /. scale in
  let log_coef = Stdlib.log (1.0 +. z *. z /. df) in
  (* Log of gamma function approximation using Stirling *)
  let log_gamma a =
    if a <= 0.0 then neg_infinity
    else 0.5 *. log (2.0 *. Float.pi /. a) +. a *. (log (a +. 1.0 /. (12.0 *. a -. 1.0 /. (10.0 *. a))) -. 1.0)
  in
  let half_df = df /. 2.0 in
  let half_df_plus_half = (df +. 1.0) /. 2.0 in
  log_gamma half_df_plus_half -. log_gamma half_df
  -. 0.5 *. log (Float.pi *. df)
  -. log scale
  -. half_df_plus_half *. log_coef

(** Compute predictive probability for new observation given sufficient stats *)
let predictive_prob ~config ~stats x =
  (* Posterior parameters under Normal-Inverse-Gamma *)
  let kappa_n = config.prior_kappa +. stats.n in
  let mu_n = (config.prior_kappa *. config.prior_mu +. stats.sum_x) /. kappa_n in
  let alpha_n = config.prior_alpha +. stats.n /. 2.0 in

  (* Compute beta_n using sufficient statistics *)
  let ss = stats.sum_x2 -. stats.sum_x *. stats.sum_x /. max 1.0 stats.n in
  let ss = max 0.0 ss in  (* Numerical stability *)
  let mu_diff = if stats.n > 0.0 then stats.sum_x /. stats.n -. config.prior_mu else 0.0 in
  let beta_n = config.prior_beta +. 0.5 *. ss
               +. config.prior_kappa *. stats.n *. mu_diff *. mu_diff /. (2.0 *. kappa_n) in

  (* Predictive is Student-t *)
  let df = 2.0 *. alpha_n in
  let scale = sqrt (beta_n *. (kappa_n +. 1.0) /. (alpha_n *. kappa_n)) in

  let log_prob = student_t_logpdf ~mu:mu_n ~scale ~df x in
  exp log_prob

(** BOCPD state maintained across observations *)
type bocpd_state = {
  run_length_probs: float array;  (** P(r_t = r | x_{1:t}) for r = 0, 1, ..., max *)
  stats_by_run: nig_stats array;  (** Sufficient stats for each run length *)
  t: int;                         (** Current timestep *)
  config: bocpd_config;
  changepoint_probs: float list;  (** History of P(r_t = 0) *)
  regime_means: float list;       (** Estimated mean per regime segment *)
  regime_vars: float list;        (** Estimated variance per regime segment *)
}

(** Initialize BOCPD state *)
let init ~config =
  let max_r = config.max_run_length in
  let run_length_probs = Array.make (max_r + 1) 0.0 in
  run_length_probs.(0) <- 1.0;  (* Start with run length 0 *)

  let stats_by_run = Array.init (max_r + 1) (fun _ -> init_stats ()) in

  {
    run_length_probs;
    stats_by_run;
    t = 0;
    config;
    changepoint_probs = [];
    regime_means = [];
    regime_vars = [];
  }

(** Process one observation, return updated state *)
let update state x =
  let config = state.config in
  let max_r = config.max_run_length in

  (* Step 1: Compute predictive probabilities for each run length *)
  let pred_probs = Array.init (max_r + 1) (fun r ->
    if state.run_length_probs.(r) > 1e-300 then
      predictive_prob ~config ~stats:state.stats_by_run.(r) x
    else
      0.0
  ) in

  (* Step 2: Compute growth probabilities (run length increases) *)
  let h = hazard ~config state.t in
  let growth_probs = Array.init (max_r + 1) (fun r ->
    if r = 0 then 0.0
    else state.run_length_probs.(r - 1) *. pred_probs.(r - 1) *. (1.0 -. h)
  ) in

  (* Step 3: Compute changepoint probability (run length resets to 0) *)
  let cp_prob = ref 0.0 in
  for r = 0 to max_r do
    cp_prob := !cp_prob +. state.run_length_probs.(r) *. pred_probs.(r) *. h
  done;

  (* Step 4: Combine into new run length distribution *)
  let new_probs = Array.make (max_r + 1) 0.0 in
  new_probs.(0) <- !cp_prob;
  for r = 1 to max_r do
    new_probs.(r) <- growth_probs.(r)
  done;

  (* Step 5: Normalize *)
  let total = Array.fold_left (+.) 0.0 new_probs in
  if total > 1e-300 then
    Array.iteri (fun i p -> new_probs.(i) <- p /. total) new_probs;

  (* Step 6: Update sufficient statistics *)
  let new_stats = Array.init (max_r + 1) (fun r ->
    if r = 0 then init_stats ()
    else if r - 1 <= max_r then update_stats state.stats_by_run.(r - 1) x
    else init_stats ()
  ) in
  (* Also update stats for run length 0 with new observation for next iteration *)
  new_stats.(0) <- update_stats (init_stats ()) x;

  (* Compute current regime statistics (weighted by run length probs) *)
  let weighted_mean = ref 0.0 in
  let weighted_var = ref 0.0 in
  for r = 0 to max_r do
    if new_probs.(r) > 1e-10 && new_stats.(r).n > 0.0 then begin
      let stats = new_stats.(r) in
      let mean = stats.sum_x /. stats.n in
      let var = if stats.n > 1.0 then
        (stats.sum_x2 -. stats.sum_x *. stats.sum_x /. stats.n) /. (stats.n -. 1.0)
      else config.prior_beta /. config.prior_alpha in
      weighted_mean := !weighted_mean +. new_probs.(r) *. mean;
      weighted_var := !weighted_var +. new_probs.(r) *. var
    end
  done;

  {
    run_length_probs = new_probs;
    stats_by_run = new_stats;
    t = state.t + 1;
    config;
    changepoint_probs = !cp_prob :: state.changepoint_probs;
    regime_means = !weighted_mean :: state.regime_means;
    regime_vars = !weighted_var :: state.regime_vars;
  }

(** Process entire return series *)
let run ~returns ~config =
  let state = ref (init ~config) in
  for i = 0 to Array.length returns - 1 do
    state := update !state returns.(i)
  done;
  !state

(** Get most likely current run length *)
let current_run_length state =
  let max_idx = ref 0 in
  for i = 1 to Array.length state.run_length_probs - 1 do
    if state.run_length_probs.(i) > state.run_length_probs.(!max_idx) then
      max_idx := i
  done;
  !max_idx

(** Get probability of recent changepoint (run length < threshold) *)
let recent_changepoint_prob state ~threshold =
  let prob = ref 0.0 in
  for r = 0 to min threshold (Array.length state.run_length_probs - 1) do
    prob := !prob +. state.run_length_probs.(r)
  done;
  !prob

(** Get expected run length *)
let expected_run_length state =
  let expected = ref 0.0 in
  for r = 0 to Array.length state.run_length_probs - 1 do
    expected := !expected +. float_of_int r *. state.run_length_probs.(r)
  done;
  !expected

(** Detect changepoints in history *)
let detect_changepoints state ~threshold =
  let cp_probs = Array.of_list (List.rev state.changepoint_probs) in
  let changepoints = ref [] in
  for t = 0 to Array.length cp_probs - 1 do
    if cp_probs.(t) > threshold then
      changepoints := t :: !changepoints
  done;
  List.rev !changepoints

(** Get regime statistics for current segment *)
let current_regime_stats state =
  let run_len = current_run_length state in
  let stats = state.stats_by_run.(run_len) in
  if stats.n > 0.0 then begin
    let mean = stats.sum_x /. stats.n in
    let var = if stats.n > 1.0 then
      (stats.sum_x2 -. stats.sum_x *. stats.sum_x /. stats.n) /. (stats.n -. 1.0)
    else state.config.prior_beta /. state.config.prior_alpha in
    Some (mean, sqrt var)
  end else
    None

(** Classify current volatility regime based on regime variance *)
let classify_vol_regime state ~vol_thresholds =
  let (low_thresh, high_thresh) = vol_thresholds in
  match current_regime_stats state with
  | None -> NormalVol
  | Some (_, vol) ->
      let annualized_vol = vol *. sqrt 252.0 in
      if annualized_vol > high_thresh then HighVol
      else if annualized_vol < low_thresh then LowVol
      else NormalVol

(** Classify trend based on regime mean *)
let classify_trend state =
  match current_regime_stats state with
  | None -> Sideways
  | Some (mean, _) ->
      let annualized_ret = mean *. 252.0 in
      if annualized_ret > 0.10 then Bull
      else if annualized_ret < -0.05 then Bear
      else Sideways

(** Full BOCPD result *)
type bocpd_result = {
  state: bocpd_state;
  trend: trend_regime;
  volatility: vol_regime;
  run_length: int;
  expected_run_length: float;
  changepoint_prob: float;        (** P(changepoint just occurred) *)
  regime_stability: float;        (** 1 - P(recent changepoint) *)
  detected_changepoints: int list;
  regime_mean: float;
  regime_vol: float;
}

(** Run full BOCPD analysis *)
let analyze ~returns ~config =
  let state = run ~returns ~config in

  let trend = classify_trend state in
  let volatility = classify_vol_regime state ~vol_thresholds:(0.12, 0.25) in
  let run_length = current_run_length state in
  let exp_run = expected_run_length state in

  let cp_prob = if List.length state.changepoint_probs > 0 then
    List.hd state.changepoint_probs
  else 0.0 in

  let stability = 1.0 -. recent_changepoint_prob state ~threshold:5 in
  let changepoints = detect_changepoints state ~threshold:config.changepoint_threshold in

  let (regime_mean, regime_vol) = match current_regime_stats state with
    | Some (m, v) -> (m, v)
    | None -> (0.0, 0.0)
  in

  {
    state;
    trend;
    volatility;
    run_length;
    expected_run_length = exp_run;
    changepoint_prob = cp_prob;
    regime_stability = stability;
    detected_changepoints = changepoints;
    regime_mean;
    regime_vol;
  }

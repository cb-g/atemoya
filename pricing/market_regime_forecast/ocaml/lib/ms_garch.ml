(** Markov-Switching GARCH model.

    Unlike separate GARCH + HMM, MS-GARCH has regime-dependent GARCH parameters.
    Each regime k has its own (omega_k, alpha_k, beta_k), and transitions follow
    a Markov chain.

    Model:
      r_t = mu_k + epsilon_t,  where s_t = k
      epsilon_t = sigma_t * z_t,  z_t ~ N(0,1)
      sigma^2_t = omega_k + alpha_k * epsilon^2_{t-1} + beta_k * sigma^2_{t-1}
      P(s_t = j | s_{t-1} = i) = p_ij
*)

open Types

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

let pi = Float.pi

(** Normal PDF *)
let normal_pdf ~mu ~sigma x =
  let z = (x -. mu) /. sigma in
  exp (-0.5 *. z *. z) /. (sigma *. sqrt (2.0 *. pi))

(** Initialize parameters with reasonable starting values *)
let init_params ~returns ~n_regimes =
  let n = Array.length returns in
  let mean_ret = Array.fold_left (+.) 0.0 returns /. float_of_int n in
  let var_ret =
    Array.fold_left (fun acc r -> acc +. (r -. mean_ret) ** 2.0) 0.0 returns
    /. float_of_int n
  in

  (* Initialize regimes with different volatility levels *)
  let mus = Array.make n_regimes mean_ret in
  let omegas = Array.init n_regimes (fun k ->
    let scale = 1.0 +. float_of_int k *. 0.5 in
    var_ret *. 0.05 *. scale
  ) in
  let alphas = Array.init n_regimes (fun k ->
    0.05 +. float_of_int k *. 0.05  (* Higher alpha in higher vol regimes *)
  ) in
  let betas = Array.init n_regimes (fun _ -> 0.90) in

  (* Symmetric transition matrix with persistence *)
  let transition_matrix = Array.init n_regimes (fun i ->
    Array.init n_regimes (fun j ->
      if i = j then 0.95 else 0.05 /. float_of_int (n_regimes - 1)
    )
  ) in

  let initial_probs = Array.make n_regimes (1.0 /. float_of_int n_regimes) in

  { n_regimes; mus; omegas; alphas; betas; transition_matrix; initial_probs }

(** Compute conditional variance for regime k given previous variance and return *)
let compute_variance ~params ~regime ~prev_var ~prev_ret =
  let omega = params.omegas.(regime) in
  let alpha = params.alphas.(regime) in
  let beta = params.betas.(regime) in
  let mu = params.mus.(regime) in
  let eps = prev_ret -. mu in
  omega +. alpha *. eps *. eps +. beta *. prev_var

(** Forward algorithm for MS-GARCH - computes filtered probabilities and likelihood *)
let forward_pass ~params ~returns =
  let n = Array.length returns in
  let k = params.n_regimes in

  (* filtered_probs.(t).(j) = P(s_t = j | r_1, ..., r_t) *)
  let filtered_probs = Array.make_matrix n k 0.0 in

  (* predicted_probs.(t).(j) = P(s_t = j | r_1, ..., r_{t-1}) *)
  let predicted_probs = Array.make_matrix n k 0.0 in

  (* Conditional variances for each regime *)
  let variances = Array.make_matrix n k 0.0 in

  let log_likelihood = ref 0.0 in

  (* Initialize with unconditional variance *)
  let unconditional_var = Array.init k (fun regime ->
    let omega = params.omegas.(regime) in
    let alpha = params.alphas.(regime) in
    let beta = params.betas.(regime) in
    let persistence = alpha +. beta in
    if persistence < 1.0 then omega /. (1.0 -. persistence)
    else omega /. 0.01  (* Fallback for non-stationary *)
  ) in

  for t = 0 to n - 1 do
    (* Prediction step: P(s_t | r_1, ..., r_{t-1}) *)
    if t = 0 then
      Array.blit params.initial_probs 0 predicted_probs.(t) 0 k
    else begin
      for j = 0 to k - 1 do
        let sum = ref 0.0 in
        for i = 0 to k - 1 do
          sum := !sum +. filtered_probs.(t-1).(i) *. params.transition_matrix.(i).(j)
        done;
        predicted_probs.(t).(j) <- !sum
      done
    end;

    (* Compute conditional variances *)
    for regime = 0 to k - 1 do
      if t = 0 then
        variances.(t).(regime) <- unconditional_var.(regime)
      else begin
        (* Use regime-weighted previous variance *)
        let prev_var = ref 0.0 in
        for i = 0 to k - 1 do
          prev_var := !prev_var +. filtered_probs.(t-1).(i) *. variances.(t-1).(i)
        done;
        variances.(t).(regime) <- compute_variance
          ~params ~regime ~prev_var:!prev_var ~prev_ret:returns.(t-1)
      end;
      (* Floor variance *)
      if variances.(t).(regime) < 1e-10 then
        variances.(t).(regime) <- 1e-10
    done;

    (* Compute observation likelihoods *)
    let likelihoods = Array.init k (fun regime ->
      let mu = params.mus.(regime) in
      let sigma = sqrt variances.(t).(regime) in
      normal_pdf ~mu ~sigma returns.(t)
    ) in

    (* Filtering step: P(s_t | r_1, ..., r_t) *)
    let marginal_likelihood = ref 0.0 in
    for j = 0 to k - 1 do
      let joint = predicted_probs.(t).(j) *. likelihoods.(j) in
      filtered_probs.(t).(j) <- joint;
      marginal_likelihood := !marginal_likelihood +. joint
    done;

    (* Normalize *)
    if !marginal_likelihood > 1e-300 then begin
      for j = 0 to k - 1 do
        filtered_probs.(t).(j) <- filtered_probs.(t).(j) /. !marginal_likelihood
      done;
      log_likelihood := !log_likelihood +. log !marginal_likelihood
    end
  done;

  (filtered_probs, variances, !log_likelihood)

(** Backward smoothing - computes P(s_t | r_1, ..., r_T) *)
let backward_smooth ~params ~filtered_probs ~returns =
  let n = Array.length returns in
  let k = params.n_regimes in
  let smoothed_probs = Array.make_matrix n k 0.0 in

  (* Initialize at T *)
  Array.blit filtered_probs.(n-1) 0 smoothed_probs.(n-1) 0 k;

  (* Backward recursion *)
  for t = n - 2 downto 0 do
    for i = 0 to k - 1 do
      let sum = ref 0.0 in
      for j = 0 to k - 1 do
        (* P(s_{t+1} = j | r_1, ..., r_t) *)
        let pred_prob = ref 0.0 in
        for m = 0 to k - 1 do
          pred_prob := !pred_prob +. filtered_probs.(t).(m) *. params.transition_matrix.(m).(j)
        done;
        if !pred_prob > 1e-300 then
          sum := !sum +. params.transition_matrix.(i).(j) *. smoothed_probs.(t+1).(j) /. !pred_prob
      done;
      smoothed_probs.(t).(i) <- filtered_probs.(t).(i) *. !sum
    done;

    (* Normalize *)
    let total = Array.fold_left (+.) 0.0 smoothed_probs.(t) in
    if total > 1e-300 then
      for i = 0 to k - 1 do
        smoothed_probs.(t).(i) <- smoothed_probs.(t).(i) /. total
      done
  done;

  smoothed_probs

(** EM algorithm for parameter estimation *)
let fit_em ~returns ~n_regimes ~max_iter ~tol =
  let n = Array.length returns in
  let params = ref (init_params ~returns ~n_regimes) in
  let prev_ll = ref neg_infinity in
  let converged = ref false in
  let iter = ref 0 in

  while !iter < max_iter && not !converged do
    incr iter;

    (* E-step: compute filtered and smoothed probabilities *)
    let (filtered_probs, variances, ll) = forward_pass ~params:!params ~returns in
    let smoothed_probs = backward_smooth ~params:!params ~filtered_probs ~returns in

    (* Check convergence *)
    if abs_float (ll -. !prev_ll) < tol then
      converged := true;
    prev_ll := ll;

    (* M-step: update parameters *)
    let k = n_regimes in

    (* Update transition matrix *)
    let new_trans = Array.make_matrix k k 0.0 in
    for i = 0 to k - 1 do
      let row_sum = ref 0.0 in
      for j = 0 to k - 1 do
        let num = ref 0.0 in
        for t = 1 to n - 1 do
          (* Joint probability P(s_{t-1}=i, s_t=j | all data) *)
          let pred_prob = ref 0.0 in
          for m = 0 to k - 1 do
            pred_prob := !pred_prob +. filtered_probs.(t-1).(m) *. (!params).transition_matrix.(m).(j)
          done;
          if !pred_prob > 1e-300 then begin
            let joint = filtered_probs.(t-1).(i) *. (!params).transition_matrix.(i).(j)
                        *. smoothed_probs.(t).(j) /. !pred_prob in
            num := !num +. joint
          end
        done;
        new_trans.(i).(j) <- !num;
        row_sum := !row_sum +. !num
      done;
      (* Normalize row *)
      if !row_sum > 1e-300 then
        for j = 0 to k - 1 do
          new_trans.(i).(j) <- new_trans.(i).(j) /. !row_sum
        done
      else
        (* Fallback to uniform *)
        for j = 0 to k - 1 do
          new_trans.(i).(j) <- 1.0 /. float_of_int k
        done
    done;

    (* Update regime-specific parameters *)
    let new_mus = Array.make k 0.0 in
    let new_omegas = Array.make k 0.0 in
    let new_alphas = Array.make k 0.0 in
    let new_betas = Array.make k 0.0 in

    for regime = 0 to k - 1 do
      let weight_sum = ref 0.0 in
      let weighted_ret = ref 0.0 in

      for t = 0 to n - 1 do
        let w = smoothed_probs.(t).(regime) in
        weight_sum := !weight_sum +. w;
        weighted_ret := !weighted_ret +. w *. returns.(t)
      done;

      if !weight_sum > 1e-10 then begin
        new_mus.(regime) <- !weighted_ret /. !weight_sum;

        (* Estimate GARCH parameters using weighted regression *)
        let mu = new_mus.(regime) in
        let eps2_sum = ref 0.0 in
        let var_lag_sum = ref 0.0 in
        let eps2_lag_sum = ref 0.0 in
        let var_sum = ref 0.0 in

        for t = 1 to n - 1 do
          let w = smoothed_probs.(t).(regime) in
          let eps_prev = returns.(t-1) -. mu in
          let var_prev = variances.(t-1).(regime) in
          let var_curr = variances.(t).(regime) in

          eps2_sum := !eps2_sum +. w *. (returns.(t) -. mu) ** 2.0;
          var_lag_sum := !var_lag_sum +. w *. var_prev;
          eps2_lag_sum := !eps2_lag_sum +. w *. eps_prev *. eps_prev;
          var_sum := !var_sum +. w *. var_curr
        done;

        (* Simple moment-based estimation with constraints *)
        let avg_var = !eps2_sum /. !weight_sum in
        new_omegas.(regime) <- max 1e-8 (avg_var *. 0.05);
        new_alphas.(regime) <- max 0.01 (min 0.3 (!params).alphas.(regime));  (* Keep bounded *)
        new_betas.(regime) <- max 0.5 (min 0.98 (!params).betas.(regime));

        (* Ensure stationarity *)
        let persistence = new_alphas.(regime) +. new_betas.(regime) in
        if persistence >= 0.999 then begin
          let scale = 0.998 /. persistence in
          new_alphas.(regime) <- new_alphas.(regime) *. scale;
          new_betas.(regime) <- new_betas.(regime) *. scale
        end
      end else begin
        (* Keep previous values *)
        new_mus.(regime) <- (!params).mus.(regime);
        new_omegas.(regime) <- (!params).omegas.(regime);
        new_alphas.(regime) <- (!params).alphas.(regime);
        new_betas.(regime) <- (!params).betas.(regime)
      end
    done;

    (* Update initial probs *)
    let new_initial = Array.copy smoothed_probs.(0) in

    params := {
      n_regimes = k;
      mus = new_mus;
      omegas = new_omegas;
      alphas = new_alphas;
      betas = new_betas;
      transition_matrix = new_trans;
      initial_probs = new_initial;
    }
  done;

  (* Final pass to get results *)
  let (filtered_probs, _variances, ll) = forward_pass ~params:!params ~returns in
  let smoothed_probs = backward_smooth ~params:!params ~filtered_probs ~returns in

  let n_params = n_regimes * 4 + n_regimes * n_regimes in  (* mu, omega, alpha, beta per regime + transition *)
  let aic = -2.0 *. ll +. 2.0 *. float_of_int n_params in
  let bic = -2.0 *. ll +. float_of_int n_params *. log (float_of_int n) in

  {
    params = !params;
    log_likelihood = ll;
    aic;
    bic;
    converged = !converged;
    n_iterations = !iter;
    filtered_probs;
    smoothed_probs;
  }

(** Fit MS-GARCH model *)
let fit ~returns ~(config : config) =
  let n_regimes = 3 in  (* Low vol, Normal vol, High vol *)
  fit_em ~returns ~n_regimes ~max_iter:config.hmm_max_iter ~tol:config.hmm_tolerance

(** Get current regime probabilities *)
let current_regime_probs result =
  let n = Array.length result.smoothed_probs in
  result.smoothed_probs.(n - 1)

(** Get most likely current regime *)
let current_regime result =
  let probs = current_regime_probs result in
  let max_idx = ref 0 in
  for i = 1 to Array.length probs - 1 do
    if probs.(i) > probs.(!max_idx) then max_idx := i
  done;
  !max_idx

(** Forecast next period regime probabilities *)
let forecast_regime_probs result =
  let probs = current_regime_probs result in
  let k = result.params.n_regimes in
  let forecast = Array.make k 0.0 in
  for j = 0 to k - 1 do
    for i = 0 to k - 1 do
      forecast.(j) <- forecast.(j) +. probs.(i) *. result.params.transition_matrix.(i).(j)
    done
  done;
  forecast

(** Get volatility forecast for each regime *)
let regime_volatilities result =
  Array.init result.params.n_regimes (fun k ->
    let omega = result.params.omegas.(k) in
    let alpha = result.params.alphas.(k) in
    let beta = result.params.betas.(k) in
    let persistence = alpha +. beta in
    if persistence < 1.0 then
      sqrt (omega /. (1.0 -. persistence))
    else
      sqrt (omega /. 0.01)
  )

(** Relabel regimes by volatility (0 = lowest vol, K-1 = highest vol) *)
let relabel_by_volatility result =
  let k = result.params.n_regimes in
  let vols = regime_volatilities result in

  (* Create index array sorted by volatility *)
  let indices = Array.init k (fun i -> i) in
  Array.sort (fun i j -> compare vols.(i) vols.(j)) indices;

  (* Create mapping: new_idx -> old_idx *)
  let mapping = indices in
  let inv_mapping = Array.make k 0 in
  Array.iteri (fun new_idx old_idx -> inv_mapping.(old_idx) <- new_idx) mapping;

  (* Reorder parameters *)
  let new_mus = Array.init k (fun i -> result.params.mus.(mapping.(i))) in
  let new_omegas = Array.init k (fun i -> result.params.omegas.(mapping.(i))) in
  let new_alphas = Array.init k (fun i -> result.params.alphas.(mapping.(i))) in
  let new_betas = Array.init k (fun i -> result.params.betas.(mapping.(i))) in
  let new_initial = Array.init k (fun i -> result.params.initial_probs.(mapping.(i))) in

  let new_trans = Array.init k (fun i ->
    Array.init k (fun j ->
      result.params.transition_matrix.(mapping.(i)).(mapping.(j))
    )
  ) in

  (* Reorder probability arrays *)
  let n = Array.length result.filtered_probs in
  let new_filtered = Array.init n (fun t ->
    Array.init k (fun i -> result.filtered_probs.(t).(mapping.(i)))
  ) in
  let new_smoothed = Array.init n (fun t ->
    Array.init k (fun i -> result.smoothed_probs.(t).(mapping.(i)))
  ) in

  {
    params = {
      n_regimes = k;
      mus = new_mus;
      omegas = new_omegas;
      alphas = new_alphas;
      betas = new_betas;
      transition_matrix = new_trans;
      initial_probs = new_initial;
    };
    log_likelihood = result.log_likelihood;
    aic = result.aic;
    bic = result.bic;
    converged = result.converged;
    n_iterations = result.n_iterations;
    filtered_probs = new_filtered;
    smoothed_probs = new_smoothed;
  }

(** Convert regime index to volatility regime type *)
let regime_to_vol_regime ~n_regimes idx =
  if n_regimes = 2 then
    if idx = 0 then LowVol else HighVol
  else if n_regimes = 3 then
    match idx with
    | 0 -> LowVol
    | 1 -> NormalVol
    | _ -> HighVol
  else
    NormalVol

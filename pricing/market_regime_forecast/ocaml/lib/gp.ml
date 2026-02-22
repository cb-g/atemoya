(** Gaussian Process Regime Detection

    Uses GP regression to model return dynamics with uncertainty quantification.
    The posterior mean indicates trend, posterior variance indicates regime stability.
*)

open Types

(** GP kernel types *)
type kernel_type =
  | RBF           (** Squared Exponential / Radial Basis Function *)
  | Matern32      (** Matern 3/2 - less smooth *)
  | Matern52      (** Matern 5/2 - moderately smooth *)
  | RationalQuadratic of float  (** RQ with alpha parameter *)

(** GP hyperparameters *)
type gp_params = {
  kernel: kernel_type;
  length_scale: float;    (** Characteristic length scale *)
  signal_var: float;      (** Signal variance (amplitude^2) *)
  noise_var: float;       (** Observation noise variance *)
}

(** GP configuration *)
type gp_config = {
  kernel_type: kernel_type;
  optimize_hyperparams: bool;
  max_opt_iter: int;
  lookback_days: int;     (** Use recent N days for GP fitting *)
  forecast_horizon: int;  (** Days ahead to forecast *)
}

let default_gp_config = {
  kernel_type = Matern52;
  optimize_hyperparams = true;
  max_opt_iter = 50;
  lookback_days = 252;    (* 1 year *)
  forecast_horizon = 21;  (* 1 month *)
}

(** Squared Exponential (RBF) kernel: k(x, x') = σ² exp(-|x-x'|²/(2l²)) *)
let rbf_kernel ~length_scale ~signal_var x1 x2 =
  let d = x1 -. x2 in
  signal_var *. exp (-0.5 *. d *. d /. (length_scale *. length_scale))

(** Matern 3/2 kernel: k(x, x') = σ²(1 + √3|x-x'|/l) exp(-√3|x-x'|/l) *)
let matern32_kernel ~length_scale ~signal_var x1 x2 =
  let d = abs_float (x1 -. x2) in
  let r = sqrt 3.0 *. d /. length_scale in
  signal_var *. (1.0 +. r) *. exp (-.r)

(** Matern 5/2 kernel: k(x, x') = σ²(1 + √5|x-x'|/l + 5|x-x'|²/(3l²)) exp(-√5|x-x'|/l) *)
let matern52_kernel ~length_scale ~signal_var x1 x2 =
  let d = abs_float (x1 -. x2) in
  let r = sqrt 5.0 *. d /. length_scale in
  let r2 = 5.0 *. d *. d /. (3.0 *. length_scale *. length_scale) in
  signal_var *. (1.0 +. r +. r2) *. exp (-.r)

(** Rational Quadratic kernel: k(x, x') = σ²(1 + |x-x'|²/(2αl²))^(-α) *)
let rq_kernel ~length_scale ~signal_var ~alpha x1 x2 =
  let d = x1 -. x2 in
  let term = 1.0 +. d *. d /. (2.0 *. alpha *. length_scale *. length_scale) in
  signal_var *. (term ** (-.alpha))

(** Compute kernel value based on type *)
let compute_kernel ~params x1 x2 =
  let l = params.length_scale in
  let s = params.signal_var in
  match params.kernel with
  | RBF -> rbf_kernel ~length_scale:l ~signal_var:s x1 x2
  | Matern32 -> matern32_kernel ~length_scale:l ~signal_var:s x1 x2
  | Matern52 -> matern52_kernel ~length_scale:l ~signal_var:s x1 x2
  | RationalQuadratic alpha -> rq_kernel ~length_scale:l ~signal_var:s ~alpha x1 x2

(** Build covariance matrix K(X, X) + σ²_n I *)
let build_cov_matrix ~params ~x =
  let n = Array.length x in
  let k = Array.make_matrix n n 0.0 in
  for i = 0 to n - 1 do
    for j = 0 to n - 1 do
      k.(i).(j) <- compute_kernel ~params x.(i) x.(j);
      if i = j then k.(i).(i) <- k.(i).(i) +. params.noise_var
    done
  done;
  k

(** Build cross-covariance matrix K(X*, X) *)
let build_cross_cov ~params ~x_train ~x_test =
  let n_train = Array.length x_train in
  let n_test = Array.length x_test in
  let k = Array.make_matrix n_test n_train 0.0 in
  for i = 0 to n_test - 1 do
    for j = 0 to n_train - 1 do
      k.(i).(j) <- compute_kernel ~params x_test.(i) x_train.(j)
    done
  done;
  k

(** Cholesky decomposition (lower triangular) *)
let cholesky a =
  let n = Array.length a in
  let l = Array.make_matrix n n 0.0 in
  for i = 0 to n - 1 do
    for j = 0 to i do
      let sum = ref 0.0 in
      for k = 0 to j - 1 do
        sum := !sum +. l.(i).(k) *. l.(j).(k)
      done;
      if i = j then
        l.(i).(j) <- sqrt (max 1e-10 (a.(i).(i) -. !sum))
      else
        l.(i).(j) <- (a.(i).(j) -. !sum) /. l.(j).(j)
    done
  done;
  l

(** Solve L x = b for lower triangular L *)
let solve_lower l b =
  let n = Array.length b in
  let x = Array.copy b in
  for i = 0 to n - 1 do
    for j = 0 to i - 1 do
      x.(i) <- x.(i) -. l.(i).(j) *. x.(j)
    done;
    x.(i) <- x.(i) /. l.(i).(i)
  done;
  x

(** Solve L^T x = b for lower triangular L *)
let solve_upper_t l b =
  let n = Array.length b in
  let x = Array.copy b in
  for i = n - 1 downto 0 do
    for j = i + 1 to n - 1 do
      x.(i) <- x.(i) -. l.(j).(i) *. x.(j)
    done;
    x.(i) <- x.(i) /. l.(i).(i)
  done;
  x

(** GP posterior computation *)
type gp_posterior = {
  mean: float array;      (** Posterior mean at test points *)
  var: float array;       (** Posterior variance at test points *)
  log_marginal_likelihood: float;
}

(** Compute GP posterior *)
let compute_posterior ~params ~x_train ~y_train ~x_test =
  let n_train = Array.length x_train in
  let n_test = Array.length x_test in

  (* Build K + σ²I and Cholesky decompose *)
  let k_train = build_cov_matrix ~params ~x:x_train in
  let l = cholesky k_train in

  (* Solve L α' = y, then L^T α = α' *)
  let alpha' = solve_lower l y_train in
  let alpha = solve_upper_t l alpha' in

  (* K(X*, X) *)
  let k_cross = build_cross_cov ~params ~x_train ~x_test in

  (* Posterior mean: K* α *)
  let mean = Array.make n_test 0.0 in
  for i = 0 to n_test - 1 do
    for j = 0 to n_train - 1 do
      mean.(i) <- mean.(i) +. k_cross.(i).(j) *. alpha.(j)
    done
  done;

  (* Posterior variance: K** - K* K^(-1) K*^T *)
  (* Solve L v = K*^T for each test point *)
  let var = Array.make n_test 0.0 in
  for i = 0 to n_test - 1 do
    let k_star_i = Array.init n_train (fun j -> k_cross.(i).(j)) in
    let v = solve_lower l k_star_i in
    let v_dot_v = Array.fold_left (fun acc x -> acc +. x *. x) 0.0 v in
    let k_star_star = compute_kernel ~params x_test.(i) x_test.(i) in
    var.(i) <- max 0.0 (k_star_star -. v_dot_v)
  done;

  (* Log marginal likelihood: -1/2 y^T K^(-1) y - 1/2 log|K| - n/2 log(2π) *)
  let y_alpha = ref 0.0 in
  for i = 0 to n_train - 1 do
    y_alpha := !y_alpha +. y_train.(i) *. alpha.(i)
  done;

  let log_det = ref 0.0 in
  for i = 0 to n_train - 1 do
    log_det := !log_det +. log l.(i).(i)
  done;
  let log_det = 2.0 *. !log_det in  (* log|K| = 2 * sum(log(diag(L))) *)

  let log_ml = -0.5 *. !y_alpha -. 0.5 *. log_det
               -. float_of_int n_train /. 2.0 *. log (2.0 *. Float.pi) in

  { mean; var; log_marginal_likelihood = log_ml }

(** Simple grid search for hyperparameter optimization *)
let optimize_hyperparams ~kernel_type ~x_train ~y_train =
  let best_params = ref {
    kernel = kernel_type;
    length_scale = 20.0;
    signal_var = 0.0001;
    noise_var = 0.0001;
  } in
  let best_ml = ref neg_infinity in

  (* Estimate initial values from data *)
  let n = Array.length y_train in
  let y_var =
    let mean = Array.fold_left (+.) 0.0 y_train /. float_of_int n in
    Array.fold_left (fun acc y -> acc +. (y -. mean) ** 2.0) 0.0 y_train /. float_of_int n
  in

  (* Grid search over length scales and variances *)
  let length_scales = [| 5.0; 10.0; 20.0; 40.0; 60.0 |] in
  let signal_vars = [| y_var *. 0.5; y_var; y_var *. 2.0 |] in
  let noise_vars = [| y_var *. 0.1; y_var *. 0.3; y_var *. 0.5 |] in

  Array.iter (fun l ->
    Array.iter (fun s ->
      Array.iter (fun noise ->
        let params = { kernel = kernel_type; length_scale = l; signal_var = s; noise_var = noise } in
        try
          let posterior = compute_posterior ~params ~x_train ~y_train ~x_test:[||] in
          if posterior.log_marginal_likelihood > !best_ml then begin
            best_ml := posterior.log_marginal_likelihood;
            best_params := params
          end
        with _ -> ()  (* Skip if Cholesky fails *)
      ) noise_vars
    ) signal_vars
  ) length_scales;

  !best_params

(** GP regression result *)
type gp_result = {
  params: gp_params;
  posterior: gp_posterior;
  trend_forecast: float array;
  uncertainty: float array;
  current_trend: float;
  current_uncertainty: float;
  anomaly_score: float;  (** How far current return is from GP prediction *)
}

(** Fit GP to returns and produce forecast *)
let fit ~returns ~config =
  let n = Array.length returns in
  let lookback = min n config.lookback_days in

  (* Use recent data *)
  let start_idx = n - lookback in
  let x_train = Array.init lookback (fun i -> float_of_int i) in
  let y_train = Array.sub returns start_idx lookback in

  (* Optimize hyperparameters *)
  let params =
    if config.optimize_hyperparams then
      optimize_hyperparams ~kernel_type:config.kernel_type ~x_train ~y_train
    else
      { kernel = config.kernel_type; length_scale = 20.0;
        signal_var = 0.0001; noise_var = 0.0001 }
  in

  (* Create test points: current + forecast horizon *)
  let x_test = Array.init (config.forecast_horizon + 1) (fun i ->
    float_of_int (lookback - 1 + i)
  ) in

  (* Compute posterior *)
  let posterior = compute_posterior ~params ~x_train ~y_train ~x_test in

  (* Current trend is the GP prediction at the last training point *)
  let current_trend = posterior.mean.(0) in
  let current_uncertainty = sqrt posterior.var.(0) in

  (* Anomaly score: how many std devs is the actual return from prediction? *)
  let last_return = y_train.(lookback - 1) in
  let anomaly_score =
    if current_uncertainty > 1e-10 then
      abs_float (last_return -. current_trend) /. current_uncertainty
    else 0.0
  in

  {
    params;
    posterior;
    trend_forecast = Array.sub posterior.mean 1 config.forecast_horizon;
    uncertainty = Array.map sqrt (Array.sub posterior.var 1 config.forecast_horizon);
    current_trend;
    current_uncertainty;
    anomaly_score;
  }

(** Classify trend based on GP posterior mean *)
let classify_trend ~result =
  let ann_trend = result.current_trend *. 252.0 in
  if ann_trend > 0.10 then Bull
  else if ann_trend < -0.05 then Bear
  else Sideways

(** Classify volatility based on GP uncertainty *)
let classify_volatility ~result ~historical_returns =
  (* Compare GP uncertainty to historical volatility *)
  let n = Array.length historical_returns in
  let hist_vol =
    let mean = Array.fold_left (+.) 0.0 historical_returns /. float_of_int n in
    sqrt (Array.fold_left (fun acc r -> acc +. (r -. mean) ** 2.0) 0.0 historical_returns /. float_of_int n)
  in
  let ann_uncertainty = result.current_uncertainty *. sqrt 252.0 in
  let ann_hist_vol = hist_vol *. sqrt 252.0 in

  if ann_uncertainty > ann_hist_vol *. 1.5 then HighVol
  else if ann_uncertainty < ann_hist_vol *. 0.7 then LowVol
  else NormalVol

(** Full GP classification result *)
type gp_classification = {
  result: gp_result;
  trend: trend_regime;
  volatility: vol_regime;
  regime_confidence: float;
  forecast_mean: float;     (** Mean of forecast (annualized) *)
  forecast_std: float;      (** Std of forecast (annualized) *)
}

(** Run full GP analysis *)
let analyze ~returns ~config =
  let result = fit ~returns ~config in
  let trend = classify_trend ~result in
  let volatility = classify_volatility ~result ~historical_returns:returns in

  (* Confidence based on inverse of uncertainty *)
  let regime_confidence = 1.0 /. (1.0 +. result.anomaly_score) in

  (* Forecast statistics *)
  let n_forecast = Array.length result.trend_forecast in
  let forecast_mean =
    Array.fold_left (+.) 0.0 result.trend_forecast /. float_of_int n_forecast *. 252.0
  in
  let forecast_std =
    let mean_unc = Array.fold_left (+.) 0.0 result.uncertainty /. float_of_int n_forecast in
    mean_unc *. sqrt 252.0
  in

  {
    result;
    trend;
    volatility;
    regime_confidence;
    forecast_mean;
    forecast_std;
  }

(** String representation of kernel type *)
let string_of_kernel = function
  | RBF -> "RBF (Squared Exponential)"
  | Matern32 -> "Matern 3/2"
  | Matern52 -> "Matern 5/2"
  | RationalQuadratic alpha -> Printf.sprintf "Rational Quadratic (α=%.2f)" alpha

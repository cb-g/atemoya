(** GARCH(1,1) Model Implementation

    σ²(t) = ω + α·ε²(t-1) + β·σ²(t-1)

    where ε(t) = r(t) - μ (demeaned return)

    Estimation via Maximum Likelihood *)

open Types

(** Annualization factor for daily data *)
let trading_days_per_year = 252.0

(** Small constant for numerical stability *)
let eps = 1e-10

(** Calculate conditional variances given GARCH parameters
    Returns array of σ²(t) for t = 1..n *)
let conditional_variances ~params ~returns =
  let n = Array.length returns in
  if n < 2 then failwith "Need at least 2 returns for GARCH";

  let { omega; alpha; beta } = params in

  (* Demean returns *)
  let mean = Array.fold_left (+.) 0.0 returns /. float_of_int n in
  let residuals = Array.map (fun r -> r -. mean) returns in

  (* Initialize variance with sample variance *)
  let sample_var =
    Array.fold_left (fun acc e -> acc +. e *. e) 0.0 residuals
    /. float_of_int n
  in

  let variances = Array.make n sample_var in

  (* Recursion: σ²(t) = ω + α·ε²(t-1) + β·σ²(t-1) *)
  for t = 1 to n - 1 do
    let e_sq = residuals.(t - 1) *. residuals.(t - 1) in
    let prev_var = variances.(t - 1) in
    variances.(t) <- omega +. (alpha *. e_sq) +. (beta *. prev_var)
  done;

  (residuals, variances)

(** Calculate negative log-likelihood (to minimize)
    L = -0.5 * Σ [log(σ²(t)) + ε²(t)/σ²(t)] *)
let neg_log_likelihood ~params ~returns =
  let { omega; alpha; beta } = params in

  (* Check constraints *)
  if omega <= 0.0 || alpha < 0.0 || beta < 0.0 || alpha +. beta >= 1.0 then
    infinity
  else
    let (residuals, variances) = conditional_variances ~params ~returns in
    let n = Array.length returns in

    let ll = ref 0.0 in
    for t = 0 to n - 1 do
      let var_t = max variances.(t) eps in
      let e_t = residuals.(t) in
      ll := !ll -. 0.5 *. (log var_t +. (e_t *. e_t /. var_t))
    done;

    -. !ll  (* Return negative for minimization *)

(** Nelder-Mead simplex optimization
    Simple but robust optimizer for 3 parameters *)
let nelder_mead ~f ~x0 ~max_iter ~tolerance =
  let n = Array.length x0 in
  let alpha = 1.0 in   (* Reflection *)
  let gamma = 2.0 in   (* Expansion *)
  let rho = 0.5 in     (* Contraction *)
  let sigma = 0.5 in   (* Shrink *)

  (* Initialize simplex: n+1 points *)
  let simplex = Array.make (n + 1) (Array.copy x0) in
  for i = 1 to n do
    simplex.(i) <- Array.copy x0;
    simplex.(i).(i - 1) <- x0.(i - 1) *. 1.5 +. 0.001
  done;

  (* Evaluate all points *)
  let values = Array.map f simplex in

  let centroid = Array.make n 0.0 in

  let iter = ref 0 in
  let converged = ref false in

  while !iter < max_iter && not !converged do
    incr iter;

    (* Sort by function value *)
    let indices = Array.init (n + 1) (fun i -> i) in
    Array.sort (fun i j -> compare values.(i) values.(j)) indices;

    let best_idx = indices.(0) in
    let worst_idx = indices.(n) in
    let second_worst_idx = indices.(n - 1) in

    (* Check convergence *)
    let range = values.(worst_idx) -. values.(best_idx) in
    if range < tolerance then converged := true
    else begin
      (* Compute centroid of all points except worst *)
      Array.fill centroid 0 n 0.0;
      for i = 0 to n - 1 do
        let idx = indices.(i) in
        for j = 0 to n - 1 do
          centroid.(j) <- centroid.(j) +. simplex.(idx).(j)
        done
      done;
      for j = 0 to n - 1 do
        centroid.(j) <- centroid.(j) /. float_of_int n
      done;

      (* Reflection *)
      let reflected = Array.init n (fun j ->
        centroid.(j) +. alpha *. (centroid.(j) -. simplex.(worst_idx).(j))
      ) in
      let f_reflected = f reflected in

      if f_reflected < values.(best_idx) then begin
        (* Try expansion *)
        let expanded = Array.init n (fun j ->
          centroid.(j) +. gamma *. (reflected.(j) -. centroid.(j))
        ) in
        let f_expanded = f expanded in
        if f_expanded < f_reflected then begin
          simplex.(worst_idx) <- expanded;
          values.(worst_idx) <- f_expanded
        end else begin
          simplex.(worst_idx) <- reflected;
          values.(worst_idx) <- f_reflected
        end
      end
      else if f_reflected < values.(second_worst_idx) then begin
        simplex.(worst_idx) <- reflected;
        values.(worst_idx) <- f_reflected
      end
      else begin
        (* Contraction *)
        let contracted =
          if f_reflected < values.(worst_idx) then
            Array.init n (fun j ->
              centroid.(j) +. rho *. (reflected.(j) -. centroid.(j))
            )
          else
            Array.init n (fun j ->
              centroid.(j) +. rho *. (simplex.(worst_idx).(j) -. centroid.(j))
            )
        in
        let f_contracted = f contracted in

        if f_contracted < min f_reflected values.(worst_idx) then begin
          simplex.(worst_idx) <- contracted;
          values.(worst_idx) <- f_contracted
        end
        else begin
          (* Shrink *)
          for i = 1 to n do
            let idx = indices.(i) in
            for j = 0 to n - 1 do
              simplex.(idx).(j) <-
                simplex.(best_idx).(j) +.
                sigma *. (simplex.(idx).(j) -. simplex.(best_idx).(j))
            done;
            values.(idx) <- f simplex.(idx)
          done
        end
      end
    end
  done;

  (* Return best point *)
  let best_idx = ref 0 in
  for i = 1 to n do
    if values.(i) < values.(!best_idx) then best_idx := i
  done;

  (simplex.(!best_idx), values.(!best_idx), !iter, !converged)

(** Fit GARCH(1,1) model to returns via MLE *)
let fit ~returns ~config =
  let n = Array.length returns in
  if n < 50 then failwith "Need at least 50 observations for GARCH";

  (* Sample variance for initialization *)
  let mean = Array.fold_left (+.) 0.0 returns /. float_of_int n in
  let sample_var =
    Array.fold_left (fun acc r ->
      let d = r -. mean in acc +. d *. d
    ) 0.0 returns /. float_of_int n
  in

  (* Initial guess: omega, alpha, beta *)
  let x0 = [| sample_var *. 0.1; 0.1; 0.8 |] in

  (* Objective function: map array to params *)
  let objective x =
    let params = { omega = x.(0); alpha = x.(1); beta = x.(2) } in
    neg_log_likelihood ~params ~returns
  in

  (* Optimize *)
  let (x_opt, neg_ll, _n_iter, _converged) =
    nelder_mead
      ~f:objective
      ~x0
      ~max_iter:config.garch_max_iter
      ~tolerance:config.garch_tolerance
  in

  let params = { omega = x_opt.(0); alpha = x_opt.(1); beta = x_opt.(2) } in
  let persistence = params.alpha +. params.beta in

  let unconditional_var =
    if persistence < 1.0 then params.omega /. (1.0 -. persistence)
    else sample_var
  in

  let log_likelihood = -. neg_ll in
  let k = 3 in  (* Number of parameters *)
  let aic = 2.0 *. float_of_int k -. 2.0 *. log_likelihood in
  let bic = float_of_int k *. log (float_of_int n) -. 2.0 *. log_likelihood in

  {
    params;
    log_likelihood;
    persistence;
    unconditional_vol = sqrt unconditional_var *. sqrt trading_days_per_year;
    aic;
    bic;
  }

(** Forecast next-period variance *)
let forecast_variance ~params ~last_residual_sq ~last_variance =
  let { omega; alpha; beta } = params in
  omega +. (alpha *. last_residual_sq) +. (beta *. last_variance)

(** Forecast volatility (annualized) given fitted model and recent data *)
let forecast_vol ~(result : Types.garch_result) ~returns =
  let (residuals, variances) = conditional_variances ~params:result.params ~returns in
  let n = Array.length returns in

  let last_e_sq = residuals.(n - 1) *. residuals.(n - 1) in
  let last_var = variances.(n - 1) in

  let next_var = forecast_variance
    ~params:result.params
    ~last_residual_sq:last_e_sq
    ~last_variance:last_var
  in

  (* Annualize: daily vol * sqrt(252) *)
  sqrt next_var *. sqrt trading_days_per_year

(** Get current (last) annualized volatility *)
let current_vol ~(result : Types.garch_result) ~returns =
  let (_, variances) = conditional_variances ~params:result.params ~returns in
  let n = Array.length returns in
  sqrt variances.(n - 1) *. sqrt trading_days_per_year

(** Calculate historical volatility percentile *)
let vol_percentile ~returns ~current_vol ~lookback_years =
  let lookback_days = lookback_years * 252 in
  let n = Array.length returns in
  let actual_lookback = min lookback_days n in

  if actual_lookback < 252 then 0.5  (* Not enough data, return neutral *)
  else
    (* Calculate rolling 20-day realized vol over lookback period *)
    let window = 20 in
    let num_windows = actual_lookback - window + 1 in
    let vols = Array.make num_windows 0.0 in

    for i = 0 to num_windows - 1 do
      let start_idx = n - actual_lookback + i in
      let window_returns = Array.sub returns start_idx window in
      let mean =
        Array.fold_left (+.) 0.0 window_returns /. float_of_int window
      in
      let var =
        Array.fold_left (fun acc r ->
          let d = r -. mean in acc +. d *. d
        ) 0.0 window_returns /. float_of_int window
      in
      vols.(i) <- sqrt var *. sqrt trading_days_per_year
    done;

    (* Sort and find percentile *)
    let sorted = Array.copy vols in
    Array.sort compare sorted;

    let count_below =
      Array.fold_left (fun acc v ->
        if v < current_vol then acc + 1 else acc
      ) 0 sorted
    in

    float_of_int count_below /. float_of_int num_windows

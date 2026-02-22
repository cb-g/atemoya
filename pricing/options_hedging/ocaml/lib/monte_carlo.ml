(* Monte Carlo Option Pricing - Longstaff-Schwartz for American Options *)

open Types

(* Box-Muller transform for generating standard normal random variables *)
let box_muller () =
  let u1 = Random.float 1.0 in
  let u2 = Random.float 1.0 in
  let r = sqrt (-2.0 *. log u1) in
  let theta = 2.0 *. Float.pi *. u2 in
  (r *. cos theta, r *. sin theta)

(* Generate a single standard normal random variable *)
let normal_random () =
  let (z, _) = box_muller () in
  z

(* Compute immediate exercise value for an option *)
let exercise_value option_type ~spot ~strike =
  match option_type with
  | Call -> max 0.0 (spot -. strike)
  | Put -> max 0.0 (strike -. spot)

(* Laguerre polynomial basis functions for regression
   L_0(x) = 1
   L_1(x) = 1 - x
   L_2(x) = (2 - 4x + x²) / 2
   L_3(x) = (6 - 18x + 9x² - x³) / 6
*)
let laguerre_basis ~x ~degree =
  let basis = Array.make (degree + 1) 0.0 in

  if degree >= 0 then basis.(0) <- 1.0;

  if degree >= 1 then basis.(1) <- 1.0 -. x;

  if degree >= 2 then
    basis.(2) <- (2.0 -. 4.0 *. x +. x *. x) /. 2.0;

  if degree >= 3 then
    basis.(3) <- (6.0 -. 18.0 *. x +. 9.0 *. x *. x -. x *. x *. x) /. 6.0;

  (* For higher degrees, use recurrence relation:
     L_{n+1}(x) = ((2n+1-x)L_n(x) - n·L_{n-1}(x)) / (n+1)
  *)
  for n = 3 to degree - 1 do
    let n_f = float_of_int n in
    basis.(n + 1) <-
      ((2.0 *. n_f +. 1.0 -. x) *. basis.(n) -. n_f *. basis.(n - 1))
      /. (n_f +. 1.0)
  done;

  basis

(* Estimate condition number of a square matrix using power iteration
   Returns: approximate condition number (ratio of largest to smallest singular value)
   For numerical stability checks in regression *)
let estimate_condition_number mat =
  let n = Owl.Mat.row_num mat in
  if n == 0 then 1.0
  else
    try
      (* Use SVD to get condition number = σ_max / σ_min *)
      let (_, s, _) = Owl.Linalg.D.svd mat in
      let s_arr = Owl.Mat.to_array s in
      let s_max = Array.fold_left max 0.0 s_arr in
      let s_min = Array.fold_left (fun acc x ->
        if x > 1e-15 then min acc x else acc
      ) infinity s_arr in
      if s_min > 1e-15 then s_max /. s_min
      else infinity
    with
    | Failure _ | Invalid_argument _ ->
      (* SVD can fail on ill-conditioned or invalid matrices *)
      infinity

(* Simple linear regression: Y = Xβ + ε
   Returns: β coefficients

   Includes condition number check to detect ill-conditioned matrices
   that could lead to numerical instability in the regression.
*)
let linear_regression (x_data : float array array) (y_data : float array) =
  let n = Array.length y_data in
  let p = if n > 0 then Array.length x_data.(0) else 0 in  (* Number of features *)

  if n = 0 || p = 0 then
    Array.make (max 1 p) 0.0
  else if n < p then
    (* Underdetermined system: not enough data points *)
    Array.make p 0.0
  else
    (* Use normal equations: β = (X'X)^{-1} X'Y *)
    (* For simplicity, use Owl's matrix operations *)
    let open Owl.Mat in

    let x_mat = of_arrays x_data in
    let y_vec = of_array y_data 1 n in

    try
      let xt = transpose x_mat in
      let xtx = dot xt x_mat in

      (* Check condition number before solving *)
      let cond_num = estimate_condition_number xtx in

      (* If condition number is too high, use ridge regression (Tikhonov regularization)
         This adds a small amount to the diagonal to stabilize the solution:
         β = (X'X + λI)^{-1} X'Y *)
      let needs_regularization = Stdlib.(cond_num > 1e10) in
      let xtx_regularized =
        if needs_regularization then begin
          (* Add ridge penalty: λ = trace(X'X) / p * 1e-6 *)
          let trace_xtx = Owl.Mat.trace xtx in
          let lambda = trace_xtx /. float_of_int p *. 1e-6 in
          let identity = eye p in
          add xtx (mul_scalar identity lambda)
        end else
          xtx
      in

      let xty = dot xt y_vec in

      (* Solve: (X'X + λI) β = X'Y *)
      let beta_mat = Owl.Linalg.D.linsolve xtx_regularized xty in
      to_array beta_mat
    with
    | Failure _ | Invalid_argument _ ->
      (* If singular matrix or linear algebra error, return zero coefficients *)
      Array.make p 0.0

(* Simulate GBM price paths
   dS = (r - q)S dt + σS dW
   S(t+dt) = S(t) exp((r - q - σ²/2)dt + σ√dt·Z)
*)
let simulate_price_paths ~spot ~rate ~dividend ~volatility ~expiry ~num_steps ~num_paths =
  let dt = expiry /. float_of_int num_steps in
  let sqrt_dt = sqrt dt in
  let drift = (rate -. dividend -. 0.5 *. volatility *. volatility) *. dt in
  let diffusion = volatility *. sqrt_dt in

  let paths = Array.make_matrix num_paths (num_steps + 1) 0.0 in

  (* Initialize all paths at spot price *)
  for i = 0 to num_paths - 1 do
    paths.(i).(0) <- spot
  done;

  (* Simulate paths forward *)
  for i = 0 to num_paths - 1 do
    for t = 0 to num_steps - 1 do
      let z = normal_random () in
      let log_return = drift +. diffusion *. z in
      paths.(i).(t + 1) <- paths.(i).(t) *. exp log_return
    done
  done;

  paths

(* Longstaff-Schwartz algorithm for American option pricing *)
let price_american_option option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility ~num_paths ~num_steps =
  if expiry <= 0.0 then
    exercise_value option_type ~spot ~strike
  else
    (* Generate price paths *)
    let paths = simulate_price_paths ~spot ~rate ~dividend ~volatility ~expiry ~num_steps ~num_paths in

    (* Cash flows matrix: when to exercise *)
    let cash_flows = Array.make_matrix num_paths (num_steps + 1) 0.0 in

    (* Initialize with payoff at expiry *)
    for i = 0 to num_paths - 1 do
      let terminal_price = paths.(i).(num_steps) in
      cash_flows.(i).(num_steps) <- exercise_value option_type ~spot:terminal_price ~strike
    done;

    let dt = expiry /. float_of_int num_steps in
    let discount = exp (-. rate *. dt) in

    (* Backward induction from T-1 to 1 *)
    for t = num_steps - 1 downto 1 do
      (* Find in-the-money paths at time t *)
      let itm_paths = ref [] in
      let itm_prices = ref [] in
      let itm_continuation = ref [] in

      for i = 0 to num_paths - 1 do
        let current_price = paths.(i).(t) in
        let immediate_exercise = exercise_value option_type ~spot:current_price ~strike in

        if immediate_exercise > 0.0 then begin
          itm_paths := i :: !itm_paths;
          itm_prices := current_price :: !itm_prices;

          (* Continuation value: discounted future cash flow *)
          let future_cf = cash_flows.(i).(t + 1) *. discount in
          itm_continuation := future_cf :: !itm_continuation
        end
      done;

      let num_itm = List.length !itm_paths in

      if num_itm > 5 then begin
        (* Have enough data points for regression *)
        let prices_array = Array.of_list (List.rev !itm_prices) in
        let continuation_array = Array.of_list (List.rev !itm_continuation) in

        (* Build regression features using Laguerre polynomials *)
        let degree = min 3 (num_itm - 2) in  (* Use up to degree 3 *)
        let x_data = Array.init num_itm (fun i ->
          let price = prices_array.(i) in
          let normalized_price = price /. strike in  (* Normalize by strike *)
          laguerre_basis ~x:normalized_price ~degree
        ) in

        (* Fit regression: continuation value = f(price) *)
        let beta = linear_regression x_data continuation_array in

        (* Update cash flows based on exercise decision *)
        let itm_paths_array = Array.of_list (List.rev !itm_paths) in
        for j = 0 to num_itm - 1 do
          let path_idx = itm_paths_array.(j) in
          let current_price = paths.(path_idx).(t) in
          let immediate_exercise = exercise_value option_type ~spot:current_price ~strike in

          (* Predicted continuation value *)
          let normalized_price = current_price /. strike in
          let basis = laguerre_basis ~x:normalized_price ~degree in
          let continuation_value = ref 0.0 in
          for k = 0 to Array.length beta - 1 do
            continuation_value := !continuation_value +. beta.(k) *. basis.(k)
          done;

          (* Exercise if immediate value > continuation value *)
          if immediate_exercise > !continuation_value then begin
            cash_flows.(path_idx).(t) <- immediate_exercise;
            (* Zero out future cash flows (already exercised) *)
            for tt = t + 1 to num_steps do
              cash_flows.(path_idx).(tt) <- 0.0
            done
          end else begin
            (* Don't exercise now, keep future cash flow *)
            cash_flows.(path_idx).(t) <- 0.0
          end
        done
      end else begin
        (* Not enough ITM paths for regression - use simple rule *)
        for i = 0 to num_paths - 1 do
          let current_price = paths.(i).(t) in
          let immediate_exercise = exercise_value option_type ~spot:current_price ~strike in

          (* Simple heuristic: exercise if deep ITM *)
          let moneyness = match option_type with
          | Put -> strike /. current_price
          | Call -> current_price /. strike
          in

          if moneyness > 1.2 && immediate_exercise > 0.0 then begin
            cash_flows.(i).(t) <- immediate_exercise;
            for tt = t + 1 to num_steps do
              cash_flows.(i).(tt) <- 0.0
            done
          end else begin
            cash_flows.(i).(t) <- 0.0
          end
        done
      end
    done;

    (* Average discounted cash flows across all paths *)
    let total_value = ref 0.0 in

    for i = 0 to num_paths - 1 do
      (* Find first exercise time for this path *)
      let exercise_time = ref None in
      for t = 1 to num_steps do
        if cash_flows.(i).(t) > 0.0 && !exercise_time = None then
          exercise_time := Some t
      done;

      match !exercise_time with
      | Some t ->
          let discount_factor = exp (-. rate *. float_of_int t *. dt) in
          total_value := !total_value +. cash_flows.(i).(t) *. discount_factor
      | None -> ()
    done;

    !total_value /. float_of_int num_paths

(* Monte Carlo Delta via finite differences *)
let monte_carlo_delta option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility ~num_paths ~num_steps =
  let bump = 0.01 *. spot in  (* 1% bump *)

  let price_up = price_american_option option_type
    ~spot:(spot +. bump) ~strike ~expiry ~rate ~dividend ~volatility ~num_paths ~num_steps in

  let price_down = price_american_option option_type
    ~spot:(spot -. bump) ~strike ~expiry ~rate ~dividend ~volatility ~num_paths ~num_steps in

  (price_up -. price_down) /. (2.0 *. bump)

(* Monte Carlo Gamma via finite differences *)
let monte_carlo_gamma option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility ~num_paths ~num_steps =
  let bump = 0.01 *. spot in  (* 1% bump *)

  let price_mid = price_american_option option_type
    ~spot ~strike ~expiry ~rate ~dividend ~volatility ~num_paths ~num_steps in

  let price_up = price_american_option option_type
    ~spot:(spot +. bump) ~strike ~expiry ~rate ~dividend ~volatility ~num_paths ~num_steps in

  let price_down = price_american_option option_type
    ~spot:(spot -. bump) ~strike ~expiry ~rate ~dividend ~volatility ~num_paths ~num_steps in

  (price_up -. 2.0 *. price_mid +. price_down) /. (bump *. bump)

(* Monte Carlo Vega via finite differences *)
let monte_carlo_vega option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility ~num_paths ~num_steps =
  let bump = 0.01 in  (* 1% absolute bump *)

  let price_up = price_american_option option_type
    ~spot ~strike ~expiry ~rate ~dividend ~volatility:(volatility +. bump) ~num_paths ~num_steps in

  let price_down = price_american_option option_type
    ~spot ~strike ~expiry ~rate ~dividend ~volatility:(volatility -. bump) ~num_paths ~num_steps in

  (price_up -. price_down) /. (2.0 *. bump) /. 100.0  (* Per 1% vol change *)

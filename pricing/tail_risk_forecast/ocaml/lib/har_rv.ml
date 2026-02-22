(** HAR-RV Model Implementation *)

open Types

let min_observations = 30

(* Rolling average helper *)
let rolling_avg (rv_series : daily_rv array) (end_idx : int) (window : int) : float =
  if end_idx < window - 1 then
    (* Not enough history, use what we have *)
    let start = 0 in
    let count = end_idx + 1 in
    let sum = ref 0.0 in
    for i = start to end_idx do
      sum := !sum +. rv_series.(i).rv
    done;
    !sum /. float_of_int count
  else
    let sum = ref 0.0 in
    for i = end_idx - window + 1 to end_idx do
      sum := !sum +. rv_series.(i).rv
    done;
    !sum /. float_of_int window

let rv_weekly rv_series idx = rolling_avg rv_series idx 5
let rv_monthly rv_series idx = rolling_avg rv_series idx 22

(* Simple OLS for HAR-RV: y = X * beta + epsilon
   We solve beta = (X'X)^(-1) * X'y using normal equations *)

(* 4x4 matrix inverse for HAR model (c, beta_d, beta_w, beta_m) *)
let invert_4x4 (m : float array array) : float array array option =
  (* Gaussian elimination with partial pivoting *)
  let n = 4 in
  let a = Array.init n (fun i -> Array.copy m.(i)) in
  let inv = Array.init n (fun i -> Array.init n (fun j -> if i = j then 1.0 else 0.0)) in

  try
    for col = 0 to n - 1 do
      (* Find pivot *)
      let max_row = ref col in
      let max_val = ref (abs_float a.(col).(col)) in
      for row = col + 1 to n - 1 do
        if abs_float a.(row).(col) > !max_val then begin
          max_val := abs_float a.(row).(col);
          max_row := row
        end
      done;

      if !max_val < 1e-10 then raise Exit;  (* Singular matrix *)

      (* Swap rows *)
      if !max_row <> col then begin
        let tmp = a.(col) in a.(col) <- a.(!max_row); a.(!max_row) <- tmp;
        let tmp = inv.(col) in inv.(col) <- inv.(!max_row); inv.(!max_row) <- tmp
      end;

      (* Scale pivot row *)
      let pivot = a.(col).(col) in
      for j = 0 to n - 1 do
        a.(col).(j) <- a.(col).(j) /. pivot;
        inv.(col).(j) <- inv.(col).(j) /. pivot
      done;

      (* Eliminate column *)
      for row = 0 to n - 1 do
        if row <> col then begin
          let factor = a.(row).(col) in
          for j = 0 to n - 1 do
            a.(row).(j) <- a.(row).(j) -. factor *. a.(col).(j);
            inv.(row).(j) <- inv.(row).(j) -. factor *. inv.(col).(j)
          done
        end
      done
    done;
    Some inv
  with Exit -> None

let estimate_har (rv_series : daily_rv array) : har_coefficients =
  let n = Array.length rv_series in

  if n < min_observations then
    (* Not enough data, return simple mean model *)
    let mean_rv = Array.fold_left (fun acc (r : daily_rv) -> acc +. r.rv) 0.0 rv_series /. float_of_int n in
    { c = mean_rv; beta_d = 0.0; beta_w = 0.0; beta_m = 0.0; r_squared = 0.0 }
  else
    (* Build design matrix X and response vector y
       For each t from 22 to n-2 (need monthly history and next-day target):
       y_t = RV_{t+1}
       X_t = [1, RV_t, RV_t^(w), RV_t^(m)] *)
    let start_idx = 22 in  (* Need 22 days of history for monthly *)
    let num_obs = n - start_idx - 1 in

    if num_obs < 15 then
      let mean_rv = Array.fold_left (fun acc (r : daily_rv) -> acc +. r.rv) 0.0 rv_series /. float_of_int n in
      { c = mean_rv; beta_d = 0.0; beta_w = 0.0; beta_m = 0.0; r_squared = 0.0 }
    else
      (* Build X (num_obs x 4) and y (num_obs x 1) *)
      let x = Array.init num_obs (fun i ->
        let t = start_idx + i in
        [| 1.0; rv_series.(t).rv; rv_weekly rv_series t; rv_monthly rv_series t |]
      ) in
      let y = Array.init num_obs (fun i ->
        let t = start_idx + i in
        rv_series.(t + 1).rv
      ) in

      (* Compute X'X (4x4) *)
      let xtx = Array.init 4 (fun i ->
        Array.init 4 (fun j ->
          let sum = ref 0.0 in
          for k = 0 to num_obs - 1 do
            sum := !sum +. x.(k).(i) *. x.(k).(j)
          done;
          !sum
        )
      ) in

      (* Compute X'y (4x1) *)
      let xty = Array.init 4 (fun i ->
        let sum = ref 0.0 in
        for k = 0 to num_obs - 1 do
          sum := !sum +. x.(k).(i) *. y.(k)
        done;
        !sum
      ) in

      (* Solve beta = (X'X)^(-1) * X'y *)
      match invert_4x4 xtx with
      | None ->
        let mean_rv = Array.fold_left (fun acc (r : daily_rv) -> acc +. r.rv) 0.0 rv_series /. float_of_int n in
        { c = mean_rv; beta_d = 0.0; beta_w = 0.0; beta_m = 0.0; r_squared = 0.0 }
      | Some xtx_inv ->
        let beta = Array.init 4 (fun i ->
          let sum = ref 0.0 in
          for j = 0 to 3 do
            sum := !sum +. xtx_inv.(i).(j) *. xty.(j)
          done;
          !sum
        ) in

        (* Compute R-squared *)
        let y_mean = Array.fold_left (+.) 0.0 y /. float_of_int num_obs in
        let ss_tot = Array.fold_left (fun acc yi -> acc +. (yi -. y_mean) ** 2.0) 0.0 y in
        let ss_res = ref 0.0 in
        for k = 0 to num_obs - 1 do
          let y_pred = beta.(0) +. beta.(1) *. x.(k).(1) +. beta.(2) *. x.(k).(2) +. beta.(3) *. x.(k).(3) in
          ss_res := !ss_res +. (y.(k) -. y_pred) ** 2.0
        done;
        let r_squared = if ss_tot > 0.0 then 1.0 -. !ss_res /. ss_tot else 0.0 in

        { c = beta.(0); beta_d = beta.(1); beta_w = beta.(2); beta_m = beta.(3); r_squared }

let forecast_rv (model : har_coefficients) (rv_series : daily_rv array) : float =
  let n = Array.length rv_series in
  if n = 0 then 0.0
  else
    let last_idx = n - 1 in
    let rv_d = rv_series.(last_idx).rv in
    let rv_w = rv_weekly rv_series last_idx in
    let rv_m = rv_monthly rv_series last_idx in

    let forecast = model.c +. model.beta_d *. rv_d +. model.beta_w *. rv_w +. model.beta_m *. rv_m in
    (* Ensure non-negative *)
    max 0.0 forecast

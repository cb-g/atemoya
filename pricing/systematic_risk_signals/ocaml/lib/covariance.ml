(** Covariance matrix computation and eigenvalue decomposition. *)

open Types

(** Compute mean of an array *)
let mean arr =
  let n = Array.length arr in
  if n = 0 then 0.0
  else Array.fold_left ( +. ) 0.0 arr /. float_of_int n

(** Compute standard deviation *)
let _std arr =
  let n = Array.length arr in
  if n <= 1 then 0.0
  else
    let m = mean arr in
    let sum_sq = Array.fold_left (fun acc x -> acc +. (x -. m) ** 2.0) 0.0 arr in
    sqrt (sum_sq /. float_of_int (n - 1))

(** Compute covariance between two arrays *)
let cov arr1 arr2 =
  let n = min (Array.length arr1) (Array.length arr2) in
  if n <= 1 then 0.0
  else
    let m1 = mean arr1 in
    let m2 = mean arr2 in
    let sum = ref 0.0 in
    for i = 0 to n - 1 do
      sum := !sum +. (arr1.(i) -. m1) *. (arr2.(i) -. m2)
    done;
    !sum /. float_of_int (n - 1)

let compute_covariance (returns : asset_returns array) : covariance_matrix =
  let n = Array.length returns in
  let matrix = Array.make_matrix n n 0.0 in
  let tickers = Array.map (fun r -> r.ticker) returns in

  for i = 0 to n - 1 do
    for j = i to n - 1 do
      let c = cov returns.(i).returns returns.(j).returns in
      matrix.(i).(j) <- c;
      matrix.(j).(i) <- c
    done
  done;

  { matrix; tickers; n_assets = n }

let to_correlation (cov_mat : covariance_matrix) : float array array =
  let n = cov_mat.n_assets in
  let corr = Array.make_matrix n n 0.0 in
  let stds = Array.init n (fun i -> sqrt cov_mat.matrix.(i).(i)) in

  for i = 0 to n - 1 do
    for j = 0 to n - 1 do
      if stds.(i) > 1e-10 && stds.(j) > 1e-10 then
        corr.(i).(j) <- cov_mat.matrix.(i).(j) /. (stds.(i) *. stds.(j))
      else
        corr.(i).(j) <- if i = j then 1.0 else 0.0
    done
  done;
  corr

(** Matrix-vector multiplication *)
let mat_vec_mult mat vec =
  let n = Array.length vec in
  Array.init n (fun i ->
    let sum = ref 0.0 in
    for j = 0 to n - 1 do
      sum := !sum +. mat.(i).(j) *. vec.(j)
    done;
    !sum
  )

(** Vector normalization *)
let normalize vec =
  let norm = sqrt (Array.fold_left (fun acc x -> acc +. x *. x) 0.0 vec) in
  if norm > 1e-10 then
    Array.map (fun x -> x /. norm) vec
  else vec

(** Dot product *)
let dot v1 v2 =
  let sum = ref 0.0 in
  for i = 0 to Array.length v1 - 1 do
    sum := !sum +. v1.(i) *. v2.(i)
  done;
  !sum

(** Power iteration for largest eigenvalue/eigenvector *)
let power_iteration mat max_iter tol =
  let n = Array.length mat in
  let vec = Array.init n (fun _ -> Random.float 1.0) in
  let vec = normalize vec in
  let vec = ref vec in
  let eigenvalue = ref 0.0 in

  for _ = 1 to max_iter do
    let new_vec = mat_vec_mult mat !vec in
    let new_eigenvalue = dot new_vec !vec in
    let new_vec = normalize new_vec in

    if abs_float (new_eigenvalue -. !eigenvalue) < tol then begin
      eigenvalue := new_eigenvalue;
      vec := new_vec
    end else begin
      eigenvalue := new_eigenvalue;
      vec := new_vec
    end
  done;

  (!eigenvalue, !vec)

(** Deflate matrix by removing contribution of eigenvector *)
let deflate mat eigenvalue eigenvec =
  let n = Array.length mat in
  let deflated = Array.make_matrix n n 0.0 in

  for i = 0 to n - 1 do
    for j = 0 to n - 1 do
      deflated.(i).(j) <- mat.(i).(j) -. eigenvalue *. eigenvec.(i) *. eigenvec.(j)
    done
  done;
  deflated

let eigen_decompose (cov_mat : covariance_matrix) : eigen_decomposition =
  let n = cov_mat.n_assets in
  let num_eigenvalues = min n 6 in  (* We need at most 5+1 eigenvalues *)
  let eigenvalues = Array.make num_eigenvalues 0.0 in
  let eigenvectors = Array.make_matrix num_eigenvalues n 0.0 in

  let mat = ref (Array.map Array.copy cov_mat.matrix) in

  for k = 0 to num_eigenvalues - 1 do
    let (eigenval, eigenvec) = power_iteration !mat 100 1e-8 in
    eigenvalues.(k) <- max 0.0 eigenval;  (* Ensure non-negative *)
    eigenvectors.(k) <- eigenvec;
    mat := deflate !mat eigenval eigenvec
  done;

  { eigenvalues; eigenvectors }

let var_explained_first (eigen : eigen_decomposition) : float =
  let total = Array.fold_left ( +. ) 0.0 eigen.eigenvalues in
  if total > 1e-10 then
    eigen.eigenvalues.(0) /. total
  else 0.0

let var_explained_2_to_5 (eigen : eigen_decomposition) : float =
  let total = Array.fold_left ( +. ) 0.0 eigen.eigenvalues in
  if total < 1e-10 then 0.0
  else
    let n = Array.length eigen.eigenvalues in
    let sum_2_to_5 = ref 0.0 in
    for i = 1 to min 4 (n - 1) do
      sum_2_to_5 := !sum_2_to_5 +. eigen.eigenvalues.(i)
    done;
    !sum_2_to_5 /. total

let correlation_to_distance (corr : float array array) : float array array =
  let n = Array.length corr in
  let dist = Array.make_matrix n n 0.0 in

  for i = 0 to n - 1 do
    for j = 0 to n - 1 do
      (* d_ij = sqrt(1 - rho_ij^2) per paper equation (4) *)
      let rho = corr.(i).(j) in
      let rho_sq = rho *. rho in
      dist.(i).(j) <- sqrt (max 0.0 (1.0 -. rho_sq))
    done
  done;
  dist

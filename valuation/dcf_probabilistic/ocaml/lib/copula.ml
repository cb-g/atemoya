(** Copula module for modeling dependence between financial metrics *)

open Types

(** Configuration for copula-based sampling *)
type copula_config = {
  use_copula : bool;
  correlation_matrix : float array array;
}

(** Error function approximation (Abramowitz and Stegun formula)

    erf(x) ≈ sign(x) * sqrt(1 - exp(-x^2 * (4/π + ax^2) / (1 + ax^2)))

    where a = 0.147
*)
let erf x =
  let a = 0.147 in
  let x2 = x *. x in
  let pi = acos (-1.0) in
  let numerator = x2 *. ((4.0 /. pi) +. (a *. x2)) in
  let denominator = 1.0 +. (a *. x2) in
  let sign_x = if x >= 0.0 then 1.0 else -1.0 in
  sign_x *. sqrt (1.0 -. exp (-.numerator /. denominator))

(** Standard normal CDF (using error function) *)
let standard_normal_cdf x =
  (* Φ(x) = 0.5 * (1 + erf(x / sqrt(2))) *)
  let sqrt2 = sqrt 2.0 in
  0.5 *. (1.0 +. (erf (x /. sqrt2)))

(** Sample from multivariate standard normal with correlation matrix

    Uses Cholesky decomposition: X = L × Z where Z ~ N(0, I)

    Returns: array of correlated standard normal samples
*)
let sample_multivariate_standard_normal ~correlation =
  let n = Array.length correlation in

  (* Sample independent standard normals *)
  let z = Array.init n (fun _ -> Sampling.standard_normal_sample ()) in

  (* Cholesky decomposition (with auto-regularization if needed) *)
  let l = Sampling.cholesky_decomposition correlation in

  (* Transform: x = L × z *)
  Array.init n (fun i ->
    let sum = ref 0.0 in
    for j = 0 to i do
      sum := !sum +. (l.(i).(j) *. z.(j))
    done;
    !sum
  )

(** Transform standard normal samples to uniform [0, 1] via CDF *)
let normals_to_uniforms normals =
  Array.map (fun x ->
    let u = standard_normal_cdf x in
    (* Clamp to (epsilon, 1-epsilon) to avoid boundary issues *)
    let epsilon = 1e-10 in
    max epsilon (min (1.0 -. epsilon) u)
  ) normals

(** Sample from empirical distribution using percentile (inverse CDF)

    Given:
    - time_series: historical data
    - u: uniform sample in [0, 1]

    Returns: value at u-th percentile of time_series
*)
let sample_from_percentile ~time_series ~percentile =
  let cleaned = Sampling.clean_array time_series in
  let n = Array.length cleaned in

  if n = 0 then 0.0
  else if n = 1 then cleaned.(0)
  else
    (* Sort array *)
    let sorted = Array.copy cleaned in
    Array.sort compare sorted;

    (* Linear interpolation at percentile *)
    let float_idx = percentile *. float_of_int (n - 1) in
    let idx_lower = int_of_float (floor float_idx) in
    let idx_upper = min (idx_lower + 1) (n - 1) in
    let weight = float_idx -. float_of_int idx_lower in

    (* Interpolate between sorted[idx_lower] and sorted[idx_upper] *)
    let v_lower = sorted.(idx_lower) in
    let v_upper = sorted.(idx_upper) in
    v_lower +. weight *. (v_upper -. v_lower)

(** Default correlation matrix for financial metrics

    Order: [NI, EBIT, CapEx, Depreciation, CA, CL]

    Empirical correlations (approximate):
    - NI ↔ EBIT: 0.90 (strong - both measure profitability)
    - NI ↔ CapEx: 0.60 (moderate - profitable firms invest more)
    - EBIT ↔ CapEx: 0.55 (moderate - operating leverage)
    - NI ↔ Depreciation: 0.35 (weak - different drivers)
    - EBIT ↔ Depreciation: 0.30 (weak)
    - CapEx ↔ Depreciation: 0.40 (moderate - capex today → depreciation tomorrow)
    - CA ↔ CL: 0.70 (strong - working capital management)
    - CA/CL ↔ others: 0.20-0.40 (weak to moderate)
*)
let default_correlation_matrix () =
  [|
    (*       NI    EBIT  CapEx  Depr   CA    CL   *)
    [| 1.00; 0.90; 0.60; 0.35; 0.30; 0.25 |];  (* NI *)
    [| 0.90; 1.00; 0.55; 0.30; 0.35; 0.30 |];  (* EBIT *)
    [| 0.60; 0.55; 1.00; 0.40; 0.40; 0.35 |];  (* CapEx *)
    [| 0.35; 0.30; 0.40; 1.00; 0.25; 0.20 |];  (* Depreciation *)
    [| 0.30; 0.35; 0.40; 0.25; 1.00; 0.70 |];  (* Current Assets *)
    [| 0.25; 0.30; 0.35; 0.20; 0.70; 1.00 |];  (* Current Liabilities *)
  |]

(** Sample correlated financial metrics using Gaussian copula *)
let sample_correlated_financials ~time_series ~correlation =
  (* Step 1: Sample from multivariate standard normal *)
  let normals = sample_multivariate_standard_normal ~correlation in

  (* Step 2: Transform to uniform [0, 1] *)
  let uniforms = normals_to_uniforms normals in

  (* Step 3: Transform to marginals via inverse CDF (percentile method) *)
  let ni = sample_from_percentile
    ~time_series:time_series.net_income
    ~percentile:uniforms.(0) in

  let ebit = sample_from_percentile
    ~time_series:time_series.ebit
    ~percentile:uniforms.(1) in

  let capex = abs_float (sample_from_percentile
    ~time_series:time_series.capex
    ~percentile:uniforms.(2)) in

  let depreciation = sample_from_percentile
    ~time_series:time_series.depreciation
    ~percentile:uniforms.(3) in

  let ca = sample_from_percentile
    ~time_series:time_series.current_assets
    ~percentile:uniforms.(4) in

  let cl = sample_from_percentile
    ~time_series:time_series.current_liabilities
    ~percentile:uniforms.(5) in

  (ni, ebit, capex, depreciation, ca, cl)

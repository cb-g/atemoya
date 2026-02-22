(** Copula module for modeling dependence between financial metrics *)

open Types

(** Copula type: Gaussian (thin tails) or Student-t (fat tails for tail dependence) *)
type copula_type =
  | Gaussian
  | StudentT of float  (* degrees of freedom, typically 3-10 for financial data *)

(** Configuration for copula-based sampling *)
type copula_config = {
  use_copula : bool;
  copula_type : copula_type;
  correlation_matrix : float array array;
}

(** Default copula configuration *)
let default_copula_config correlation_matrix = {
  use_copula = true;
  copula_type = Gaussian;
  correlation_matrix;
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

(** Student-t distribution functions for Student-t copula *)

(** Log-gamma function using Lanczos approximation
    Accurate to ~15 significant digits for x > 0 *)
let rec loggamma x =
  if x <= 0.0 then infinity
  else if x < 0.5 then
    (* Reflection formula: Γ(1-x)Γ(x) = π/sin(πx) *)
    let pi = acos (-1.0) in
    log (pi /. sin (pi *. x)) -. loggamma (1.0 -. x)
  else begin
    (* Lanczos approximation with g=7 *)
    let g = 7.0 in
    let c = [|
      0.99999999999980993;
      676.5203681218851;
      -1259.1392167224028;
      771.32342877765313;
      -176.61502916214059;
      12.507343278686905;
      -0.13857109526572012;
      9.9843695780195716e-6;
      1.5056327351493116e-7;
    |] in
    let x = x -. 1.0 in
    let sum = ref c.(0) in
    for i = 1 to 8 do
      sum := !sum +. c.(i) /. (x +. float_of_int i)
    done;
    let t = x +. g +. 0.5 in
    0.5 *. log (2.0 *. acos (-1.0)) +. (x +. 0.5) *. log t -. t +. log !sum
  end

(** Beta function using log-gamma for numerical stability
    B(a, b) = Γ(a)Γ(b) / Γ(a+b) *)
let log_beta a b =
  loggamma a +. loggamma b -. loggamma (a +. b)

(** Incomplete beta function ratio I_x(a, b) using continued fraction
    This is the regularized incomplete beta function *)
let incomplete_beta_ratio ~x ~a ~b =
  if x <= 0.0 then 0.0
  else if x >= 1.0 then 1.0
  else begin
    (* Use continued fraction expansion (Lentz's algorithm) *)
    let max_iter = 200 in
    let epsilon = 1e-10 in

    (* Use symmetry: I_x(a,b) = 1 - I_{1-x}(b,a) when x > (a+1)/(a+b+2) *)
    let (x, a, b, flip) =
      if x > (a +. 1.0) /. (a +. b +. 2.0) then
        (1.0 -. x, b, a, true)
      else
        (x, a, b, false)
    in

    (* Prefactor: x^a * (1-x)^b / (a * B(a,b)) *)
    let lbeta = log_beta a b in
    let front = exp (a *. log x +. b *. log (1.0 -. x) -. lbeta) /. a in

    (* Continued fraction coefficients *)
    let d_coef m =
      let m_f = float_of_int m in
      let num = m_f *. (b -. m_f) *. x /. ((a +. 2.0 *. m_f -. 1.0) *. (a +. 2.0 *. m_f)) in
      num
    in
    let e_coef m =
      let m_f = float_of_int m in
      let num = -.(a +. m_f) *. (a +. b +. m_f) *. x /.
                 ((a +. 2.0 *. m_f) *. (a +. 2.0 *. m_f +. 1.0)) in
      num
    in

    (* Modified Lentz's algorithm with proper early exit *)
    let tiny = 1e-30 in
    let f = ref 1.0 in
    let c = ref 1.0 in
    let d = ref 0.0 in
    let converged = ref false in
    let m = ref 1 in

    while !m <= max_iter && not !converged do
      (* d_m term *)
      let dm = d_coef !m in
      d := 1.0 +. dm *. !d;
      if abs_float !d < tiny then d := tiny;
      c := 1.0 +. dm /. !c;
      if abs_float !c < tiny then c := tiny;
      d := 1.0 /. !d;
      f := !f *. !c *. !d;

      (* e_m term *)
      let em = e_coef !m in
      d := 1.0 +. em *. !d;
      if abs_float !d < tiny then d := tiny;
      c := 1.0 +. em /. !c;
      if abs_float !c < tiny then c := tiny;
      d := 1.0 /. !d;
      let delta = !c *. !d in
      f := !f *. delta;

      (* Check convergence *)
      if abs_float (delta -. 1.0) < epsilon then
        converged := true;

      incr m
    done;

    let result = front *. !f in
    if flip then 1.0 -. result else result
  end

(** Student-t CDF
    F(t; ν) = 1 - 0.5 * I_{ν/(ν+t²)}(ν/2, 1/2)  for t >= 0
    F(t; ν) = 0.5 * I_{ν/(ν+t²)}(ν/2, 1/2)      for t < 0
*)
let student_t_cdf ~df t =
  if df <= 0.0 then 0.5  (* Invalid df, return median *)
  else begin
    let x = df /. (df +. t *. t) in
    let ibeta = incomplete_beta_ratio ~x ~a:(df /. 2.0) ~b:0.5 in
    if t >= 0.0 then
      1.0 -. 0.5 *. ibeta
    else
      0.5 *. ibeta
  end

(** Sample from chi-squared distribution with k degrees of freedom

    Chi-squared is a special case of Gamma: χ²(ν) ~ Gamma(ν/2, 2)

    For ν ≥ 1, we can use sum of squared normals for integer part.
    For ν < 1 (fractional df), we MUST use the Gamma distribution directly
    since sum-of-squares method doesn't work.
*)
let chi_squared_sample ~df =
  if df <= 0.0 then 0.0  (* Invalid: return 0 *)
  else if df < 1.0 then
    (* For df < 1: Use Gamma directly. χ²(ν) = Gamma(ν/2, 2) *)
    2.0 *. Sampling.gamma_sample ~shape:(df /. 2.0) ~scale:1.0
  else begin
    (* For df >= 1: Sum squared normals for integer part *)
    let k = int_of_float df in
    let sum = ref 0.0 in
    for _ = 1 to k do
      let z = Sampling.standard_normal_sample () in
      sum := !sum +. z *. z
    done;
    (* Handle fractional part if df is not integer *)
    let frac = df -. float_of_int k in
    if frac > 0.01 then
      (* Add Gamma(frac/2, 2) contribution for fractional part *)
      !sum +. 2.0 *. Sampling.gamma_sample ~shape:(frac /. 2.0) ~scale:1.0
    else
      !sum
  end

(** Sample from Student-t distribution with df degrees of freedom
    T = Z / sqrt(V/df) where Z ~ N(0,1) and V ~ χ²(df)
*)
let student_t_sample ~df =
  let z = Sampling.standard_normal_sample () in
  let v = chi_squared_sample ~df in
  z /. sqrt (v /. df)

(** Sample from multivariate Student-t with correlation matrix
    Using: T = Z / sqrt(V/df) where Z ~ MVN(0, Σ) and V ~ χ²(df)

    The key difference from Gaussian copula: all marginals are divided by
    the SAME chi-squared variable, which creates tail dependence.
    When V is small (extreme event), all variables move together.
*)
let sample_multivariate_student_t ~correlation ~df =
  let _n = Array.length correlation in

  (* Sample from multivariate standard normal *)
  let normals = sample_multivariate_standard_normal ~correlation in

  (* Sample single chi-squared (shared across all dimensions) *)
  let v = chi_squared_sample ~df in
  let scale = sqrt (v /. df) in

  (* Transform: t_i = z_i / sqrt(V/df) *)
  Array.map (fun z -> z /. scale) normals

(** Transform Student-t samples to uniform [0, 1] via Student-t CDF *)
let student_t_to_uniforms ~df samples =
  Array.map (fun t ->
    let u = student_t_cdf ~df t in
    (* Clamp to (epsilon, 1-epsilon) to avoid boundary issues *)
    let epsilon = 1e-10 in
    max epsilon (min (1.0 -. epsilon) u)
  ) samples

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

(** Sample correlated financial metrics with configurable copula type

    The copula type affects tail dependence:
    - Gaussian: No tail dependence (correlations break down in extremes)
    - StudentT(df): Symmetric tail dependence (extremes occur together)

    For financial modeling, Student-t with df=4-6 is often preferred
    as it captures the empirical observation that correlations spike
    during market crises ("correlations go to 1 in a crash").
*)
let sample_correlated_financials_with_copula ~time_series ~correlation ~copula_type =
  (* Step 1: Sample from multivariate distribution based on copula type *)
  let uniforms = match copula_type with
    | Gaussian ->
        (* Gaussian copula: sample MVN, transform via normal CDF *)
        let normals = sample_multivariate_standard_normal ~correlation in
        normals_to_uniforms normals
    | StudentT df ->
        (* Student-t copula: sample multivariate t, transform via t CDF *)
        let t_samples = sample_multivariate_student_t ~correlation ~df in
        student_t_to_uniforms ~df t_samples
  in

  (* Step 2: Transform to marginals via inverse CDF (percentile method) *)
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

(** Sample correlated financial metrics using Gaussian copula (default) *)
let sample_correlated_financials ~time_series ~correlation =
  sample_correlated_financials_with_copula
    ~time_series ~correlation ~copula_type:Gaussian

(** Compute tail dependence coefficient for Student-t copula

    λ = 2 * t_{ν+1}(-sqrt((ν+1)(1-ρ)/(1+ρ)))

    where:
    - ν is degrees of freedom
    - ρ is correlation coefficient
    - t_{ν+1} is Student-t CDF with ν+1 degrees of freedom

    For Gaussian copula, λ = 0 (no tail dependence).
    For Student-t, λ > 0 and increases as df decreases.
*)
let tail_dependence_coefficient ~copula_type ~correlation_coef =
  match copula_type with
  | Gaussian -> 0.0
  | StudentT df ->
      if abs_float correlation_coef >= 1.0 then 1.0
      else begin
        let rho = correlation_coef in
        let ratio = (df +. 1.0) *. (1.0 -. rho) /. (1.0 +. rho) in
        let arg = -. sqrt ratio in
        2.0 *. student_t_cdf ~df:(df +. 1.0) arg
      end

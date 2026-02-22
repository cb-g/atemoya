(* Cointegration testing for pairs trading *)

open Types

(** Statistics helpers **)

let mean arr =
  if Array.length arr = 0 then 0.0
  else
    let sum = Array.fold_left (+.) 0.0 arr in
    sum /. float_of_int (Array.length arr)

let std arr =
  if Array.length arr < 2 then 0.0
  else
    let mu = mean arr in
    let variance = Array.fold_left (fun acc x -> acc +. (x -. mu) ** 2.0) 0.0 arr
                   /. float_of_int (Array.length arr - 1) in
    sqrt variance

(** Linear regression **)

(* Ordinary Least Squares regression: Y = α + βX + ε
   Returns: (alpha, beta, residuals)
*)
let ols_regression ~x ~y =
  let n = min (Array.length x) (Array.length y) in
  if n < 2 then (0.0, 1.0, [||])
  else
    let x_arr = Array.sub x 0 n in
    let y_arr = Array.sub y 0 n in

    let x_mean = mean x_arr in
    let y_mean = mean y_arr in

    (* Calculate beta: β = Cov(X,Y) / Var(X) *)
    let numerator = ref 0.0 in
    let denominator = ref 0.0 in
    for i = 0 to n - 1 do
      let x_dev = x_arr.(i) -. x_mean in
      let y_dev = y_arr.(i) -. y_mean in
      numerator := !numerator +. (x_dev *. y_dev);
      denominator := !denominator +. (x_dev *. x_dev)
    done;

    let beta = if !denominator > 0.0 then !numerator /. !denominator else 1.0 in
    let alpha = y_mean -. beta *. x_mean in

    (* Calculate residuals *)
    let residuals = Array.init n (fun i ->
      y_arr.(i) -. (alpha +. beta *. x_arr.(i))
    ) in

    (alpha, beta, residuals)

(** Augmented Dickey-Fuller test with lag selection **)

(* ADF critical values (5% significance level) based on sample size
   Source: MacKinnon (1994) response surface coefficients
   These are for the case with constant, no trend *)
let adf_critical_value_5pct n =
  (* MacKinnon approximation: cv = β∞ + β₁/T + β₂/T²
     Note: t is sample size, used in the asymptotic formula *)
  let _t = float_of_int n in
  if n < 25 then -3.00
  else if n < 50 then -2.93
  else if n < 100 then -2.89
  else if n < 250 then -2.88
  else if n < 500 then -2.87
  else -2.86

(* Bayesian Information Criterion for lag selection *)
let bic ~n ~k ~rss =
  let n_f = float_of_int n in
  let k_f = float_of_int k in
  n_f *. log (rss /. n_f) +. k_f *. log n_f

(* Compute ADF regression with p lags:
   Δy_t = α + ρ·y_{t-1} + Σᵢ γᵢ·Δy_{t-i} + εₜ
   Returns: (rho, se_rho, rss) *)
let adf_regression ~series ~p =
  let n = Array.length series in
  let effective_n = n - p - 1 in

  if effective_n < 5 then (0.0, 1.0, infinity)
  else begin
    (* Build Δy series *)
    let delta_y = Array.init (n - 1) (fun i -> series.(i + 1) -. series.(i)) in

    (* Target: Δy_t for t = p+1 to n-1 *)
    let y_target = Array.sub delta_y p effective_n in

    (* Regressors: constant, y_{t-1}, Δy_{t-1}, ..., Δy_{t-p} *)
    let num_regressors = 2 + p in  (* constant + y_lag + p delta lags *)

    (* Build design matrix *)
    let x_data = Array.init effective_n (fun i ->
      let row = Array.make num_regressors 0.0 in
      row.(0) <- 1.0;  (* constant *)
      row.(1) <- series.(i + p);  (* y_{t-1} *)
      for j = 0 to p - 1 do
        row.(2 + j) <- delta_y.(i + p - 1 - j)  (* Δy_{t-1-j} *)
      done;
      row
    ) in

    (* Solve via normal equations using demeaned regression for rho *)
    (* First compute means *)
    let sum_y = ref 0.0 in
    let sum_ylag = ref 0.0 in
    for i = 0 to effective_n - 1 do
      sum_y := !sum_y +. y_target.(i);
      sum_ylag := !sum_ylag +. x_data.(i).(1)
    done;
    let mean_y = !sum_y /. float_of_int effective_n in
    let mean_ylag = !sum_ylag /. float_of_int effective_n in

    (* Compute variance and covariance for rho estimate *)
    let cov_xy = ref 0.0 in
    let var_x = ref 0.0 in
    for i = 0 to effective_n - 1 do
      let x_dev = x_data.(i).(1) -. mean_ylag in
      let y_dev = y_target.(i) -. mean_y in
      cov_xy := !cov_xy +. x_dev *. y_dev;
      var_x := !var_x +. x_dev *. x_dev
    done;

    if !var_x < 1e-12 then (0.0, 1.0, infinity)
    else begin
      let rho = !cov_xy /. !var_x in

      (* Compute residuals and RSS *)
      let rss = ref 0.0 in
      for i = 0 to effective_n - 1 do
        let y_hat = mean_y +. rho *. (x_data.(i).(1) -. mean_ylag) in
        let resid = y_target.(i) -. y_hat in
        rss := !rss +. resid *. resid
      done;

      (* Standard error of rho *)
      let sigma2 = !rss /. float_of_int (effective_n - num_regressors) in
      let se_rho = sqrt (sigma2 /. !var_x) in

      (rho, se_rho, !rss)
    end
  end

(* Test if series is stationary using ADF with automatic lag selection
   H0: Unit root (non-stationary)
   H1: Stationary
   Returns: (test_statistic, critical_value_5pct)
*)
let adf_test series =
  let n = Array.length series in
  if n < 10 then (0.0, -3.00)  (* Not enough data *)
  else begin
    (* Determine maximum lag order using Schwert's rule:
       p_max = floor(12 * (T/100)^{1/4}) *)
    let p_max = min 12 (int_of_float (12.0 *. ((float_of_int n /. 100.0) ** 0.25))) in
    let p_max = max 1 p_max in

    (* Select optimal lag using BIC *)
    let best_p = ref 0 in
    let best_bic = ref infinity in

    for p = 0 to p_max do
      let (_, _, rss) = adf_regression ~series ~p in
      let effective_n = n - p - 1 in
      let k = 2 + p in  (* constant + rho + p lag coefficients *)

      if rss < infinity && effective_n > k then begin
        let bic_val = bic ~n:effective_n ~k ~rss in
        if bic_val < !best_bic then begin
          best_bic := bic_val;
          best_p := p
        end
      end
    done;

    (* Run ADF with optimal lag *)
    let (rho, se_rho, _) = adf_regression ~series ~p:!best_p in

    (* Test statistic: t = ρ / SE(ρ) *)
    let t_stat = if se_rho > 0.0 then rho /. se_rho else 0.0 in

    (* Get critical value based on sample size *)
    let critical_value = adf_critical_value_5pct n in

    (t_stat, critical_value)
  end

(** Cointegration test **)

(* Test if two price series are cointegrated using Engle-Granger method *)
let test_cointegration ~prices1 ~prices2 =
  (* Step 1: Run cointegrating regression Y ~ X *)
  let (alpha, beta, residuals) = ols_regression ~x:prices1 ~y:prices2 in

  (* Step 2: Test if residuals are stationary (ADF test) *)
  let (adf_stat, critical_val) = adf_test residuals in

  (* If ADF statistic < critical value, reject H0 (unit root) => stationary => cointegrated *)
  let is_cointegrated = adf_stat < critical_val in

  {
    is_cointegrated;
    hedge_ratio = beta;
    alpha;
    adf_statistic = adf_stat;
    critical_value = critical_val;
    p_value = None;  (* Would need interpolation table *)
    method_name = "Engle-Granger (OLS)";
  }

(** Spread calculation **)

(* Calculate spread: spread_t = Y_t - β*X_t - α *)
let calculate_spread ~prices1 ~prices2 ~hedge_ratio ~alpha =
  let n = min (Array.length prices1) (Array.length prices2) in
  Array.init n (fun i ->
    prices2.(i) -. (hedge_ratio *. prices1.(i)) -. alpha
  )

(* Calculate spread using cointegration result *)
let spread_from_cointegration ~prices1 ~prices2 ~coint_result =
  calculate_spread
    ~prices1
    ~prices2
    ~hedge_ratio:coint_result.hedge_ratio
    ~alpha:coint_result.alpha

(** Total Least Squares regression **)

(* TLS regression: Y = α + βX + ε
   Minimizes perpendicular distance (symmetric — TLS(X,Y) consistent with TLS(Y,X))
   Uses analytical 2×2 eigenvalue decomposition.

   For centered data [x̃, ỹ], form the 2×2 matrix:
     S = [[Σx̃², Σx̃ỹ], [Σx̃ỹ, Σỹ²]]
   The TLS slope comes from the eigenvector of the smallest eigenvalue.
   For eigenvector [a, b]: β = -a/b
*)
let tls_regression ~x ~y =
  let n = min (Array.length x) (Array.length y) in
  if n < 2 then (0.0, 1.0, [||])
  else
    let x_arr = Array.sub x 0 n in
    let y_arr = Array.sub y 0 n in

    let x_mean = mean x_arr in
    let y_mean = mean y_arr in

    (* Compute 2×2 scatter matrix elements *)
    let sxx = ref 0.0 in
    let sxy = ref 0.0 in
    let syy = ref 0.0 in
    for i = 0 to n - 1 do
      let xd = x_arr.(i) -. x_mean in
      let yd = y_arr.(i) -. y_mean in
      sxx := !sxx +. xd *. xd;
      sxy := !sxy +. xd *. yd;
      syy := !syy +. yd *. yd
    done;

    (* Eigenvalues of [[sxx, sxy], [sxy, syy]]:
       λ = (tr ± √(tr² - 4·det)) / 2
       where tr = sxx + syy, det = sxx·syy - sxy² *)
    let tr = !sxx +. !syy in
    let det = !sxx *. !syy -. !sxy *. !sxy in
    let disc = tr *. tr -. 4.0 *. det in
    let disc = if disc < 0.0 then 0.0 else disc in (* numerical guard *)

    let lambda_min = (tr -. sqrt disc) /. 2.0 in

    (* Eigenvector for λ_min: (S - λI)v = 0
       [sxx - λ, sxy] [a]   [0]
       [sxy, syy - λ] [b] = [0]
       From first row: a·(sxx - λ) + b·sxy = 0
       → a/b = -sxy/(sxx - λ)
       → β = -a/b = sxy/(sxx - λ) *)
    let denom = !sxx -. lambda_min in
    let beta =
      if abs_float denom > 1e-12 then !sxy /. denom
      else if abs_float !sxy > 1e-12 then
        (* Use second row: a·sxy + b·(syy - λ) = 0 → β = (syy - λ)/sxy *)
        (!syy -. lambda_min) /. !sxy
      else 1.0  (* degenerate *)
    in

    let alpha = y_mean -. beta *. x_mean in

    let residuals = Array.init n (fun i ->
      y_arr.(i) -. (alpha +. beta *. x_arr.(i))
    ) in

    (alpha, beta, residuals)

(* Test cointegration using TLS + Engle-Granger *)
let test_cointegration_tls ~prices1 ~prices2 =
  let (alpha, beta, residuals) = tls_regression ~x:prices1 ~y:prices2 in
  let (adf_stat, critical_val) = adf_test residuals in
  let is_cointegrated = adf_stat < critical_val in
  {
    is_cointegrated;
    hedge_ratio = beta;
    alpha;
    adf_statistic = adf_stat;
    critical_value = critical_val;
    p_value = None;
    method_name = "Engle-Granger (TLS)";
  }

(** Johansen cointegration test for 2 variables **)

(* 2×2 matrix helpers *)

(* Invert 2×2 matrix [[a,b],[c,d]] = (1/det)·[[d,-b],[-c,a]] *)
let inv2x2 a b c d =
  let det = a *. d -. b *. c in
  if abs_float det < 1e-15 then None
  else
    let inv_det = 1.0 /. det in
    Some (d *. inv_det, -.b *. inv_det, -.c *. inv_det, a *. inv_det)

(* Multiply 2×2 matrices: C = A·B *)
let mul2x2 a11 a12 a21 a22 b11 b12 b21 b22 =
  (a11 *. b11 +. a12 *. b21,
   a11 *. b12 +. a12 *. b22,
   a21 *. b11 +. a22 *. b21,
   a21 *. b12 +. a22 *. b22)

(* Eigenvalues of 2×2 matrix, sorted descending *)
let eigenvalues_2x2 a b c d =
  let tr = a +. d in
  let det = a *. d -. b *. c in
  let disc = tr *. tr -. 4.0 *. det in
  let disc = if disc < 0.0 then 0.0 else disc in
  let sq = sqrt disc in
  let l1 = (tr +. sq) /. 2.0 in
  let l2 = (tr -. sq) /. 2.0 in
  (l1, l2)

(* Eigenvector for eigenvalue λ of [[a,b],[c,d]]:
   (a-λ)v1 + b·v2 = 0 → v = [b, λ-a] or [λ-d, c] *)
let eigenvector_2x2 a b _c d lam =
  let v1 = b in
  let v2 = lam -. a in
  let norm = sqrt (v1 *. v1 +. v2 *. v2) in
  if norm < 1e-15 then
    let v1 = lam -. d in
    let v2 = _c in
    let norm = sqrt (v1 *. v1 +. v2 *. v2) in
    if norm < 1e-15 then (1.0, 0.0)
    else (v1 /. norm, v2 /. norm)
  else
    (v1 /. norm, v2 /. norm)

(* Johansen trace test for 2 variables
   Uses VECM with 1 lag:
   ΔZ_t = Π·Z_{t-1} + μ + ε_t

   Procedure:
   1. Form ΔZ and Z_{t-1}
   2. Demean both (regress on constant)
   3. Compute moment matrices S00, S01, S10, S11
   4. Solve generalized eigenvalue problem
   5. Trace statistic = -T·Σ ln(1-λᵢ)

   Johansen critical values (2 variables, 5% significance):
   - r=0: trace critical = 15.41
   - r≤1: trace critical = 3.76
*)
let johansen_test ~prices1 ~prices2 =
  let n = min (Array.length prices1) (Array.length prices2) in
  if n < 20 then
    { is_cointegrated = false; hedge_ratio = 1.0; alpha = 0.0;
      adf_statistic = 0.0; critical_value = 15.41; p_value = None;
      method_name = "Johansen" }
  else
    let t = n - 1 in  (* effective sample size *)

    (* ΔZ_t = Z_t - Z_{t-1} for each variable *)
    let dz1 = Array.init t (fun i -> prices1.(i + 1) -. prices1.(i)) in
    let dz2 = Array.init t (fun i -> prices2.(i + 1) -. prices2.(i)) in

    (* Z_{t-1} (lagged levels) *)
    let z1_lag = Array.sub prices1 0 t in
    let z2_lag = Array.sub prices2 0 t in

    (* Demean all series (equivalent to regressing on constant) *)
    let mean_dz1 = mean dz1 in
    let mean_dz2 = mean dz2 in
    let mean_z1 = mean z1_lag in
    let mean_z2 = mean z2_lag in

    let r0_1 = Array.init t (fun i -> dz1.(i) -. mean_dz1) in
    let r0_2 = Array.init t (fun i -> dz2.(i) -. mean_dz2) in
    let r1_1 = Array.init t (fun i -> z1_lag.(i) -. mean_z1) in
    let r1_2 = Array.init t (fun i -> z2_lag.(i) -. mean_z2) in

    let tf = float_of_int t in

    (* Moment matrices Sij = (1/T) · Ri' · Rj *)
    (* S00: 2×2 from R0 *)
    let s00_11 = ref 0.0 in let s00_12 = ref 0.0 in
    let s00_22 = ref 0.0 in
    for i = 0 to t - 1 do
      s00_11 := !s00_11 +. r0_1.(i) *. r0_1.(i);
      s00_12 := !s00_12 +. r0_1.(i) *. r0_2.(i);
      s00_22 := !s00_22 +. r0_2.(i) *. r0_2.(i)
    done;
    let s00_11 = !s00_11 /. tf in let s00_12 = !s00_12 /. tf in
    let s00_22 = !s00_22 /. tf in

    (* S11: 2×2 from R1 *)
    let s11_11 = ref 0.0 in let s11_12 = ref 0.0 in
    let s11_22 = ref 0.0 in
    for i = 0 to t - 1 do
      s11_11 := !s11_11 +. r1_1.(i) *. r1_1.(i);
      s11_12 := !s11_12 +. r1_1.(i) *. r1_2.(i);
      s11_22 := !s11_22 +. r1_2.(i) *. r1_2.(i)
    done;
    let s11_11 = !s11_11 /. tf in let s11_12 = !s11_12 /. tf in
    let s11_22 = !s11_22 /. tf in

    (* S01: 2×2 from R0' · R1 *)
    let s01_11 = ref 0.0 in let s01_12 = ref 0.0 in
    let s01_21 = ref 0.0 in let s01_22 = ref 0.0 in
    for i = 0 to t - 1 do
      s01_11 := !s01_11 +. r0_1.(i) *. r1_1.(i);
      s01_12 := !s01_12 +. r0_1.(i) *. r1_2.(i);
      s01_21 := !s01_21 +. r0_2.(i) *. r1_1.(i);
      s01_22 := !s01_22 +. r0_2.(i) *. r1_2.(i)
    done;
    let s01_11 = !s01_11 /. tf in let s01_12 = !s01_12 /. tf in
    let s01_21 = !s01_21 /. tf in let s01_22 = !s01_22 /. tf in

    (* S10 = S01' *)
    let s10_11 = s01_11 in let s10_12 = s01_21 in
    let s10_21 = s01_12 in let s10_22 = s01_22 in

    (* Solve: eigenvalues of S11⁻¹·S10·S00⁻¹·S01 *)
    match inv2x2 s00_11 s00_12 s00_12 s00_22 with
    | None ->
      { is_cointegrated = false; hedge_ratio = 1.0; alpha = 0.0;
        adf_statistic = 0.0; critical_value = 15.41; p_value = None;
        method_name = "Johansen" }
    | Some (s00i_11, s00i_12, s00i_21, s00i_22) ->
      match inv2x2 s11_11 s11_12 s11_12 s11_22 with
      | None ->
        { is_cointegrated = false; hedge_ratio = 1.0; alpha = 0.0;
          adf_statistic = 0.0; critical_value = 15.41; p_value = None;
          method_name = "Johansen" }
      | Some (s11i_11, s11i_12, s11i_21, s11i_22) ->
        (* M = S11⁻¹ · S10 · S00⁻¹ · S01 *)
        let (tmp_11, tmp_12, tmp_21, tmp_22) =
          mul2x2 s00i_11 s00i_12 s00i_21 s00i_22
                 s01_11 s01_12 s01_21 s01_22 in
        let (tmp2_11, tmp2_12, tmp2_21, tmp2_22) =
          mul2x2 s10_11 s10_12 s10_21 s10_22
                 tmp_11 tmp_12 tmp_21 tmp_22 in
        let (m_11, m_12, m_21, m_22) =
          mul2x2 s11i_11 s11i_12 s11i_21 s11i_22
                 tmp2_11 tmp2_12 tmp2_21 tmp2_22 in

        let (lambda1, lambda2) = eigenvalues_2x2 m_11 m_12 m_21 m_22 in

        (* Clamp eigenvalues to [0, 1) for log *)
        let clamp_lambda l =
          if l < 0.0 then 0.0
          else if l >= 1.0 then 0.999
          else l
        in
        let l1 = clamp_lambda lambda1 in
        let l2 = clamp_lambda lambda2 in

        (* Trace statistic for r=0: -T·(ln(1-λ₁) + ln(1-λ₂)) *)
        let trace_r0 = -.tf *. (log (1.0 -. l1) +. log (1.0 -. l2)) in
        let trace_critical_r0 = 15.41 in

        let is_cointegrated = trace_r0 > trace_critical_r0 in

        (* Extract cointegrating vector from eigenvector of largest eigenvalue *)
        let (v1, v2) = eigenvector_2x2 m_11 m_12 m_21 m_22 lambda1 in

        (* Normalize: [1, -β] so hedge_ratio = -v2/v1 *)
        let hedge_ratio =
          if abs_float v1 > 1e-12 then -.v2 /. v1
          else 1.0
        in

        (* Compute alpha from means *)
        let alpha = (mean prices2) -. hedge_ratio *. (mean prices1) in

        {
          is_cointegrated;
          hedge_ratio;
          alpha;
          adf_statistic = trace_r0;
          critical_value = trace_critical_r0;
          p_value = None;
          method_name = "Johansen";
        }

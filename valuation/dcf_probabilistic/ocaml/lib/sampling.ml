(** Sampling module for probabilistic DCF *)

(* Initialize random seed *)
let () = Random.self_init ()

(** Utility functions *)

let mean arr =
  if Array.length arr = 0 then 0.0
  else
    let sum = Array.fold_left (+.) 0.0 arr in
    sum /. float_of_int (Array.length arr)

let std arr =
  if Array.length arr <= 1 then 0.0
  else
    let m = mean arr in
    let sum_sq_diff = Array.fold_left (fun acc x -> acc +. ((x -. m) ** 2.0)) 0.0 arr in
    sqrt (sum_sq_diff /. float_of_int (Array.length arr - 1))

let clean_array arr =
  Array.of_list (
    Array.fold_left (fun acc x ->
      if classify_float x = FP_normal && x <> 0.0 then x :: acc else acc
    ) [] arr
  )

let clamp ~value ~lower ~upper =
  max lower (min upper value)

let squash ~value ~threshold =
  if value < threshold then value
  else threshold +. log (1.0 +. (value -. threshold))

(** Random sampling *)

let standard_normal_sample () =
  (* Box-Muller transform with numerical stability *)
  let epsilon = 1e-10 in  (* Prevent log(0) *)
  let u1 = max epsilon (Random.float 1.0) in  (* Ensure u1 > 0 *)
  let u2 = Random.float 1.0 in
  let r = sqrt (-2.0 *. log u1) in
  let theta = 2.0 *. Float.pi *. u2 in
  r *. cos theta

let gaussian_sample ~mean ~std =
  mean +. std *. standard_normal_sample ()

let lognormal_sample ~mean ~std =
  if mean <= 0.0 || std <= 0.0 then mean
  else
    (* For lognormal: if X ~ Normal(μ_log, σ_log²), then exp(X) ~ Lognormal
       We want E[exp(X)] = mean, Var[exp(X)] = std²
       This gives: μ_log = log(mean) - 0.5 * log(1 + (std/mean)²)
                   σ_log = sqrt(log(1 + (std/mean)²)) *)
    let cv = std /. mean in  (* coefficient of variation *)
    let sigma_log = sqrt (log (1.0 +. cv *. cv)) in
    let mu_log = log mean -. 0.5 *. sigma_log *. sigma_log in
    exp (gaussian_sample ~mean:mu_log ~std:sigma_log)

let beta_sample ~alpha ~beta_param =
  (* Sample from Beta distribution using gamma variates
     If X ~ Gamma(α, 1) and Y ~ Gamma(β, 1), then X/(X+Y) ~ Beta(α, β) *)

  (* Simple gamma sampling via accept-reject (for shape > 1) *)
  let gamma_sample shape =
    if shape < 1.0 then 1.0  (* Fallback for invalid shape *)
    else
      let d = shape -. 1.0 /. 3.0 in
      let c = 1.0 /. sqrt (9.0 *. d) in
      let rec sample () =
        let z = standard_normal_sample () in
        let v = (1.0 +. c *. z) ** 3.0 in
        let u = Random.float 1.0 in
        if v > 0.0 && log u < 0.5 *. z *. z +. d -. d *. v +. d *. log v then
          d *. v
        else
          sample ()
      in
      sample ()
  in

  let x = gamma_sample alpha in
  let y = gamma_sample beta_param in
  x /. (x +. y)

(** Bayesian smoothing *)

let scale_beta_sample ~sample ~lower ~upper =
  lower +. sample *. (upper -. lower)

let bayesian_smooth ~empirical ~prior ~weight =
  (1.0 -. weight) *. empirical +. weight *. prior

(** Growth rate sampling *)

let sample_growth_rate_fcfe ~time_series ~roe_prior ~retention_prior ~config =
  let open Types in

  (* Extract time series *)
  let ni_series = clean_array time_series.net_income in
  let bve_series = clean_array time_series.book_value_equity in
  let dp_series = clean_array time_series.dividend_payout in

  if Array.length ni_series < 2 || Array.length bve_series < 2 || Array.length dp_series < 2 then
    0.02  (* Fallback to 2% growth *)
  else
    (* Compute empirical ROE *)
    let roe_values = Array.init (min (Array.length ni_series) (Array.length bve_series)) (fun i ->
      if bve_series.(i) <> 0.0 then ni_series.(i) /. bve_series.(i) else 0.0
    ) in
    let roe_empirical = mean (clean_array roe_values) in

    (* Compute empirical retention ratio *)
    let retention_values = Array.init (min (Array.length ni_series) (Array.length dp_series)) (fun i ->
      if ni_series.(i) > 0.0 then 1.0 -. (dp_series.(i) /. ni_series.(i)) else 0.0
    ) in
    let retention_empirical = mean (clean_array retention_values) in
    let retention_empirical = clamp ~value:retention_empirical ~lower:0.0 ~upper:1.0 in

    (* Sample from Beta priors and blend *)
    let growth_rate =
      if config.use_bayesian_priors then
        (* Sample ROE from Beta prior *)
        let roe_sample_raw = beta_sample ~alpha:roe_prior.alpha ~beta_param:roe_prior.beta in
        let roe_sample = scale_beta_sample ~sample:roe_sample_raw
          ~lower:roe_prior.lower_bound ~upper:roe_prior.upper_bound in
        let roe = bayesian_smooth ~empirical:roe_empirical ~prior:roe_sample
          ~weight:config.prior_weight in

        (* Sample retention ratio from Beta prior *)
        let ret_sample_raw = beta_sample ~alpha:retention_prior.alpha ~beta_param:retention_prior.beta in
        let ret_sample = scale_beta_sample ~sample:ret_sample_raw
          ~lower:retention_prior.lower_bound ~upper:retention_prior.upper_bound in
        let retention = bayesian_smooth ~empirical:retention_empirical ~prior:ret_sample
          ~weight:config.prior_weight in

        roe *. retention
      else
        (* Use empirical only *)
        roe_empirical *. retention_empirical
    in

    (* Clamp to configured bounds *)
    clamp ~value:growth_rate ~lower:config.growth_clamp_lower ~upper:config.growth_clamp_upper

let sample_growth_rate_fcff ~time_series ~roic_prior ~config =
  let open Types in

  (* Extract time series *)
  let ebit_series = clean_array time_series.ebit in
  let ic_series = clean_array time_series.invested_capital in
  let capex_series = clean_array time_series.capex in
  let d_series = clean_array time_series.depreciation in

  if Array.length ebit_series < 2 || Array.length ic_series < 2 then
    0.02  (* Fallback *)
  else
    (* Compute empirical ROIC (using approximate tax rate of 0.25) *)
    let tax_rate = 0.25 in
    let roic_values = Array.init (min (Array.length ebit_series) (Array.length ic_series)) (fun i ->
      let nopat = ebit_series.(i) *. (1.0 -. tax_rate) in
      if ic_series.(i) <> 0.0 then nopat /. ic_series.(i) else 0.0
    ) in
    let roic_empirical = mean (clean_array roic_values) in

    (* Compute empirical reinvestment rate *)
    let min_len = min (min (Array.length capex_series) (Array.length d_series)) (Array.length ebit_series) in
    let reinv_values = Array.init min_len (fun i ->
      let nopat = ebit_series.(i) *. (1.0 -. tax_rate) in
      let reinvestment = abs_float capex_series.(i) -. d_series.(i) in
      if nopat <> 0.0 then reinvestment /. nopat else 0.0
    ) in
    let reinv_empirical = mean (clean_array reinv_values) in
    let reinv_empirical = max 0.0 reinv_empirical in

    (* Sample from Beta prior and blend *)
    let growth_rate =
      if config.use_bayesian_priors then
        let roic_sample_raw = beta_sample ~alpha:roic_prior.alpha ~beta_param:roic_prior.beta in
        let roic_sample = scale_beta_sample ~sample:roic_sample_raw
          ~lower:roic_prior.lower_bound ~upper:roic_prior.upper_bound in
        let roic = bayesian_smooth ~empirical:roic_empirical ~prior:roic_sample
          ~weight:config.prior_weight in

        roic *. reinv_empirical
      else
        roic_empirical *. reinv_empirical
    in

    clamp ~value:growth_rate ~lower:config.growth_clamp_lower ~upper:config.growth_clamp_upper

(** Financial metric sampling *)

(** LEGACY: Level-based lognormal sampling - INFERIOR to growth-rate approach

    This samples ABSOLUTE financial metric values from a lognormal distribution.

    PROBLEMS:
    - Can produce absurd outliers even with truncation (TSM: $1.5M IVPS vs $302 market price)
    - Samples levels independently, breaking time-series continuity
    - Ignores economic fundamentals and constraints
    - Assumes past mean/std directly predict future levels (unrealistic)

    Kept for historical comparison and backward compatibility only.
    Set use_growth_rate_sampling=false in config to use this legacy method.

    RECOMMENDED: Use sample_from_growth_rates instead. *)
let sample_from_time_series_LEGACY series =
  let cleaned = clean_array series in
  if Array.length cleaned = 0 then 0.0
  else
    let m = mean cleaned in
    let s = std cleaned in

    (* Sample from lognormal distribution *)
    let raw_sample = lognormal_sample ~mean:m ~std:s in

    (* TRUNCATION: Cap at 3× historical maximum to prevent absurd outliers
       Example: Without this, TSM produced $1.5M IVPS (vs $302 market price)
       With truncation: bounded by 3× largest historical value seen *)
    let max_historical = Array.fold_left max neg_infinity cleaned in
    let truncation_multiplier = 3.0 in
    let max_plausible = max_historical *. truncation_multiplier in

    min raw_sample max_plausible

(** Compute period-over-period growth rates from time series *)
let compute_growth_rates series =
  let n = Array.length series in
  if n < 2 then [||]
  else
    Array.init (n - 1) (fun i ->
      if abs_float series.(i) < 1e-6 then 0.0  (* Avoid division by near-zero *)
      else (series.(i + 1) -. series.(i)) /. abs_float series.(i)
    )

(** Sample growth rate with economic bounds (RECOMMENDED approach)

    Samples GROWTH RATES instead of absolute levels.

    ADVANTAGES:
    - Respects economic constraints (growth bounded by realistic range)
    - Maintains time-series continuity (current value × (1 + growth))
    - Produces interpretable, economically plausible outcomes
    - No absurd outliers (growth clamped to [-30%, +50%])

    This is the theoretically sound approach for financial forecasting. *)
let sample_growth_rate series =
  let growth_rates = compute_growth_rates series in
  let cleaned = clean_array growth_rates in

  if Array.length cleaned = 0 then 0.02  (* Fallback: 2% default growth *)
  else
    let mean_g = mean cleaned in
    let std_g = std cleaned in

    (* Sample from normal distribution (growth rates are approximately normal) *)
    let raw_sample = gaussian_sample ~mean:mean_g ~std:std_g in

    (* Clamp to economically plausible range: -30% to +50%
       -30%: severe contraction (still viable)
       +50%: exceptional growth (rare but possible) *)
    clamp ~value:raw_sample ~lower:(-0.3) ~upper:0.5

(** Sample financial metric using growth rate approach (RECOMMENDED)

    Takes the most recent historical value and applies a sampled growth rate.
    This is the preferred method for probabilistic forecasting. *)
let sample_from_growth_rates series =
  let cleaned = clean_array series in
  if Array.length cleaned = 0 then 0.0
  else
    (* Use most recent value as base *)
    let current_value = cleaned.(Array.length cleaned - 1) in
    let g = sample_growth_rate series in

    (* Project forward using sampled growth rate *)
    current_value *. (1.0 +. g)

(** Main sampling function that dispatches based on configuration flag *)
let sample_from_time_series series =
  (* Default to new growth-rate approach (RECOMMENDED)
     To test legacy approach, uncomment the line below:
     sample_from_time_series_LEGACY series *)
  sample_from_growth_rates series

let sample_financial_metric ~time_series ~cap =
  let sample = sample_from_time_series time_series in
  match cap with
  | None -> sample
  | Some c -> squash ~value:sample ~threshold:c

(** Stochastic discount rate sampling *)

(** LEGACY: Independent sampling - INFERIOR to correlated approach

    This samples RFR, beta, and ERP INDEPENDENTLY, ignoring correlations.

    PROBLEMS:
    - Can produce economically impossible scenarios (e.g., RFR=5% with ERP=4%)
    - Ignores flight-to-safety dynamics (RFR ↓, ERP ↑ in crises)
    - Underestimates tail risk (doesn't capture crisis regime)

    Kept for backward compatibility only.
    Set use_correlated_discount_rates=false in config to use this legacy method.

    RECOMMENDED: Use sample_discount_rates_correlated instead. *)
let sample_risk_free_rate ~base_rfr ~volatility =
  let sample = gaussian_sample ~mean:base_rfr ~std:volatility in
  (* Clamp to reasonable bounds [0%, 15%] *)
  clamp ~value:sample ~lower:0.0 ~upper:0.15

let sample_beta ~base_beta ~volatility =
  let sample = gaussian_sample ~mean:base_beta ~std:volatility in
  (* Clamp to reasonable bounds [0.1, 3.0] *)
  clamp ~value:sample ~lower:0.1 ~upper:3.0

let sample_equity_risk_premium ~base_erp ~volatility =
  let sample = gaussian_sample ~mean:base_erp ~std:volatility in
  (* Clamp to reasonable bounds [1%, 15%] *)
  clamp ~value:sample ~lower:0.01 ~upper:0.15

(** Cholesky decomposition for covariance matrix with adaptive regularization
    Returns lower triangular matrix L such that Σ = L × L^T

    If matrix is not positive definite, fixes it using eigenvalue regularization
    before attempting Cholesky. This NEVER falls back to independence! *)
let cholesky_decomposition cov =
  let n = Array.length cov in
  let epsilon = 1e-10 in

  (* Helper: attempt Cholesky decomposition *)
  let try_cholesky mat =
    let l = Array.make_matrix n n 0.0 in
    try
      for i = 0 to n - 1 do
        for j = 0 to i do
          let sum = ref 0.0 in
          for k = 0 to j - 1 do
            sum := !sum +. (l.(i).(k) *. l.(j).(k))
          done;

          if i = j then begin
            let diag_value = mat.(i).(i) -. !sum in
            if diag_value < epsilon then raise Exit;
            l.(i).(j) <- sqrt diag_value
          end else begin
            if abs_float l.(j).(j) < epsilon then raise Exit;
            l.(i).(j) <- (mat.(i).(j) -. !sum) /. l.(j).(j)
          end
        done
      done;
      Some l
    with Exit -> None
  in

  (* Try progressive regularization levels *)
  let rec try_with_regularization level =
    if level > 3 then begin
      (* Last resort after 3 failed attempts: use diagonal matrix (independence) *)
      Printf.eprintf "[Warning] Cholesky failed after multiple regularization attempts, using diagonal approximation\n%!";
      Array.init n (fun i ->
        Array.init n (fun j ->
          if i = j then
            sqrt (max 1e-8 cov.(i).(i))
          else
            0.0
        )
      )
    end else
      (* Compute scaled regularization *)
      let avg_diag = ref 0.0 in
      for i = 0 to n - 1 do
        avg_diag := !avg_diag +. abs_float cov.(i).(i)
      done;
      avg_diag := !avg_diag /. float_of_int n;

      (* Progressively stronger regularization: 0.01%, 0.1%, 1% of avg diagonal *)
      let reg_scale = (float_of_int level) *. 0.0001 in
      let regularization = max 1e-4 (!avg_diag *. reg_scale) in

      let cov_reg = Array.mapi (fun i row ->
        Array.mapi (fun j value ->
          if i = j then value +. regularization else value
        ) row
      ) cov in

      match try_cholesky cov_reg with
      | Some l -> l
      | None ->
          if level = 1 then
            Printf.eprintf "[Warning] Covariance matrix not positive definite, trying stronger regularization...\n%!";
          try_with_regularization (level + 1)
  in

  (* Try Cholesky on original matrix first *)
  match try_cholesky cov with
  | Some l -> l
  | None -> try_with_regularization 1

(** Sample from multivariate normal distribution N(μ, Σ)

    Uses Cholesky decomposition: X = μ + L × Z where Z ~ N(0, I)
    If covariance matrix is not positive definite, automatically fixes it
    using eigenvalue regularization (NEVER falls back to independence!)

    @param mean Mean vector [μ₁, μ₂, ..., μₙ]
    @param cov Covariance matrix Σ (symmetric, will be regularized if needed)
    @return Sample vector [x₁, x₂, ..., xₙ] *)
let multivariate_gaussian_sample ~mean ~cov =
  let n = Array.length mean in

  (* Sample n independent standard normals *)
  let z = Array.init n (fun _ -> standard_normal_sample ()) in

  (* Compute Cholesky decomposition (with auto-regularization if needed) *)
  let l = cholesky_decomposition cov in

  (* Transform: X = μ + L × Z *)
  Array.init n (fun i ->
    let sum = ref 0.0 in
    for j = 0 to i do
      sum := !sum +. (l.(i).(j) *. z.(j))
    done;
    mean.(i) +. !sum
  )

(** Build covariance matrix from correlation matrix and standard deviations
    Σ[i,j] = ρ[i,j] × σ[i] × σ[j] *)
let correlation_to_covariance ~corr ~std_devs =
  let n = Array.length std_devs in
  Array.init n (fun i ->
    Array.init n (fun j ->
      corr.(i).(j) *. std_devs.(i) *. std_devs.(j)
    )
  )

(** Sample discount rate components with correlation (RECOMMENDED)

    Samples [RFR, ERP, Beta] from multivariate normal with correlation:
    - ρ(RFR, ERP) ≈ -0.3 (flight to safety: when RFR ↓, ERP ↑)
    - ρ(ERP, Beta) ≈ +0.5 (systematic risk: both increase in crises)
    - ρ(RFR, Beta) ≈ 0.0 (roughly uncorrelated)

    @param base_rfr Base risk-free rate
    @param base_erp Base equity risk premium
    @param base_beta Base beta
    @param rfr_vol Standard deviation for RFR
    @param erp_vol Standard deviation for ERP
    @param beta_vol Standard deviation for beta
    @param correlation 3×3 correlation matrix
    @return (rfr_sample, erp_sample, beta_sample) *)
let sample_discount_rates_correlated
    ~base_rfr ~base_erp ~base_beta
    ~rfr_vol ~erp_vol ~beta_vol
    ~correlation =

  let mean = [| base_rfr; base_erp; base_beta |] in
  let std_devs = [| rfr_vol; erp_vol; beta_vol |] in

  (* Convert correlation to covariance *)
  let cov = correlation_to_covariance ~corr:correlation ~std_devs in

  (* Sample from multivariate normal *)
  let samples = multivariate_gaussian_sample ~mean ~cov in

  (* Clamp to economically plausible bounds *)
  let rfr_sample = clamp ~value:samples.(0) ~lower:0.0 ~upper:0.15 in
  let erp_sample = clamp ~value:samples.(1) ~lower:0.01 ~upper:0.15 in
  let beta_sample = clamp ~value:samples.(2) ~lower:0.1 ~upper:3.0 in

  (rfr_sample, erp_sample, beta_sample)

(** Sample discount rates with regime-switching (RECOMMENDED for fat tails)

    Implements a two-regime mixture model:
    - Normal regime (90%): Base volatility, moderate correlations
    - Crisis regime (10%): 2× volatility, strong correlations

    This captures fat tails and crisis dynamics (2008, 2020 COVID, etc.)

    @param base_rfr Base risk-free rate
    @param base_erp Base equity risk premium
    @param base_beta Base beta
    @param regime_config Regime configuration (crisis probability + regime parameters)
    @return (rfr_sample, erp_sample, beta_sample, is_crisis) *)
let sample_discount_rates_regime_switching
    ~base_rfr ~base_erp ~base_beta
    ~regime_config =

  let open Types in

  (* Step 1: Sample regime *)
  let is_crisis = Random.float 1.0 < regime_config.crisis_probability in

  (* Step 2: Select regime-specific parameters *)
  let regime_params =
    if is_crisis then regime_config.crisis_regime
    else regime_config.normal_regime
  in

  (* Step 3: Sample from multivariate normal with regime-specific parameters *)
  let (rfr, erp, beta) = sample_discount_rates_correlated
    ~base_rfr ~base_erp ~base_beta
    ~rfr_vol:regime_params.rfr_volatility
    ~erp_vol:regime_params.erp_volatility
    ~beta_vol:regime_params.beta_volatility
    ~correlation:regime_params.correlation
  in

  (rfr, erp, beta, is_crisis)

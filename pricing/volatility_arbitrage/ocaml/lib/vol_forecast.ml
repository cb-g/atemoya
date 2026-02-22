(* Volatility forecasting implementation *)

open Types

let trading_days_per_year = 252.0

(* Helper functions *)
let annualize_variance var =
  var *. trading_days_per_year

let variance_to_vol var =
  sqrt var

(* GARCH(1,1) multi-step forecast *)
let garch_forecast ~params ~current_variance ~horizon_days =
  let { omega; alpha; beta } = params in
  let persistence = alpha +. beta in

  (* Multi-step forecast: σ²_{t+h} = ω·(1-β^h)/(1-β) + (α+β)^h·σ²_t *)
  let h = float_of_int horizon_days in
  let beta_power_h = beta ** h in

  let unconditional_var =
    if abs_float (1.0 -. beta) < 1e-10 then omega
    else omega /. (1.0 -. beta)
  in

  let forecast_var =
    unconditional_var *. (1.0 -. beta_power_h) +.
    (persistence ** h) *. current_variance
  in

  let forecast_vol = variance_to_vol (annualize_variance forecast_var) in

  {
    timestamp = Unix.time ();
    forecast_type = GARCH params;
    forecast_vol;
    confidence_interval = None;  (* Computed separately *)
    horizon_days;
  }

(* GARCH(1,1) parameter estimation via Quasi-Maximum Likelihood (QMLE)
   Uses grid search with refinement for numerical stability.

   Model: σ²_t = ω + α·r²_{t-1} + β·σ²_{t-1}
   Log-likelihood: L = -0.5·Σ[log(σ²_t) + r²_t/σ²_t]

   Constraints:
   - ω > 0
   - α ≥ 0, β ≥ 0
   - α + β < 1 (stationarity)
*)
let estimate_garch_params ~returns =
  let n = Array.length returns in
  if n < 30 then
    (* Default parameters if insufficient data for reliable estimation *)
    { omega = 0.00001; alpha = 0.05; beta = 0.90 }
  else begin
    (* Demean returns *)
    let mean = Array.fold_left (+.) 0.0 returns /. float_of_int n in
    let centered = Array.map (fun r -> r -. mean) returns in

    (* Sample variance for initialization *)
    let sample_var = Array.fold_left (fun acc r -> acc +. r *. r) 0.0 centered
                     /. float_of_int n in

    (* Compute GARCH log-likelihood for given parameters *)
    let garch_log_likelihood ~omega ~alpha ~beta =
      if omega <= 0.0 || alpha < 0.0 || beta < 0.0 || alpha +. beta >= 1.0 then
        neg_infinity
      else begin
        (* Initialize variance with unconditional variance *)
        let uncond_var = omega /. (1.0 -. alpha -. beta) in
        let sigma2 = ref (max uncond_var sample_var) in
        let ll = ref 0.0 in

        for t = 1 to n - 1 do
          let r_prev = centered.(t - 1) in
          let r_curr = centered.(t) in

          (* Update variance: σ²_t = ω + α·r²_{t-1} + β·σ²_{t-1} *)
          sigma2 := omega +. alpha *. r_prev *. r_prev +. beta *. !sigma2;

          (* Enforce minimum variance for numerical stability *)
          sigma2 := max !sigma2 1e-10;

          (* Log-likelihood contribution: -0.5·[log(σ²) + r²/σ²] *)
          ll := !ll -. 0.5 *. (log !sigma2 +. r_curr *. r_curr /. !sigma2)
        done;

        !ll
      end
    in

    (* Grid search for initial parameter estimates *)
    let best_ll = ref neg_infinity in
    let best_alpha = ref 0.05 in
    let best_beta = ref 0.90 in

    (* Coarse grid search *)
    let alpha_grid = [| 0.02; 0.05; 0.08; 0.10; 0.15; 0.20 |] in
    let beta_grid = [| 0.70; 0.75; 0.80; 0.85; 0.90; 0.93 |] in

    Array.iter (fun a ->
      Array.iter (fun b ->
        if a +. b < 0.99 then begin
          let omega = sample_var *. (1.0 -. a -. b) in
          let ll = garch_log_likelihood ~omega ~alpha:a ~beta:b in
          if ll > !best_ll then begin
            best_ll := ll;
            best_alpha := a;
            best_beta := b
          end
        end
      ) beta_grid
    ) alpha_grid;

    (* Fine grid refinement around best estimate *)
    let refine_alpha = !best_alpha in
    let refine_beta = !best_beta in

    for i = -5 to 5 do
      for j = -5 to 5 do
        let a = refine_alpha +. float_of_int i *. 0.01 in
        let b = refine_beta +. float_of_int j *. 0.01 in
        if a > 0.0 && b > 0.0 && a +. b < 0.99 then begin
          let omega = sample_var *. (1.0 -. a -. b) in
          let ll = garch_log_likelihood ~omega ~alpha:a ~beta:b in
          if ll > !best_ll then begin
            best_ll := ll;
            best_alpha := a;
            best_beta := b
          end
        end
      done
    done;

    (* Validate and clamp final estimates *)
    let alpha = max 0.01 (min 0.30 !best_alpha) in
    let beta = max 0.50 (min 0.95 !best_beta) in

    (* Ensure stationarity *)
    let persistence = alpha +. beta in
    let (alpha, beta) =
      if persistence >= 0.99 then
        (* Scale down to ensure stationarity *)
        let scale = 0.98 /. persistence in
        (alpha *. scale, beta *. scale)
      else
        (alpha, beta)
    in

    let omega = sample_var *. (1.0 -. alpha -. beta) in

    { omega; alpha; beta }
  end

(* GARCH confidence interval (approximate) *)
let garch_confidence_interval ~params ~current_variance ~horizon_days =
  let forecast = garch_forecast ~params ~current_variance ~horizon_days in
  let forecast_vol = forecast.forecast_vol in

  (* Approximate 95% CI as ±1.96 * SE *)
  (* SE increases with horizon: SE ≈ σ·√(h/252) *)
  let h = float_of_int horizon_days in
  let se = forecast_vol *. sqrt (h /. trading_days_per_year) in

  let lower = max 0.0 (forecast_vol -. 1.96 *. se) in
  let upper = forecast_vol +. 1.96 *. se in

  (lower, upper)

(* EWMA variance computation *)
let ewma_variance ~returns ~lambda =
  let n = Array.length returns in
  if n = 0 then 0.0
  else if n = 1 then returns.(0) *. returns.(0)
  else begin
    (* Initialize with first squared return *)
    let var = ref (returns.(0) *. returns.(0)) in

    (* Update recursively: σ²_t = λ·σ²_{t-1} + (1-λ)·r²_{t-1} *)
    for i = 1 to n - 1 do
      let r_sq = returns.(i) *. returns.(i) in
      var := lambda *. !var +. (1.0 -. lambda) *. r_sq
    done;

    !var
  end

(* EWMA forecast *)
let ewma_forecast ~returns ~lambda ~horizon_days =
  let current_var = ewma_variance ~returns ~lambda in

  (* EWMA forecast is constant: σ²_{t+h} = σ²_t for all h *)
  (* (This is a property of EWMA - no mean reversion) *)
  let forecast_vol = variance_to_vol (annualize_variance current_var) in

  {
    timestamp = Unix.time ();
    forecast_type = EWMA { lambda };
    forecast_vol;
    confidence_interval = None;
    horizon_days;
  }

(* HAR parameter estimation via OLS *)
let estimate_har_params ~realized_vols =
  let n = Array.length realized_vols in
  if n < 30 then
    (* Default parameters if insufficient data *)
    (0.0, 0.3, 0.4, 0.3)
  else begin
    (* Extract volatilities *)
    let vols = Array.map (fun rv -> rv.volatility) realized_vols in

    (* Compute RV components: daily, weekly (5d avg), monthly (21d avg) *)
    let rv_daily = Array.sub vols 21 (n - 21) in  (* Skip first 21 for lags *)

    let rv_weekly = Array.init (n - 21) (fun i ->
      let sum = ref 0.0 in
      for j = 0 to 4 do
        sum := !sum +. vols.(i + 21 - 1 - j)
      done;
      !sum /. 5.0
    ) in

    let rv_monthly = Array.init (n - 21) (fun i ->
      let sum = ref 0.0 in
      for j = 0 to 20 do
        sum := !sum +. vols.(i + 21 - 1 - j)
      done;
      !sum /. 21.0
    ) in

    (* Target: RV_t (one day ahead) *)
    let y = Array.sub vols 22 (n - 22) in
    let m = Array.length y in

    if m < 5 then
      (* Not enough data points for regression *)
      (0.0, 0.3, 0.4, 0.3)
    else begin
      (* Design matrix X: [1, RV_d, RV_w, RV_m] *)
      (* Use OLS with normal equations: β = (X'X)^(-1) X'y *)

      (* Compute X'X and X'y components *)
      let sum_1 = float_of_int m in
      let sum_d = ref 0.0 in
      let sum_w = ref 0.0 in
      let sum_m = ref 0.0 in
      let sum_d2 = ref 0.0 in
      let sum_w2 = ref 0.0 in
      let sum_m2 = ref 0.0 in
      let sum_dw = ref 0.0 in
      let sum_dm = ref 0.0 in
      let sum_wm = ref 0.0 in
      let sum_y = ref 0.0 in
      let sum_yd = ref 0.0 in
      let sum_yw = ref 0.0 in
      let sum_ym = ref 0.0 in

      for i = 0 to m - 1 do
        let d = rv_daily.(i) in
        let w = rv_weekly.(i) in
        let mn = rv_monthly.(i) in
        let yi = y.(i) in

        sum_d := !sum_d +. d;
        sum_w := !sum_w +. w;
        sum_m := !sum_m +. mn;
        sum_d2 := !sum_d2 +. d *. d;
        sum_w2 := !sum_w2 +. w *. w;
        sum_m2 := !sum_m2 +. mn *. mn;
        sum_dw := !sum_dw +. d *. w;
        sum_dm := !sum_dm +. d *. mn;
        sum_wm := !sum_wm +. w *. mn;
        sum_y := !sum_y +. yi;
        sum_yd := !sum_yd +. yi *. d;
        sum_yw := !sum_yw +. yi *. w;
        sum_ym := !sum_ym +. yi *. mn
      done;

      (* Solve 4x4 linear system using Cramer's rule for numerical stability.
         X'X β = X'y where X'X is:
         | n      Σd     Σw     Σm   |   | β₀ |   | Σy  |
         | Σd     Σd²    Σdw    Σdm  | × | βd | = | Σyd |
         | Σw     Σdw    Σw²    Σwm  |   | βw |   | Σyw |
         | Σm     Σdm    Σwm    Σm²  |   | βm |   | Σym |

         We use a simplified approach: solve demeaned regression first,
         then compute intercept. This avoids 4x4 matrix inversion issues. *)

      let mean_y = !sum_y /. sum_1 in
      let mean_d = !sum_d /. sum_1 in
      let mean_w = !sum_w /. sum_1 in
      let mean_m = !sum_m /. sum_1 in

      (* Centered sums of squares and cross-products *)
      let var_d = !sum_d2 -. sum_1 *. mean_d *. mean_d in
      let var_w = !sum_w2 -. sum_1 *. mean_w *. mean_w in
      let var_m = !sum_m2 -. sum_1 *. mean_m *. mean_m in
      let cov_dw = !sum_dw -. sum_1 *. mean_d *. mean_w in
      let cov_dm = !sum_dm -. sum_1 *. mean_d *. mean_m in
      let cov_wm = !sum_wm -. sum_1 *. mean_w *. mean_m in
      let cov_yd = !sum_yd -. sum_1 *. mean_y *. mean_d in
      let cov_yw = !sum_yw -. sum_1 *. mean_y *. mean_w in
      let cov_ym = !sum_ym -. sum_1 *. mean_y *. mean_m in

      (* Solve 3x3 system for centered regression using Cramer's rule:
         | var_d   cov_dw  cov_dm |   | βd |   | cov_yd |
         | cov_dw  var_w   cov_wm | × | βw | = | cov_yw |
         | cov_dm  cov_wm  var_m  |   | βm |   | cov_ym | *)

      (* Determinant of 3x3 matrix *)
      let det_a =
        var_d *. (var_w *. var_m -. cov_wm *. cov_wm)
        -. cov_dw *. (cov_dw *. var_m -. cov_wm *. cov_dm)
        +. cov_dm *. (cov_dw *. cov_wm -. var_w *. cov_dm)
      in

      if abs_float det_a < 1e-12 then
        (* Near-singular matrix: fall back to defaults *)
        (0.0, 0.3, 0.4, 0.3)
      else begin
        (* Cramer's rule for each coefficient *)
        let det_d =
          cov_yd *. (var_w *. var_m -. cov_wm *. cov_wm)
          -. cov_dw *. (cov_yw *. var_m -. cov_wm *. cov_ym)
          +. cov_dm *. (cov_yw *. cov_wm -. var_w *. cov_ym)
        in
        let det_w =
          var_d *. (cov_yw *. var_m -. cov_wm *. cov_ym)
          -. cov_yd *. (cov_dw *. var_m -. cov_wm *. cov_dm)
          +. cov_dm *. (cov_dw *. cov_ym -. cov_yw *. cov_dm)
        in
        let det_m =
          var_d *. (var_w *. cov_ym -. cov_yw *. cov_wm)
          -. cov_dw *. (cov_dw *. cov_ym -. cov_yw *. cov_dm)
          +. cov_yd *. (cov_dw *. cov_wm -. var_w *. cov_dm)
        in

        let beta_d = det_d /. det_a in
        let beta_w = det_w /. det_a in
        let beta_m = det_m /. det_a in

        (* Clamp coefficients to reasonable range [0, 1] for stability *)
        let clamp v = max 0.0 (min 1.0 v) in
        let beta_d = clamp beta_d in
        let beta_w = clamp beta_w in
        let beta_m = clamp beta_m in

        (* Compute intercept from means *)
        let beta_0 = mean_y -. beta_d *. mean_d -. beta_w *. mean_w -. beta_m *. mean_m in

        (beta_0, beta_d, beta_w, beta_m)
      end
    end
  end

(* HAR forecast *)
let har_forecast ~realized_vols ~horizon_days =
  let (beta_0, beta_d, beta_w, beta_m) = estimate_har_params ~realized_vols in

  let n = Array.length realized_vols in
  if n < 21 then
    (* Fallback to simple average *)
    let avg_vol = Array.fold_left (fun acc rv -> acc +. rv.volatility) 0.0 realized_vols
                  /. float_of_int n in
    {
      timestamp = Unix.time ();
      forecast_type = HAR { beta_d; beta_w; beta_m };
      forecast_vol = avg_vol;
      confidence_interval = None;
      horizon_days;
    }
  else begin
    (* Get recent RV components *)
    let vols = Array.map (fun rv -> rv.volatility) realized_vols in

    let rv_d = vols.(n - 1) in
    let rv_w = (Array.fold_left (+.) 0.0 (Array.sub vols (n - 5) 5)) /. 5.0 in
    let rv_m = (Array.fold_left (+.) 0.0 (Array.sub vols (n - 21) 21)) /. 21.0 in

    (* HAR forecast: RV_{t+1} = β₀ + β_d·RV_d + β_w·RV_w + β_m·RV_m *)
    let forecast_vol = beta_0 +. beta_d *. rv_d +. beta_w *. rv_w +. beta_m *. rv_m in

    {
      timestamp = Unix.time ();
      forecast_type = HAR { beta_d; beta_w; beta_m };
      forecast_vol = max 0.01 forecast_vol;  (* Floor at 1% *)
      confidence_interval = None;
      horizon_days;
    }
  end

(* Historical average forecast *)
let historical_forecast ~realized_vols ~window_days =
  let n = Array.length realized_vols in
  let window = min window_days n in

  if window = 0 then
    {
      timestamp = Unix.time ();
      forecast_type = Historical { window = window_days };
      forecast_vol = 0.20;  (* Default 20% *)
      confidence_interval = None;
      horizon_days = 1;
    }
  else begin
    let recent_vols = Array.sub realized_vols (n - window) window in
    let avg_vol = Array.fold_left (fun acc rv -> acc +. rv.volatility) 0.0 recent_vols
                  /. float_of_int window in

    (* Compute standard error for CI *)
    let variance = Array.fold_left (fun acc rv ->
      let dev = rv.volatility -. avg_vol in
      acc +. dev *. dev
    ) 0.0 recent_vols /. float_of_int (window - 1) in

    let se = sqrt variance /. sqrt (float_of_int window) in
    let ci = (avg_vol -. 1.96 *. se, avg_vol +. 1.96 *. se) in

    {
      timestamp = Unix.time ();
      forecast_type = Historical { window = window_days };
      forecast_vol = avg_vol;
      confidence_interval = Some ci;
      horizon_days = 1;
    }
  end

(* Ensemble forecast *)
let ensemble_forecast ~forecasts ~weights =
  let n = Array.length forecasts in
  if n = 0 || n <> Array.length weights then
    {
      timestamp = Unix.time ();
      forecast_type = Historical { window = 21 };
      forecast_vol = 0.20;
      confidence_interval = None;
      horizon_days = 1;
    }
  else begin
    (* Normalize weights *)
    let sum_weights = Array.fold_left (+.) 0.0 weights in
    let norm_weights = Array.map (fun w -> w /. sum_weights) weights in

    (* Weighted average of forecasts *)
    let weighted_vol = ref 0.0 in
    for i = 0 to n - 1 do
      weighted_vol := !weighted_vol +. norm_weights.(i) *. forecasts.(i).forecast_vol
    done;

    (* Use first forecast's metadata *)
    {
      timestamp = forecasts.(0).timestamp;
      forecast_type = forecasts.(0).forecast_type;
      forecast_vol = !weighted_vol;
      confidence_interval = None;
      horizon_days = forecasts.(0).horizon_days;
    }
  end

(* Forecast RMSE *)
let forecast_rmse ~forecasts ~realized =
  let n = min (Array.length forecasts) (Array.length realized) in
  if n = 0 then 0.0
  else begin
    let sum_sq_error = ref 0.0 in
    for i = 0 to n - 1 do
      let error = forecasts.(i).forecast_vol -. realized.(i).volatility in
      sum_sq_error := !sum_sq_error +. error *. error
    done;
    sqrt (!sum_sq_error /. float_of_int n)
  end

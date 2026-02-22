(* Realized variance calculations using various estimators *)

(* ========================================================================== *)
(* Close-to-Close Realized Variance *)
(* ========================================================================== *)

let compute_realized_variance ~prices ~annualization_factor =
  let n = Array.length prices in
  if n < 2 then 0.0
  else begin
    let sum_squared_returns = ref 0.0 in

    for i = 1 to n - 1 do
      let log_return = log (prices.(i) /. prices.(i - 1)) in
      sum_squared_returns := !sum_squared_returns +. (log_return *. log_return)
    done;

    (* RV = (Annualization / N) × Σ r² *)
    (annualization_factor /. float_of_int (n - 1)) *. !sum_squared_returns
  end

(* ========================================================================== *)
(* Parkinson High-Low Estimator *)
(* ========================================================================== *)

let parkinson_estimator ~highs ~lows ~annualization_factor =
  (*
    Parkinson (1980): Uses high-low range

    RV = (252/N) Σ [(ln(H/L))² / (4·ln(2))]

    More efficient than close-to-close (5x less variance)
  *)
  let n = Array.length highs in
  if n < 1 || Array.length lows <> n then 0.0
  else begin
    let sum = ref 0.0 in
    let four_ln_2 = 4.0 *. log 2.0 in

    for i = 0 to n - 1 do
      let hl_ratio = log (highs.(i) /. lows.(i)) in
      sum := !sum +. (hl_ratio *. hl_ratio)
    done;

    (annualization_factor /. float_of_int n) *. (!sum /. four_ln_2)
  end

(* ========================================================================== *)
(* Garman-Klass OHLC Estimator *)
(* ========================================================================== *)

let garman_klass_estimator ~opens ~highs ~lows ~closes ~annualization_factor =
  (*
    Garman-Klass (1980): Uses OHLC

    RV = (252/N) Σ [0.5·(ln(H/L))² - (2·ln(2) - 1)·(ln(C/O))²]

    8x more efficient than close-to-close
  *)
  let n = Array.length opens in
  if n < 1 || Array.length highs <> n || Array.length lows <> n || Array.length closes <> n then 0.0
  else begin
    let sum = ref 0.0 in
    let coeff = 2.0 *. log 2.0 -. 1.0 in

    for i = 0 to n - 1 do
      let hl = log (highs.(i) /. lows.(i)) in
      let co = log (closes.(i) /. opens.(i)) in
      let term = 0.5 *. hl *. hl -. coeff *. co *. co in
      sum := !sum +. term
    done;

    (annualization_factor /. float_of_int n) *. !sum
  end

(* ========================================================================== *)
(* Rogers-Satchell Estimator *)
(* ========================================================================== *)

let rogers_satchell_estimator ~opens ~highs ~lows ~closes ~annualization_factor =
  (*
    Rogers-Satchell (1991): Drift-independent estimator

    RV = (252/N) Σ [ln(H/C)·ln(H/O) + ln(L/C)·ln(L/O)]

    Handles non-zero drift better than Garman-Klass
  *)
  let n = Array.length opens in
  if n < 1 || Array.length highs <> n || Array.length lows <> n || Array.length closes <> n then 0.0
  else begin
    let sum = ref 0.0 in

    for i = 0 to n - 1 do
      let hc = log (highs.(i) /. closes.(i)) in
      let ho = log (highs.(i) /. opens.(i)) in
      let lc = log (lows.(i) /. closes.(i)) in
      let lo = log (lows.(i) /. opens.(i)) in
      let term = hc *. ho +. lc *. lo in
      sum := !sum +. term
    done;

    (annualization_factor /. float_of_int n) *. !sum
  end

(* ========================================================================== *)
(* Yang-Zhang Estimator *)
(* ========================================================================== *)

let yang_zhang_estimator ~opens ~highs ~lows ~closes ~annualization_factor =
  (*
    Yang-Zhang (2000): Combines overnight and intraday volatility

    RV = σ²_overnight + k·σ²_open-close + (1-k)·σ²_RS

    where k = 0.34 / (1.34 + (n+1)/(n-1))

    Most efficient unbiased estimator (14x better than close-to-close)
  *)
  let n = Array.length opens in
  if n < 2 || Array.length highs <> n || Array.length lows <> n || Array.length closes <> n then 0.0
  else begin
    (* Overnight variance *)
    let overnight_sum = ref 0.0 in
    let overnight_mean = ref 0.0 in

    for i = 1 to n - 1 do
      let overnight_ret = log (opens.(i) /. closes.(i - 1)) in
      overnight_mean := !overnight_mean +. overnight_ret
    done;
    overnight_mean := !overnight_mean /. float_of_int (n - 1);

    for i = 1 to n - 1 do
      let overnight_ret = log (opens.(i) /. closes.(i - 1)) in
      let dev = overnight_ret -. !overnight_mean in
      overnight_sum := !overnight_sum +. dev *. dev
    done;
    let sigma_o = !overnight_sum /. float_of_int (n - 1) in

    (* Open-to-close variance *)
    let oc_sum = ref 0.0 in
    let oc_mean = ref 0.0 in

    for i = 0 to n - 1 do
      let oc_ret = log (closes.(i) /. opens.(i)) in
      oc_mean := !oc_mean +. oc_ret
    done;
    oc_mean := !oc_mean /. float_of_int n;

    for i = 0 to n - 1 do
      let oc_ret = log (closes.(i) /. opens.(i)) in
      let dev = oc_ret -. !oc_mean in
      oc_sum := !oc_sum +. dev *. dev
    done;
    let sigma_c = !oc_sum /. float_of_int n in

    (* Rogers-Satchell component *)
    let sigma_rs = rogers_satchell_estimator ~opens ~highs ~lows ~closes ~annualization_factor:1.0 in

    (* Weighting factor k *)
    let k = 0.34 /. (1.34 +. (float_of_int (n + 1)) /. (float_of_int (n - 1))) in

    (* Yang-Zhang estimator *)
    let yz = sigma_o +. k *. sigma_c +. (1.0 -. k) *. sigma_rs in
    annualization_factor *. yz
  end

(* ========================================================================== *)
(* Rolling Realized Variance *)
(* ========================================================================== *)

let rolling_realized_variance ~prices ~window_days ~annualization_factor =
  let n = Array.length prices in
  if n < window_days + 1 then [||]
  else begin
    let num_windows = n - window_days in
    Array.init num_windows (fun i ->
      let window = Array.sub prices i (window_days + 1) in
      compute_realized_variance ~prices:window ~annualization_factor
    )
  end

(* ========================================================================== *)
(* EWMA Forecast *)
(* ========================================================================== *)

let forecast_ewma ~returns ~lambda ~annualization_factor =
  (*
    Exponentially Weighted Moving Average

    σ²ₜ = λ·σ²ₜ₋₁ + (1-λ)·r²ₜ

    Common lambda values:
    - RiskMetrics: λ = 0.94 (daily)
    - Short-term: λ = 0.90
    - Long-term: λ = 0.97
  *)
  let n = Array.length returns in
  if n < 2 then 0.0
  else begin
    (* Initialize with sample variance *)
    let init_var = ref 0.0 in
    for i = 0 to min 20 (n - 1) do
      init_var := !init_var +. returns.(i) *. returns.(i)
    done;
    init_var := !init_var /. float_of_int (min 21 n);

    (* EWMA recursion *)
    let var = ref !init_var in
    for i = 0 to n - 1 do
      var := lambda *. !var +. (1.0 -. lambda) *. returns.(i) *. returns.(i)
    done;

    annualization_factor *. !var
  end

(* ========================================================================== *)
(* GARCH(1,1) Forecast *)
(* ========================================================================== *)

let forecast_garch ~returns ~omega ~alpha ~beta ~annualization_factor =
  (*
    GARCH(1,1) model:

    σ²ₜ = ω + α·r²ₜ₋₁ + β·σ²ₜ₋₁

    Long-run variance: ω / (1 - α - β)

    Typical parameters (equity indices):
    - ω ≈ 0.000001
    - α ≈ 0.05-0.10
    - β ≈ 0.85-0.92
    - α + β < 1 (stationarity)
  *)
  let n = Array.length returns in
  if n < 2 then 0.0
  else begin
    (* Initialize with unconditional variance *)
    let long_run_var = omega /. (1.0 -. alpha -. beta) in
    let var = ref long_run_var in

    (* GARCH recursion *)
    for i = 0 to n - 1 do
      var := omega +. alpha *. returns.(i) *. returns.(i) +. beta *. !var
    done;

    annualization_factor *. !var
  end

(* Hedge Ratio Optimization *)

(** Statistical measures **)

(* Calculate mean *)
let mean series =
  let n = Array.length series in
  if n = 0 then 0.0
  else Array.fold_left (+.) 0.0 series /. float_of_int n

(* Calculate variance *)
let variance ~series =
  let n = Array.length series in
  if n < 2 then 0.0
  else
    let mu = mean series in
    let sum_sq_dev = Array.fold_left (fun acc x ->
      let dev = x -. mu in
      acc +. dev *. dev
    ) 0.0 series in
    sum_sq_dev /. float_of_int (n - 1)

(* Calculate standard deviation *)
let std_dev ~series =
  sqrt (variance ~series)

(* Calculate covariance *)
let covariance ~series1 ~series2 =
  let n1 = Array.length series1 in
  let n2 = Array.length series2 in

  if n1 = 0 || n2 = 0 || n1 <> n2 then
    0.0
  else
    let mu1 = mean series1 in
    let mu2 = mean series2 in

    let sum_products = ref 0.0 in
    for i = 0 to n1 - 1 do
      let dev1 = series1.(i) -. mu1 in
      let dev2 = series2.(i) -. mu2 in
      sum_products := !sum_products +. dev1 *. dev2
    done;

    !sum_products /. float_of_int (n1 - 1)

(* Calculate correlation *)
let correlation ~series1 ~series2 =
  let cov = covariance ~series1 ~series2 in
  let std1 = std_dev ~series:series1 in
  let std2 = std_dev ~series:series2 in

  if std1 = 0.0 || std2 = 0.0 then 0.0
  else cov /. (std1 *. std2)

(* Calculate beta *)
let beta ~dependent ~independent =
  let cov = covariance ~series1:dependent ~series2:independent in
  let var_indep = variance ~series:independent in

  if var_indep = 0.0 then 0.0
  else cov /. var_indep

(** Minimum variance hedge ratio **)

(* Minimum variance hedge ratio

   h* = Cov(ΔS, ΔF) / Var(ΔF)

   This is equivalent to the regression coefficient (beta)
*)
let min_variance_hedge_ratio ~exposure_returns ~futures_returns =
  beta ~dependent:exposure_returns ~independent:futures_returns

(* Regression-based hedge ratio (same as min variance) *)
let regression_hedge_ratio ~exposure_returns ~futures_returns =
  min_variance_hedge_ratio ~exposure_returns ~futures_returns

(** Optimal hedge with costs **)

(* Optimal hedge ratio considering transaction costs

   Without costs: h* = Cov(S,F) / Var(F) = h_mv (min variance)

   With transaction costs, minimize mean-variance utility with costs:
   min_h [ γ × Var(S - h×F) + c × |h| ]

   where:
   - γ = risk aversion coefficient
   - c = transaction cost per unit
   - S = exposure returns, F = futures returns

   Var(S - h×F) = Var(S) + h²×Var(F) - 2h×Cov(S,F)

   Taking derivative w.r.t. h and setting to zero:
   2γ × h × Var(F) - 2γ × Cov(S,F) + c × sign(h) = 0

   For h > 0 (typical hedging case):
   h* = Cov(S,F)/Var(F) - c / (2γ × Var(F))
   h* = h_mv - c / (2γ × σ_F²)

   This formula has proper economic interpretation:
   - Cost adjustment is INVERSELY proportional to risk aversion (more risk-averse = hedge more)
   - Cost adjustment is INVERSELY proportional to futures variance (more volatile = smaller adjustment)
   - Reduces hedge ratio when costs are high relative to risk reduction benefit
*)
let optimal_hedge_with_costs ~exposure_returns ~futures_returns ~transaction_cost_bps ~risk_aversion =
  let h_min_var = min_variance_hedge_ratio ~exposure_returns ~futures_returns in

  (* Get futures variance for the adjustment *)
  let var_futures = variance ~series:futures_returns in

  (* Transaction cost per unit (convert bps to decimal) *)
  let cost_per_unit = transaction_cost_bps /. 10000.0 in

  (* Cost adjustment: c / (2γ × σ_F²) *)
  let cost_adjustment =
    if var_futures > 1e-10 && risk_aversion > 0.0 then
      cost_per_unit /. (2.0 *. risk_aversion *. var_futures)
    else
      0.0
  in

  (* Optimal hedge ratio with cost adjustment *)
  let h_optimal = h_min_var -. cost_adjustment in

  (* Ensure hedge ratio is non-negative (can't short-hedge a long exposure) *)
  max 0.0 h_optimal

(** Cross-hedge optimization **)

(* Multi-instrument hedge (multiple regression)

   For simplicity, use a greedy approach:
   1. Find best single instrument hedge
   2. Add next best instrument for residual risk
   3. Repeat

   Full solution would use matrix operations (X'X)^-1 X'Y
*)
let multi_instrument_hedge ~exposure_returns ~futures_returns_array =
  let n_instruments = Array.length futures_returns_array in

  if n_instruments = 0 then
    [||]
  else if n_instruments = 1 then
    (* Single instrument: use min variance *)
    [| min_variance_hedge_ratio ~exposure_returns ~futures_returns:futures_returns_array.(0) |]
  else
    (* Multiple instruments: simplified greedy approach *)
    (* For now, just calculate individual hedge ratios *)
    (* TODO: Implement proper multiple regression *)
    Array.map (fun futures_returns ->
      min_variance_hedge_ratio ~exposure_returns ~futures_returns
    ) futures_returns_array

(** Hedge effectiveness metrics **)

(* R-squared (coefficient of determination) *)
let r_squared ~actual ~predicted =
  let n = Array.length actual in
  if n = 0 || Array.length predicted <> n then 0.0
  else
    let mean_actual = mean actual in

    let ss_tot = ref 0.0 in
    let ss_res = ref 0.0 in

    for i = 0 to n - 1 do
      ss_tot := !ss_tot +. (actual.(i) -. mean_actual) ** 2.0;
      ss_res := !ss_res +. (actual.(i) -. predicted.(i)) ** 2.0
    done;

    if !ss_tot = 0.0 then 0.0
    else 1.0 -. (!ss_res /. !ss_tot)

(* Hedge effectiveness ratio *)
let hedge_effectiveness_ratio ~unhedged_returns ~hedged_returns =
  let var_unhedged = variance ~series:unhedged_returns in
  let var_hedged = variance ~series:hedged_returns in

  if var_unhedged = 0.0 then 0.0
  else 1.0 -. (var_hedged /. var_unhedged)

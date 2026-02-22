(** Value-at-Risk and Expected Shortfall forecasting *)

open Types

type distribution =
  | Normal
  | StudentT of float

(* Standard normal quantiles *)
let z_95 = 1.6449
let z_99 = 2.3263

(* Standard normal PDF at x *)
let phi x = exp (-0.5 *. x *. x) /. sqrt (2.0 *. Float.pi)

(* Approximate t-distribution quantile using Abramowitz & Stegun *)
let t_quantile df alpha =
  (* For large df, approaches normal *)
  if df > 30.0 then
    if alpha = 0.95 then z_95 else z_99
  else
    (* Common values for t-distribution *)
    match (int_of_float df, alpha) with
    | 5, 0.95 -> 2.015
    | 5, 0.99 -> 3.365
    | 6, 0.95 -> 1.943
    | 6, 0.99 -> 3.143
    | 7, 0.95 -> 1.895
    | 7, 0.99 -> 2.998
    | 8, 0.95 -> 1.860
    | 8, 0.99 -> 2.896
    | 10, 0.95 -> 1.812
    | 10, 0.99 -> 2.764
    | 15, 0.95 -> 1.753
    | 15, 0.99 -> 2.602
    | 20, 0.95 -> 1.725
    | 20, 0.99 -> 2.528
    | _ ->
      (* Linear interpolation fallback *)
      let base = if alpha = 0.95 then z_95 else z_99 in
      base *. (1.0 +. 2.0 /. df)

(* ES for normal distribution: ES = phi(z) / (1 - alpha) * sigma *)
let es_normal_factor alpha =
  let z = if alpha = 0.95 then z_95 else z_99 in
  phi z /. (1.0 -. alpha)

(* ES multiplier for t-distribution relative to VaR
   ES/VaR ratio increases with lower df (fatter tails) *)
let es_t_multiplier df alpha =
  (* For t(6): ES ≈ 1.25 * VaR at 95%, 1.35 * VaR at 99%
     For t(4): ES ≈ 1.35 * VaR at 95%, 1.50 * VaR at 99% *)
  let base_mult = if alpha >= 0.99 then 1.35 else 1.25 in
  base_mult +. (6.0 -. df) *. 0.05  (* Increase multiplier for lower df *)

let compute_var dist alpha sigma =
  match dist with
  | Normal ->
    let z = if alpha >= 0.99 then z_99 else z_95 in
    z *. sigma
  | StudentT df ->
    let t = t_quantile df alpha in
    t *. sigma

let compute_es dist alpha sigma =
  match dist with
  | Normal ->
    es_normal_factor alpha *. sigma
  | StudentT df ->
    (* ES = VaR * multiplier for t-distribution *)
    let var = compute_var dist alpha sigma in
    var *. es_t_multiplier df alpha

let forecast_tail_risk
    ?(distribution = StudentT 6.0)  (* Default: t(6) for fat tails *)
    ?(jump_premium = 0.15)          (* Add 15% to vol if recent jumps *)
    (har : har_coefficients)
    (rv_series : daily_rv array)
    (jumps : jump_indicator array)
    : tail_risk_forecast =

  let n = Array.length rv_series in
  let today = if n > 0 then rv_series.(n - 1).date else "unknown" in

  (* Base RV forecast from HAR model *)
  let base_rv = Har_rv.forecast_rv har rv_series in

  (* Check for recent jumps (last 5 days) *)
  let recent_jump_count = Jump_detection.count_recent_jumps jumps 5 in
  let jump_adjusted = recent_jump_count > 0 in

  (* Add jump premium if recent jumps detected *)
  let rv_forecast =
    if jump_adjusted then
      base_rv *. (1.0 +. jump_premium *. float_of_int recent_jump_count)
    else
      base_rv
  in

  let vol_forecast = sqrt rv_forecast in

  (* Compute VaR and ES *)
  let var_95 = compute_var distribution 0.95 vol_forecast in
  let var_99 = compute_var distribution 0.99 vol_forecast in
  let es_95 = compute_es distribution 0.95 vol_forecast in
  let es_99 = compute_es distribution 0.99 vol_forecast in

  {
    date = today;
    rv_forecast;
    vol_forecast;
    var_95;
    var_99;
    es_95;
    es_99;
    jump_adjusted;
  }

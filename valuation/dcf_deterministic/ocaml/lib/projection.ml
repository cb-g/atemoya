(** Multi-year cash flow projection with optional mean reversion *)

(** Calculate mean-reverting growth rate at time t

    g(t) = g_LT + (g_0 - g_LT) × exp(-λ × t)

    Where:
    - g_0 = initial growth rate (fundamental-based)
    - g_LT = long-term terminal growth rate (GDP proxy)
    - λ = mean reversion speed (higher = faster decay)
    - t = time in years

    This captures the economic reality that high growth rates are not
    sustainable indefinitely - they decay toward the economy's growth rate.
*)
let mean_reverting_growth_rate ~g_0 ~g_terminal ~lambda ~t =
  g_terminal +. (g_0 -. g_terminal) *. exp (-. lambda *. t)

(** Project cash flows with constant growth rate (legacy behavior) *)
let project_constant_growth ~cf_0 ~growth_rate ~years =
  (* CF_t = CF_0 × (1 + g)^t for t = 1..years *)
  Array.init years (fun i ->
    let t = float_of_int (i + 1) in
    cf_0 *. ((1.0 +. growth_rate) ** t)
  )

(** Project cash flows with mean-reverting growth rates

    Each year's growth rate decays toward terminal growth:
    CF_t = CF_{t-1} × (1 + g(t))

    where g(t) = g_LT + (g_0 - g_LT) × exp(-λ × t)
*)
let project_mean_reverting ~cf_0 ~growth_rate ~terminal_growth ~lambda ~years =
  let cash_flows = Array.make years 0.0 in
  let cf_prev = ref cf_0 in

  for i = 0 to years - 1 do
    let t = float_of_int (i + 1) in
    let g_t = mean_reverting_growth_rate
      ~g_0:growth_rate
      ~g_terminal:terminal_growth
      ~lambda
      ~t
    in
    let cf_t = !cf_prev *. (1.0 +. g_t) in
    cash_flows.(i) <- cf_t;
    cf_prev := cf_t
  done;

  cash_flows

(** Project FCFE with configurable growth model *)
let project_fcfe ~fcfe_0 ~growth_rate ~years =
  (* Default: constant growth for backward compatibility *)
  project_constant_growth ~cf_0:fcfe_0 ~growth_rate ~years

(** Project FCFE with mean reversion option *)
let project_fcfe_with_reversion ~fcfe_0 ~growth_rate ~terminal_growth ~lambda ~years ~use_reversion =
  if use_reversion then
    project_mean_reverting ~cf_0:fcfe_0 ~growth_rate ~terminal_growth ~lambda ~years
  else
    project_constant_growth ~cf_0:fcfe_0 ~growth_rate ~years

(** Project FCFF with configurable growth model *)
let project_fcff ~fcff_0 ~growth_rate ~years =
  (* Default: constant growth for backward compatibility *)
  project_constant_growth ~cf_0:fcff_0 ~growth_rate ~years

(** Project FCFF with mean reversion option *)
let project_fcff_with_reversion ~fcff_0 ~growth_rate ~terminal_growth ~lambda ~years ~use_reversion =
  if use_reversion then
    project_mean_reverting ~cf_0:fcff_0 ~growth_rate ~terminal_growth ~lambda ~years
  else
    project_constant_growth ~cf_0:fcff_0 ~growth_rate ~years

let create_projection ~financial_data ~market_data ~tax_rate ~params =
  let open Types in

  (* Calculate current year cash flows (year 0) *)
  let fcfe_0 = Cash_flow.calculate_fcfe ~financial_data ~market_data in
  let fcff_0 = Cash_flow.calculate_fcff ~financial_data ~tax_rate in

  (* Calculate growth rates with clamping *)
  let growth_rate_fcfe, growth_clamped_fcfe =
    Growth.calculate_fcfe_growth_rate ~financial_data ~fcfe:fcfe_0 ~params
  in

  let growth_rate_fcff, growth_clamped_fcff =
    Growth.calculate_fcff_growth_rate ~financial_data ~tax_rate ~params
  in

  (* Project cash flows over h years
     Use mean reversion if enabled in params *)
  let fcfe = project_fcfe_with_reversion
    ~fcfe_0
    ~growth_rate:growth_rate_fcfe
    ~terminal_growth:params.terminal_growth_rate
    ~lambda:params.mean_reversion_lambda
    ~years:params.projection_years
    ~use_reversion:params.mean_reversion_enabled
  in

  let fcff = project_fcff_with_reversion
    ~fcff_0
    ~growth_rate:growth_rate_fcff
    ~terminal_growth:params.terminal_growth_rate
    ~lambda:params.mean_reversion_lambda
    ~years:params.projection_years
    ~use_reversion:params.mean_reversion_enabled
  in

  {
    fcfe;
    fcff;
    growth_rate_fcfe;
    growth_rate_fcff;
    growth_clamped_fcfe;
    growth_clamped_fcff;
  }

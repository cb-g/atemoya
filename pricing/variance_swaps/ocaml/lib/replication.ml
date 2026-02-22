(* Variance swap replication using option portfolios *)

open Types
open Variance_swap_pricing

(* Helper: error function (same as in variance_swap_pricing) *)
let erf x =
  let a1 =  0.254829592 in
  let a2 = -0.284496736 in
  let a3 =  1.421413741 in
  let a4 = -1.453152027 in
  let a5 =  1.061405429 in
  let p  =  0.3275911 in
  let sign = if x < 0.0 then -1.0 else 1.0 in
  let x = abs_float x in
  let t = 1.0 /. (1.0 +. p *. x) in
  let y = 1.0 -. (((((a5 *. t +. a4) *. t) +. a3) *. t +. a2) *. t +. a1) *. t *. exp (-. x *. x) in
  sign *. y

(* Helper: normal CDF *)
let normal_cdf x =
  0.5 *. (1.0 +. erf (x /. sqrt 2.0))

(* ========================================================================== *)
(* Helpers *)
(* ========================================================================== *)

let compute_option_greeks ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  (*
    Simplified Greeks for replication portfolio
    Delta: ∂V/∂S
    Vega: ∂V/∂σ
  *)
  if expiry <= 0.0 || volatility <= 0.0 then
    { delta = 0.0; gamma = 0.0; vega = 0.0; theta = 0.0; rho = 0.0 }
  else begin
    let d1 = (log (spot /. strike) +. (rate -. dividend +. 0.5 *. volatility *. volatility) *. expiry)
             /. (volatility *. sqrt expiry) in
    let d2 = d1 -. volatility *. sqrt expiry in

    let delta = match option_type with
      | Call -> exp (-.dividend *. expiry) *. normal_cdf d1
      | Put -> exp (-.dividend *. expiry) *. (normal_cdf d1 -. 1.0)
    in

    (* Gamma (same for call and put) *)
    let n_d1 = (1.0 /. sqrt (2.0 *. Float.pi)) *. exp (-.0.5 *. d1 *. d1) in
    let gamma = (exp (-.dividend *. expiry) *. n_d1) /. (spot *. volatility *. sqrt expiry) in

    (* Vega *)
    let vega = spot *. exp (-.dividend *. expiry) *. n_d1 *. sqrt expiry in

    (* Theta *)
    let theta_part1 = -.(spot *. n_d1 *. volatility *. exp (-.dividend *. expiry)) /. (2.0 *. sqrt expiry) in
    let theta_part2 = match option_type with
      | Call ->
          -.rate *. strike *. exp (-.rate *. expiry) *. normal_cdf d2 +.
          dividend *. spot *. exp (-.dividend *. expiry) *. normal_cdf d1
      | Put ->
          rate *. strike *. exp (-.rate *. expiry) *. normal_cdf (-.d2) -.
          dividend *. spot *. exp (-.dividend *. expiry) *. normal_cdf (-.d1)
    in
    let theta = theta_part1 +. theta_part2 in

    (* Rho *)
    let rho = match option_type with
      | Call -> strike *. expiry *. exp (-.rate *. expiry) *. normal_cdf d2
      | Put -> -.strike *. expiry *. exp (-.rate *. expiry) *. normal_cdf (-.d2)
    in

    { delta; gamma; vega; theta; rho }
  end

(* ========================================================================== *)
(* Build Replication Portfolio *)
(* ========================================================================== *)

let build_replication_portfolio vol_surface underlying_data ~rate ~expiry ~target_variance_notional ~strike_grid =
  (*
    Carr-Madan replication:

    Variance exposure = (2/T)·e^(rT) Σᵢ [Option_i / K_i²] · ΔK_i

    Weight for each option: w_i = (2/T)·e^(rT) · ΔK_i / K_i²

    Normalized by target variance notional
  *)
  let spot = underlying_data.spot_price in
  let dividend = underlying_data.dividend_yield in
  let forward = spot *. exp ((rate -. dividend) *. expiry) in

  let n = Array.length strike_grid in
  if n < 2 then
    {
      ticker = underlying_data.ticker;
      target_variance_notional;
      legs = [||];
      total_cost = 0.0;
      total_vega = 0.0;
      total_delta = 0.0;
    }
  else begin
    let legs = Array.mapi (fun i strike ->
      (* Determine option type: put if K < F, call if K >= F *)
      let option_type = if strike < forward then Put else Call in

      (* Compute ΔK using midpoint rule *)
      let delta_k =
        if i = 0 then strike_grid.(i + 1) -. strike
        else if i = n - 1 then strike -. strike_grid.(i - 1)
        else (strike_grid.(i + 1) -. strike_grid.(i - 1)) /. 2.0
      in

      (* Weight: (2/T)·e^(rT) · ΔK / K² *)
      let base_weight = (2.0 /. expiry) *. exp (rate *. expiry) *. delta_k /. (strike *. strike) in

      (* Scale by target notional *)
      let weight = base_weight *. target_variance_notional in

      (* Get IV from surface *)
      let iv = get_iv_from_surface vol_surface ~strike ~expiry ~spot in

      (* Price option *)
      let price = bs_price ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility:iv in

      (* Compute Greeks *)
      let option_greeks = compute_option_greeks ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility:iv in

      {
        option_type;
        strike;
        expiry;
        weight;
        price;
        delta = option_greeks.delta *. weight;
        vega = option_greeks.vega *. weight;
      }
    ) strike_grid in

    (* Compute totals *)
    let total_cost = Array.fold_left (fun acc (leg : replication_leg) -> acc +. leg.price *. leg.weight) 0.0 legs in
    let total_vega = Array.fold_left (fun acc (leg : replication_leg) -> acc +. leg.vega) 0.0 legs in
    let total_delta = Array.fold_left (fun acc (leg : replication_leg) -> acc +. leg.delta) 0.0 legs in

    {
      ticker = underlying_data.ticker;
      target_variance_notional;
      legs;
      total_cost;
      total_vega;
      total_delta;
    }
  end

(* ========================================================================== *)
(* Portfolio Greeks *)
(* ========================================================================== *)

let portfolio_greeks portfolio ~vol_surface ~spot ~rate ~dividend =
  let delta = portfolio.total_delta in
  let vega = portfolio.total_vega in

  (* Gamma: sum of individual option gammas weighted by position *)
  let gamma = Array.fold_left (fun acc leg ->
    let iv = get_iv_from_surface vol_surface ~strike:leg.strike ~expiry:leg.expiry ~spot in
    let g = compute_option_greeks ~option_type:leg.option_type ~spot ~strike:leg.strike
              ~expiry:leg.expiry ~rate ~dividend ~volatility:iv in
    acc +. g.gamma *. leg.weight
  ) 0.0 portfolio.legs in

  (* Theta: approximate as -vega / (2 * sqrt(T)) *)
  let avg_expiry = if Array.length portfolio.legs > 0 then
    portfolio.legs.(0).expiry
  else 0.0 in
  let theta = if avg_expiry > 0.0 then -.vega /. (2.0 *. sqrt avg_expiry) else 0.0 in

  (* Rho: small for variance swaps *)
  let rho = 0.0 in

  { delta; gamma; vega; theta; rho }

(* ========================================================================== *)
(* Delta Neutrality *)
(* ========================================================================== *)

let is_delta_neutral portfolio ~tolerance =
  abs_float portfolio.total_delta < tolerance

(* ========================================================================== *)
(* Rebalancing *)
(* ========================================================================== *)

let rebalance_portfolio portfolio ~current_spot ~vol_surface ~rate =
  (*
    Rebalancing steps:
    1. Reprice all legs at current spot
    2. Recompute Greeks
    3. Adjust weights if delta drift is large

    For static replication, we typically don't rebalance unless
    spot moves significantly (> 10% from entry)
  *)
  let updated_legs = Array.map (fun leg ->
    (* Get updated IV *)
    let iv = get_iv_from_surface vol_surface ~strike:leg.strike ~expiry:leg.expiry ~spot:current_spot in

    (* Reprice *)
    let price = bs_price
      ~option_type:leg.option_type
      ~spot:current_spot
      ~strike:leg.strike
      ~expiry:leg.expiry
      ~rate
      ~dividend:0.0  (* Simplified *)
      ~volatility:iv
    in

    (* Recompute Greeks *)
    let option_greeks = compute_option_greeks
      ~option_type:leg.option_type
      ~spot:current_spot
      ~strike:leg.strike
      ~expiry:leg.expiry
      ~rate
      ~dividend:0.0
      ~volatility:iv
    in

    {
      leg with
      price;
      delta = option_greeks.delta *. leg.weight;
      vega = option_greeks.vega *. leg.weight;
    }
  ) portfolio.legs in

  (* Recompute totals *)
  let total_cost = Array.fold_left (fun acc (leg : replication_leg) -> acc +. leg.price *. leg.weight) 0.0 updated_legs in
  let total_vega = Array.fold_left (fun acc (leg : replication_leg) -> acc +. leg.vega) 0.0 updated_legs in
  let total_delta = Array.fold_left (fun acc (leg : replication_leg) -> acc +. leg.delta) 0.0 updated_legs in

  { portfolio with legs = updated_legs; total_cost; total_vega; total_delta }

(* ========================================================================== *)
(* Variance Vega *)
(* ========================================================================== *)

let variance_vega portfolio =
  (*
    Variance vega: ∂K_var / ∂σ

    For variance swaps: Vega_var ≈ Total vega of replication portfolio
  *)
  portfolio.total_vega

(* ========================================================================== *)
(* Transaction Costs *)
(* ========================================================================== *)

let estimate_transaction_costs portfolio ~bid_ask_spread_bps =
  (*
    Transaction cost = Σ (Price × Weight × Spread)

    where Spread = bid_ask_spread_bps / 10000
  *)
  let spread_fraction = bid_ask_spread_bps /. 10000.0 in

  Array.fold_left (fun acc leg ->
    let cost = leg.price *. leg.weight *. spread_fraction in
    acc +. cost
  ) 0.0 portfolio.legs

(* ========================================================================== *)
(* Optimize Strike Grid *)
(* ========================================================================== *)

let optimize_strike_grid _vol_surface underlying_data ~rate:_ ~expiry:_ ~target_variance_notional:_ ~num_strikes =
  (*
    Optimal strike spacing for variance swap replication:

    1. Log-moneyness spacing (equal spacing in log(K/S))
    2. Concentrated around ATM
    3. Wider spacing in wings

    Range: typically 70% to 130% of spot (or based on vol surface coverage)
  *)
  let spot = underlying_data.spot_price in

  (* Log-moneyness range *)
  let min_log_m = log 0.70 in  (* 70% of spot *)
  let max_log_m = log 1.30 in  (* 130% of spot *)

  (* Generate log-spaced strikes *)
  Array.init num_strikes (fun i ->
    let fraction = float_of_int i /. float_of_int (num_strikes - 1) in
    let log_m = min_log_m +. fraction *. (max_log_m -. min_log_m) in
    spot *. exp log_m
  )

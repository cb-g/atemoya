(* Variance swap pricing using Carr-Madan replication *)

open Types

(* ========================================================================== *)
(* Black-Scholes Pricing (simplified, for option pricing in grid) *)
(* ========================================================================== *)

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

let normal_cdf x =
  0.5 *. (1.0 +. erf (x /. sqrt 2.0))

let bs_price ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  if expiry <= 0.0 || volatility <= 0.0 then 0.0
  else begin
    let d1 = (log (spot /. strike) +. (rate -. dividend +. 0.5 *. volatility *. volatility) *. expiry)
             /. (volatility *. sqrt expiry) in
    let d2 = d1 -. volatility *. sqrt expiry in

    match option_type with
    | Call ->
        spot *. exp (-.dividend *. expiry) *. normal_cdf d1 -.
        strike *. exp (-.rate *. expiry) *. normal_cdf d2
    | Put ->
        strike *. exp (-.rate *. expiry) *. normal_cdf (-.d2) -.
        spot *. exp (-.dividend *. expiry) *. normal_cdf (-.d1)
  end

(* Get IV from vol surface *)
let get_iv_from_surface vol_surface ~strike ~expiry ~spot =
  match vol_surface with
  | SVI params ->
      if Array.length params = 0 then 0.20
      else begin
        let closest_idx = ref 0 in
        let min_diff = ref (abs_float (params.(0).expiry -. expiry)) in
        for i = 1 to Array.length params - 1 do
          let diff = abs_float (params.(i).expiry -. expiry) in
          if diff < !min_diff then begin
            min_diff := diff;
            closest_idx := i
          end
        done;

        let p = params.(!closest_idx) in
        let log_moneyness = log (strike /. spot) in
        let delta_k = log_moneyness -. p.m in
        let sqrt_term = sqrt (delta_k *. delta_k +. p.sigma *. p.sigma) in
        let total_var = p.a +. p.b *. (p.rho *. delta_k +. sqrt_term) in
        sqrt (max 0.0001 (total_var /. expiry))
      end

(* ========================================================================== *)
(* Strike Grid Generation *)
(* ========================================================================== *)

let generate_strike_grid ~spot ~num_strikes ~log_moneyness_range:(min_k, max_k) =
  (* Generate log-spaced strikes *)
  let log_strikes = Array.init num_strikes (fun i ->
    let fraction = float_of_int i /. float_of_int (num_strikes - 1) in
    min_k +. fraction *. (max_k -. min_k)
  ) in

  (* Convert to actual strikes *)
  Array.map (fun log_k -> spot *. exp log_k) log_strikes

(* ========================================================================== *)
(* Carr-Madan Discrete Implementation *)
(* ========================================================================== *)

let carr_madan_discrete ~option_prices ~spot:_ ~forward ~expiry ~rate =
  (*
    Carr-Madan formula (discrete):

    K_var = (2/T)·e^(rT)·Σᵢ [(Option_i / K_i²) · ΔK_i]

    where:
      Option_i = Put(K_i)  if K_i < F
               = Call(K_i) if K_i ≥ F
      ΔK_i = (K_{i+1} - K_{i-1}) / 2  (midpoint rule)
  *)

  let n = Array.length option_prices in
  if n < 2 then 0.0
  else begin
    let sum = ref 0.0 in

    for i = 0 to n - 1 do
      let (strike, put_price, call_price) = option_prices.(i) in

      (* Choose put or call based on strike relative to forward *)
      let option_price = if strike < forward then put_price else call_price in

      (* Compute ΔK using midpoint rule *)
      let delta_k =
        if i = 0 then
          (* First strike: use forward difference *)
          let (k_next, _, _) = option_prices.(i + 1) in
          k_next -. strike
        else if i = n - 1 then
          (* Last strike: use backward difference *)
          let (k_prev, _, _) = option_prices.(i - 1) in
          strike -. k_prev
        else
          (* Middle strikes: use central difference *)
          let (k_prev, _, _) = option_prices.(i - 1) in
          let (k_next, _, _) = option_prices.(i + 1) in
          (k_next -. k_prev) /. 2.0
      in

      (* Add contribution: (Option / K²) · ΔK *)
      let contribution = (option_price /. (strike *. strike)) *. delta_k in
      sum := !sum +. contribution
    done;

    (* Final formula: (2/T) · e^(rT) · Σ *)
    let variance_strike = (2.0 /. expiry) *. exp (rate *. expiry) *. !sum in
    variance_strike
  end

(* ========================================================================== *)
(* Variance Swap Pricing *)
(* ========================================================================== *)

let price_variance_swap vol_surface ~spot ~expiry ~rate ~dividend ~strike_grid ~ticker ~notional =
  (* Compute forward price *)
  let forward = spot *. exp ((rate -. dividend) *. expiry) in

  (* Price options at each strike *)
  let option_prices = Array.map (fun strike ->
    let iv = get_iv_from_surface vol_surface ~strike ~expiry ~spot in
    let put_price = bs_price ~option_type:Put ~spot ~strike ~expiry ~rate ~dividend ~volatility:iv in
    let call_price = bs_price ~option_type:Call ~spot ~strike ~expiry ~rate ~dividend ~volatility:iv in
    (strike, put_price, call_price)
  ) strike_grid in

  (* Compute variance strike using Carr-Madan *)
  let variance_strike = carr_madan_discrete ~option_prices ~spot ~forward ~expiry ~rate in

  (* Compute vega notional *)
  let vega_notional = notional /. (2.0 *. sqrt variance_strike) in

  {
    ticker;
    notional;
    strike_var = variance_strike;
    expiry;
    vega_notional;
    entry_date = Unix.time ();
    entry_spot = spot;
  }

(* ========================================================================== *)
(* Helper Functions *)
(* ========================================================================== *)

let compute_vega_notional ~notional ~variance_strike =
  notional /. (2.0 *. sqrt variance_strike)

let variance_swap_payoff (var_swap : variance_swap) ~realized_variance =
  var_swap.notional *. (realized_variance -. var_swap.strike_var)

let variance_swap_mtm (var_swap : variance_swap) ~current_var_strike ~days_to_expiry =
  (* Approximate MTM as linear interpolation *)
  let total_days = int_of_float (var_swap.expiry *. 365.0) in
  let time_fraction = float_of_int days_to_expiry /. float_of_int total_days in

  (* MTM ≈ Notional × (Current_Strike - Entry_Strike) × time_fraction *)
  var_swap.notional *. (current_var_strike -. var_swap.strike_var) *. time_fraction

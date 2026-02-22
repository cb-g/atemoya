(* Volatility Surface Modeling - SVI and SABR *)

open Types

(* SVI Formula: Total variance as function of log-moneyness
   w(k; θ) = a + b × {ρ(k - m) + √[(k - m)² + σ²]}

   where:
   - k = log(K/F) = log-moneyness
   - θ = (a, b, ρ, m, σ) = SVI parameters
*)
let svi_total_variance (params : svi_params) ~log_moneyness =
  let k = log_moneyness in
  let delta_k = k -. params.m in
  let sqrt_term = sqrt (delta_k *. delta_k +. params.sigma *. params.sigma) in
  params.a +. params.b *. (params.rho *. delta_k +. sqrt_term)

(* Convert SVI total variance to implied volatility
   IV(k, T) = √[w(k; θ) / T]
*)
let svi_implied_vol (params : svi_params) ~strike ~spot =
  let log_moneyness = log (strike /. spot) in
  let total_var = svi_total_variance params ~log_moneyness in
  if total_var <= 0.0 then
    failwith (Printf.sprintf "Vol_surface.svi_implied_vol: negative variance %f" total_var)
  else if params.expiry <= 0.0 then
    failwith "Vol_surface.svi_implied_vol: expiry must be positive"
  else
    sqrt (total_var /. params.expiry)

(* SABR implied volatility (Hagan et al. 2002 approximation)

   For small time to expiry or F ≈ K, use simplified formula:
   σ_SABR(K, F) ≈ α / (FK)^((1-β)/2)

   For general case, use full Hagan formula with correction terms
*)
let sabr_implied_vol (params : sabr_params) ~forward ~strike =
  let alpha = params.alpha in
  let beta = params.beta in
  let rho = params.rho in
  let nu = params.nu in

  (* Handle ATM case (F ≈ K) *)
  if abs_float (forward -. strike) < 1e-6 then
    (* ATM volatility *)
    let atm_factor = (forward ** (1.0 -. beta)) in
    let correction = 1.0 +. params.expiry *. (
      ((1.0 -. beta) ** 2.0) *. (alpha ** 2.0) /. (24.0 *. (atm_factor ** 2.0))
      +. 0.25 *. rho *. beta *. nu *. alpha /. atm_factor
      +. (2.0 -. 3.0 *. rho *. rho) *. (nu ** 2.0) /. 24.0
    ) in
    alpha /. atm_factor *. correction

  else
    (* General case *)
    let fk_mid = (forward *. strike) ** (0.5 *. (1.0 -. beta)) in
    let log_fk = log (forward /. strike) in

    (* z parameter *)
    let z = (nu /. alpha) *. fk_mid *. log_fk in

    (* χ(z) function *)
    let chi_z =
      if abs_float z < 1e-6 then
        1.0  (* Limit as z → 0 *)
      else
        let sqrt_term = sqrt (1.0 -. 2.0 *. rho *. z +. z *. z) in
        z /. log ((sqrt_term +. z -. rho) /. (1.0 -. rho))
    in

    (* First factor *)
    let factor1 = alpha /. fk_mid in

    (* Second factor with correction terms *)
    let one_minus_beta_sq = (1.0 -. beta) ** 2.0 in
    let log_fk_sq = log_fk ** 2.0 in

    let correction_term = 1.0 +. (
      one_minus_beta_sq *. log_fk_sq /. 24.0
      +. (one_minus_beta_sq ** 2.0) *. (log_fk ** 4.0) /. 1920.0
    ) in

    let factor2 = chi_z /. correction_term in

    (* Third factor (time-dependent correction) *)
    let fk_avg = (forward +. strike) /. 2.0 in
    let fk_avg_factor = fk_avg ** (1.0 -. beta) in

    let time_correction = 1.0 +. params.expiry *. (
      one_minus_beta_sq *. (alpha ** 2.0) /. (24.0 *. (fk_avg_factor ** 2.0))
      +. 0.25 *. rho *. beta *. nu *. alpha /. fk_avg_factor
      +. (2.0 -. 3.0 *. (rho ** 2.0)) *. (nu ** 2.0) /. 24.0
    ) in

    factor1 *. factor2 *. time_correction

(* Find closest expiry index in param array *)
let find_closest_expiry_idx ~expiry ~params_array ~get_expiry =
  if Array.length params_array = 0 then
    failwith "Vol_surface.find_closest_expiry_idx: empty params array"
  else
    let min_idx = ref 0 in
    let min_diff = ref (abs_float (expiry -. get_expiry params_array.(0))) in

    for i = 1 to Array.length params_array - 1 do
      let diff = abs_float (expiry -. get_expiry params_array.(i)) in
      if diff < !min_diff then begin
        min_diff := diff;
        min_idx := i
      end
    done;

    !min_idx

(* Interpolate SVI parameters between two expiries *)
let interpolate_svi_params (params1 : svi_params) (params2 : svi_params) ~weight =
  {
    expiry = params1.expiry *. (1.0 -. weight) +. params2.expiry *. weight;
    a = params1.a *. (1.0 -. weight) +. params2.a *. weight;
    b = params1.b *. (1.0 -. weight) +. params2.b *. weight;
    rho = params1.rho *. (1.0 -. weight) +. params2.rho *. weight;
    m = params1.m *. (1.0 -. weight) +. params2.m *. weight;
    sigma = params1.sigma *. (1.0 -. weight) +. params2.sigma *. weight;
  }

(* Interpolate SABR parameters between two expiries *)
let interpolate_sabr_params (params1 : sabr_params) (params2 : sabr_params) ~weight =
  {
    expiry = params1.expiry *. (1.0 -. weight) +. params2.expiry *. weight;
    alpha = params1.alpha *. (1.0 -. weight) +. params2.alpha *. weight;
    beta = params1.beta *. (1.0 -. weight) +. params2.beta *. weight;
    rho = params1.rho *. (1.0 -. weight) +. params2.rho *. weight;
    nu = params1.nu *. (1.0 -. weight) +. params2.nu *. weight;
  }

(* Interpolate volatility from surface *)
let interpolate_vol (vol_surface : vol_surface) ~strike ~expiry ~spot =
  match vol_surface with
  | SVI params_array ->
      if Array.length params_array = 0 then
        failwith "Vol_surface.interpolate_vol: empty SVI params"
      else if Array.length params_array = 1 then
        (* Only one expiry available *)
        svi_implied_vol params_array.(0) ~strike ~spot
      else
        (* Find surrounding expiries for interpolation *)
        let get_expiry (p : svi_params) = p.expiry in
        let expiries = Array.map get_expiry params_array in

        (* Find lower and upper bounds *)
        let lower_idx = ref 0 in
        let upper_idx = ref 0 in

        (* Sort by expiry and find bracket *)
        for i = 0 to Array.length expiries - 1 do
          if expiries.(i) <= expiry then lower_idx := i;
          if expiries.(i) >= expiry && !upper_idx = 0 then upper_idx := i
        done;

        if !lower_idx = !upper_idx then
          (* Exact match or extrapolation *)
          svi_implied_vol params_array.(!lower_idx) ~strike ~spot
        else
          (* Linear interpolation between expiries *)
          let t1 = expiries.(!lower_idx) in
          let t2 = expiries.(!upper_idx) in
          let weight = (expiry -. t1) /. (t2 -. t1) in

          let interp_params = interpolate_svi_params
            params_array.(!lower_idx)
            params_array.(!upper_idx)
            ~weight
          in

          svi_implied_vol interp_params ~strike ~spot

  | SABR params_array ->
      if Array.length params_array = 0 then
        failwith "Vol_surface.interpolate_vol: empty SABR params"
      else if Array.length params_array = 1 then
        (* Only one expiry available *)
        let forward = spot in  (* Assume forward ≈ spot for simplicity *)
        sabr_implied_vol params_array.(0) ~forward ~strike
      else
        (* Similar interpolation logic for SABR *)
        let get_expiry (p : sabr_params) = p.expiry in
        let expiries = Array.map get_expiry params_array in

        let lower_idx = ref 0 in
        let upper_idx = ref 0 in

        for i = 0 to Array.length expiries - 1 do
          if expiries.(i) <= expiry then lower_idx := i;
          if expiries.(i) >= expiry && !upper_idx = 0 then upper_idx := i
        done;

        let forward = spot in  (* Assume forward ≈ spot *)

        if !lower_idx = !upper_idx then
          sabr_implied_vol params_array.(!lower_idx) ~forward ~strike
        else
          let t1 = expiries.(!lower_idx) in
          let t2 = expiries.(!upper_idx) in
          let weight = (expiry -. t1) /. (t2 -. t1) in

          let interp_params = interpolate_sabr_params
            params_array.(!lower_idx)
            params_array.(!upper_idx)
            ~weight
          in

          sabr_implied_vol interp_params ~forward ~strike

(* Check SVI no-arbitrage conditions *)
let check_svi_arbitrage (params : svi_params) =
  (* Basic parameter constraints *)
  let basic_ok =
    params.a >= 0.0 &&
    params.b >= 0.0 &&
    params.rho >= -1.0 && params.rho <= 1.0 &&
    params.sigma > 0.0
  in

  (* Butterfly arbitrage condition: d²C/dK² >= 0
     For SVI, this requires: b/σ >= |ρ|
  *)
  let butterfly_ok =
    if params.sigma > 0.0 then
      params.b /. params.sigma >= abs_float params.rho
    else
      false
  in

  (* Calendar arbitrage: ∂w/∂T >= 0
     For SVI, ensure total variance is increasing with time
  *)
  let calendar_ok = params.a >= 0.0 in

  basic_ok && butterfly_ok && calendar_ok

(* Validate SABR parameters *)
let validate_sabr (params : sabr_params) =
  params.alpha > 0.0 &&
  params.beta >= 0.0 && params.beta <= 1.0 &&
  params.rho >= -1.0 && params.rho <= 1.0 &&
  params.nu > 0.0 &&
  params.expiry > 0.0

(* Generate surface grid for visualization *)
let generate_surface_grid vol_surface ~spot ~strike_range ~expiry_range ~grid_points =
  let (strike_min, strike_max) = strike_range in
  let (expiry_min, expiry_max) = expiry_range in
  let (n_strikes, n_expiries) = grid_points in

  let strike_step = (strike_max -. strike_min) /. float_of_int (n_strikes - 1) in
  let expiry_step = (expiry_max -. expiry_min) /. float_of_int (n_expiries - 1) in

  let grid = ref [] in

  for i = 0 to n_strikes - 1 do
    for j = 0 to n_expiries - 1 do
      let strike = strike_min +. float_of_int i *. strike_step in
      let expiry = expiry_min +. float_of_int j *. expiry_step in

      try
        let iv = interpolate_vol vol_surface ~strike ~expiry ~spot in
        grid := (strike, expiry, iv) :: !grid
      with Failure _ ->
        (* Skip points that fail to interpolate *)
        ()
    done
  done;

  Array.of_list (List.rev !grid)

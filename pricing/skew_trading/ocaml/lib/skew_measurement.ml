(* Skew measurement - compute various skew metrics from volatility surface *)

open Types

(* ========================================================================== *)
(* Black-Scholes Helpers *)
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

(* Get IV from SVI surface *)
let get_iv_from_surface vol_surface ~strike ~expiry ~spot =
  match vol_surface with
  | SVI params ->
      if Array.length params = 0 then 0.20
      else begin
        (* Find closest expiry *)
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
        sqrt (max 0.0001 (total_var /. p.expiry))
      end

(* Compute option delta *)
let bs_delta ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  if expiry <= 0.0 || volatility <= 0.0 then 0.0
  else begin
    let d1 = (log (spot /. strike) +. (rate -. dividend +. 0.5 *. volatility *. volatility) *. expiry)
             /. (volatility *. sqrt expiry) in

    match option_type with
    | Call -> exp (-.dividend *. expiry) *. normal_cdf d1
    | Put -> exp (-.dividend *. expiry) *. (normal_cdf d1 -. 1.0)
  end

(* ========================================================================== *)
(* Find Delta Strike (Newton-Raphson) *)
(* ========================================================================== *)

let find_delta_strike option_type ~target_delta ~spot ~expiry ~rate ~dividend vol_surface =
  (*
    Newton-Raphson iteration to find strike K where Δ(K) = target_delta

    K_{n+1} = K_n - [Δ(K_n) - target_delta] / Γ(K_n)

    where Γ = dΔ/dK (gamma in strike space)
  *)
  if expiry <= 0.0 then None
  else begin
    (* Initial guess: use put-call symmetry approximation *)
    let initial_strike = match option_type with
      | Call -> spot *. exp (0.5 *. abs_float target_delta)
      | Put -> spot *. exp (-.0.5 *. abs_float target_delta)
    in

    let max_iterations = 20 in
    let tolerance = 0.001 in

    let rec iterate strike iter =
      if iter >= max_iterations then None
      else begin
        let iv = get_iv_from_surface vol_surface ~strike ~expiry ~spot in
        let delta = bs_delta ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility:iv in

        let error = delta -. target_delta in

        if abs_float error < tolerance then Some strike
        else begin
          (* Approximate gamma for derivative *)
          let h = strike *. 0.001 in
          let strike_up = strike +. h in
          let iv_up = get_iv_from_surface vol_surface ~strike:strike_up ~expiry ~spot in
          let delta_up = bs_delta ~option_type ~spot ~strike:strike_up ~expiry ~rate ~dividend ~volatility:iv_up in

          let d_delta_dk = (delta_up -. delta) /. h in

          if abs_float d_delta_dk < 1e-10 then None
          else begin
            let new_strike = strike -. error /. d_delta_dk in
            (* Bound the strike to reasonable range *)
            let bounded_strike = max (spot *. 0.5) (min (spot *. 2.0) new_strike) in
            iterate bounded_strike (iter + 1)
          end
        end
      end
    in

    iterate initial_strike 0
  end

(* ========================================================================== *)
(* Skew Metrics *)
(* ========================================================================== *)

let compute_atm_vol vol_surface ~spot ~expiry =
  get_iv_from_surface vol_surface ~strike:spot ~expiry ~spot

let compute_rr25 vol_surface ~spot ~expiry ~rate ~dividend =
  (*
    RR25 = IV(25Δ Call) - IV(25Δ Put)

    For equities: typically negative (put skew)
    RR25 ~ -3% to -5% (normal)
    RR25 ~ -7% to -10% (elevated)
  *)
  match find_delta_strike Call ~target_delta:0.25 ~spot ~expiry ~rate ~dividend vol_surface with
  | None -> 0.0
  | Some call_25d_strike ->
      match find_delta_strike Put ~target_delta:(-0.25) ~spot ~expiry ~rate ~dividend vol_surface with
      | None -> 0.0
      | Some put_25d_strike ->
          let call_25d_vol = get_iv_from_surface vol_surface ~strike:call_25d_strike ~expiry ~spot in
          let put_25d_vol = get_iv_from_surface vol_surface ~strike:put_25d_strike ~expiry ~spot in
          call_25d_vol -. put_25d_vol

let compute_bf25 vol_surface ~spot ~expiry ~rate ~dividend =
  (*
    BF25 = [IV(25Δ Call) + IV(25Δ Put)] / 2 - IV(ATM)

    Measures "wings" vs "body" of smile
    Positive BF25: fat tails (smile shape)
  *)
  let atm_vol = compute_atm_vol vol_surface ~spot ~expiry in

  match find_delta_strike Call ~target_delta:0.25 ~spot ~expiry ~rate ~dividend vol_surface with
  | None -> 0.0
  | Some call_25d_strike ->
      match find_delta_strike Put ~target_delta:(-0.25) ~spot ~expiry ~rate ~dividend vol_surface with
      | None -> 0.0
      | Some put_25d_strike ->
          let call_25d_vol = get_iv_from_surface vol_surface ~strike:call_25d_strike ~expiry ~spot in
          let put_25d_vol = get_iv_from_surface vol_surface ~strike:put_25d_strike ~expiry ~spot in
          ((call_25d_vol +. put_25d_vol) /. 2.0) -. atm_vol

let compute_skew_slope vol_surface ~spot ~expiry ~strike_range:(low_pct, high_pct) =
  (*
    Linear regression slope: IV vs strike

    Skew_Slope = [IV(90% Strike) - IV(110% Strike)] / 0.20

    Positive slope: put skew (IV decreases with strike)
  *)
  let low_strike = spot *. low_pct in
  let high_strike = spot *. high_pct in

  let low_iv = get_iv_from_surface vol_surface ~strike:low_strike ~expiry ~spot in
  let high_iv = get_iv_from_surface vol_surface ~strike:high_strike ~expiry ~spot in

  (* Slope per unit moneyness *)
  (low_iv -. high_iv) /. (high_pct -. low_pct)

(* ========================================================================== *)
(* Skew Observation *)
(* ========================================================================== *)

let compute_skew_observation vol_surface underlying_data ~rate ~expiry =
  let spot = underlying_data.spot_price in
  let dividend = underlying_data.dividend_yield in

  (* Compute all metrics *)
  let rr25 = compute_rr25 vol_surface ~spot ~expiry ~rate ~dividend in
  let bf25 = compute_bf25 vol_surface ~spot ~expiry ~rate ~dividend in
  let skew_slope = compute_skew_slope vol_surface ~spot ~expiry ~strike_range:(0.9, 1.1) in
  let atm_vol = compute_atm_vol vol_surface ~spot ~expiry in

  (* Get 25-delta strikes *)
  let call_25d_strike = match find_delta_strike Call ~target_delta:0.25 ~spot ~expiry ~rate ~dividend vol_surface with
    | Some k -> k
    | None -> spot *. 1.1
  in

  let put_25d_strike = match find_delta_strike Put ~target_delta:(-0.25) ~spot ~expiry ~rate ~dividend vol_surface with
    | Some k -> k
    | None -> spot *. 0.9
  in

  let call_25d_vol = get_iv_from_surface vol_surface ~strike:call_25d_strike ~expiry ~spot in
  let put_25d_vol = get_iv_from_surface vol_surface ~strike:put_25d_strike ~expiry ~spot in

  {
    timestamp = Unix.time ();
    ticker = underlying_data.ticker;
    expiry;
    rr25;
    bf25;
    skew_slope;
    atm_vol;
    put_25d_vol;
    call_25d_vol;
    put_25d_strike;
    call_25d_strike;
  }

(* ========================================================================== *)
(* Time Series *)
(* ========================================================================== *)

let compute_skew_time_series ~vol_surface_data ~underlying_data ~rate ~expiry =
  Array.map (fun (timestamp, surface) ->
    let obs = compute_skew_observation surface underlying_data ~rate ~expiry in
    { obs with timestamp }
  ) vol_surface_data

(* ========================================================================== *)
(* Statistics *)
(* ========================================================================== *)

let get_metric_values observations ~metric =
  Array.map (fun (obs : skew_observation) ->
    match metric with
    | "rr25" -> obs.rr25
    | "bf25" -> obs.bf25
    | "slope" -> obs.skew_slope
    | "atm_vol" -> obs.atm_vol
    | _ -> 0.0
  ) observations

let skew_statistics observations ~metric =
  let values = get_metric_values observations ~metric in
  let n = Array.length values in

  if n < 2 then (0.0, 0.0, 0.0, 0.0)
  else begin
    (* Mean *)
    let sum = Array.fold_left (+.) 0.0 values in
    let mean = sum /. float_of_int n in

    (* Standard deviation *)
    let sum_sq_dev = Array.fold_left (fun acc v ->
      let dev = v -. mean in
      acc +. dev *. dev
    ) 0.0 values in
    let std = sqrt (sum_sq_dev /. float_of_int (n - 1)) in

    (* Percentiles *)
    let sorted = Array.copy values in
    Array.sort compare sorted;

    let p25_idx = n / 4 in
    let p75_idx = (3 * n) / 4 in

    let p25 = sorted.(p25_idx) in
    let p75 = sorted.(p75_idx) in

    (mean, std, p25, p75)
  end

let compute_z_score observations ~current_value ~metric =
  let (mean, std, _, _) = skew_statistics observations ~metric in
  if std > 0.0 then
    (current_value -. mean) /. std
  else
    0.0

(* ========================================================================== *)
(* Regime Detection *)
(* ========================================================================== *)

let detect_regime_change observations ~window ~threshold =
  (*
    Detect regime shifts using rolling z-score

    z = (value_t - mean_rolling) / std_rolling

    Regime change if |z| > threshold
  *)
  let n = Array.length observations in
  if n < window + 1 then Array.make n false
  else begin
    Array.init n (fun i ->
      if i < window then false
      else begin
        (* Compute rolling statistics *)
        let window_values = Array.sub observations (i - window) window in
        let values = get_metric_values window_values ~metric:"rr25" in

        let sum = Array.fold_left (+.) 0.0 values in
        let mean = sum /. float_of_int window in

        let sum_sq_dev = Array.fold_left (fun acc v ->
          let dev = v -. mean in
          acc +. dev *. dev
        ) 0.0 values in
        let std = sqrt (sum_sq_dev /. float_of_int window) in

        (* Current z-score *)
        let current_value = observations.(i).rr25 in
        let z_score = if std > 0.0 then abs_float ((current_value -. mean) /. std) else 0.0 in

        z_score > threshold
      end
    )
  end

(** Regime detection based on rolling volatility *)

open Types

(** Calculate annualized realized volatility from returns
    Uses 252 trading days per year for annualization *)
let realized_volatility ~returns ~window_days =
  let n = Array.length returns in
  if n < window_days then
    failwith "Not enough data for volatility calculation"
  else
    (* Take the last window_days returns *)
    let recent_returns = Array.sub returns (n - window_days) window_days in

    (* Calculate standard deviation *)
    let mean =
      Array.fold_left (+.) 0.0 recent_returns /. float_of_int window_days
    in
    let variance =
      Array.fold_left
        (fun acc r ->
          let dev = r -. mean in
          acc +. (dev *. dev))
        0.0
        recent_returns
      /. float_of_int window_days
    in
    let daily_vol = sqrt variance in

    (* Annualize: multiply by sqrt(252) *)
    daily_vol *. sqrt 252.0

(** Calculate percentile from a historical distribution *)
let percentile ~values ~p =
  let n = Array.length values in
  if n = 0 then failwith "Cannot calculate percentile of empty array"
  else
    let sorted = Array.copy values in
    Array.sort compare sorted;
    let idx = int_of_float (float_of_int n *. p) in
    let idx = min idx (n - 1) in
    sorted.(idx)

(** Calculate stress regime weight with smooth transition
    Returns a value in [0, 1] where:
    - 0 = calm regime (vol below lower bound)
    - 1 = stress regime (vol above upper bound)
    - linear interpolation in between *)
let stress_weight ~current_vol ~lower_pct ~upper_pct =
  if current_vol <= lower_pct then 0.0
  else if current_vol >= upper_pct then 1.0
  else
    (* Linear ramp between bounds *)
    (current_vol -. lower_pct) /. (upper_pct -. lower_pct)

(** Detect regime state from benchmark returns
    Uses trailing 3-5 year lookback for percentile calculation
    Uses 20-day window for current volatility *)
let detect_regime
    ~benchmark_returns
    ~lookback_years
    ~vol_window_days
    ~lower_percentile
    ~upper_percentile =

  let n = Array.length benchmark_returns in
  let lookback_days = lookback_years * 252 in

  if n < lookback_days then
    failwith "Not enough benchmark history for regime detection"
  else
    (* Calculate rolling 20-day volatilities over the lookback period *)
    let num_windows = lookback_days - vol_window_days + 1 in
    let historical_vols = Array.make num_windows 0.0 in

    for i = 0 to num_windows - 1 do
      let window_returns =
        Array.sub benchmark_returns i vol_window_days
      in
      let mean =
        Array.fold_left (+.) 0.0 window_returns /. float_of_int vol_window_days
      in
      let variance =
        Array.fold_left
          (fun acc r ->
            let dev = r -. mean in
            acc +. (dev *. dev))
          0.0
          window_returns
        /. float_of_int vol_window_days
      in
      let daily_vol = sqrt variance in
      historical_vols.(i) <- daily_vol *. sqrt 252.0
    done;

    (* Get percentile bounds from historical distribution *)
    let lower_bound = percentile ~values:historical_vols ~p:lower_percentile in
    let upper_bound = percentile ~values:historical_vols ~p:upper_percentile in

    (* Calculate current volatility *)
    let current_vol =
      realized_volatility ~returns:benchmark_returns ~window_days:vol_window_days
    in

    (* Calculate stress weight *)
    let stress_wt =
      stress_weight ~current_vol ~lower_pct:lower_bound ~upper_pct:upper_bound
    in

    {
      volatility = current_vol;
      stress_weight = stress_wt;
      is_stress = stress_wt > 0.5;  (* Convention: >50% stress weight = stress *)
    }

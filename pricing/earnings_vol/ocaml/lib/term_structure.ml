(** IV Term Structure Analysis *)

open Types

(** Calculate term structure slope between front and back month *)
let calculate_slope (observations : iv_observation array) : float =
  let n = Array.length observations in
  if n < 2 then 0.0
  else
    (* Front month: nearest expiration *)
    let front = observations.(0) in
    (* Back month: find closest to 45 days *)
    let back = Array.fold_left (fun acc obs ->
      let current_diff = abs (obs.days_to_expiry - 45) in
      let acc_diff = abs (acc.days_to_expiry - 45) in
      if current_diff < acc_diff then obs else acc
    ) observations.(n-1) observations in
    
    (* Slope = Front IV - Back IV (negative = backwardation) *)
    front.atm_iv -. back.atm_iv

(** Calculate term structure ratio *)
let calculate_ratio (observations : iv_observation array) : float =
  let n = Array.length observations in
  if n < 2 then 1.0
  else
    let front = observations.(0) in
    let back = Array.fold_left (fun acc obs ->
      let current_diff = abs (obs.days_to_expiry - 45) in
      let acc_diff = abs (acc.days_to_expiry - 45) in
      if current_diff < acc_diff then obs else acc
    ) observations.(n-1) observations in
    
    if back.atm_iv > 0.0 then
      front.atm_iv /. back.atm_iv
    else 1.0

(** Build term structure from observations *)
let build_term_structure ~ticker ~observations : iv_term_structure =
  let n = Array.length observations in
  if n = 0 then
    {
      ticker;
      observations = [||];
      front_month_iv = 0.0;
      back_month_iv = 0.0;
      term_structure_slope = 0.0;
      term_structure_ratio = 1.0;
    }
  else
    let slope = calculate_slope observations in
    let ratio = calculate_ratio observations in
    let front_iv = observations.(0).atm_iv in
    let back = Array.fold_left (fun acc obs ->
      let current_diff = abs (obs.days_to_expiry - 45) in
      let acc_diff = abs (acc.days_to_expiry - 45) in
      if current_diff < acc_diff then obs else acc
    ) observations.(n-1) observations in
    
    {
      ticker;
      observations;
      front_month_iv = front_iv;
      back_month_iv = back.atm_iv;
      term_structure_slope = slope;
      term_structure_ratio = ratio;
    }

(** Calculate realized volatility from price series *)
let calculate_realized_vol ~prices ~annualization_factor : realized_vol =
  let n = Array.length prices in
  if n < 2 then
    { ticker = ""; lookback_days = 0; rv = 0.0; variance = 0.0 }
  else
    (* Calculate log returns *)
    let returns = Array.init (n - 1) (fun i ->
      log (prices.(i + 1) /. prices.(i))
    ) in
    
    (* Calculate variance *)
    let mean_return = Array.fold_left (+.) 0.0 returns /. float_of_int (Array.length returns) in
    let sum_sq_dev = Array.fold_left (fun acc r ->
      let dev = r -. mean_return in
      acc +. (dev *. dev)
    ) 0.0 returns in
    let variance = sum_sq_dev /. float_of_int (Array.length returns - 1) in
    
    (* Annualize *)
    let annualized_variance = variance *. annualization_factor in
    let rv = sqrt annualized_variance in
    
    {
      ticker = "";
      lookback_days = n;
      rv;
      variance = annualized_variance;
    }

(** Calculate IV/RV ratio *)
let calculate_iv_rv_ratio ~implied_vol ~realized_vol : iv_rv_ratio =
  let ratio = if realized_vol.rv > 0.0 then
    implied_vol /. realized_vol.rv
  else 1.0 in
  
  {
    ticker = realized_vol.ticker;
    implied_vol_30d = implied_vol;
    realized_vol_30d = realized_vol.rv;
    iv_rv_ratio = ratio;
    iv_minus_rv = implied_vol -. realized_vol.rv;
  }

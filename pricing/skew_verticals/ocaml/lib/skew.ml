(** Volatility Skew Calculator *)

open Types

(** Find option closest to target delta *)
let find_option_by_delta ~(options : option_data array) ~(target_delta : float) : option_data option =
  if Array.length options = 0 then None
  else
    let closest = Array.fold_left (fun acc opt ->
      let curr_diff = abs_float (opt.delta -. target_delta) in
      let acc_diff = abs_float (acc.delta -. target_delta) in
      if curr_diff < acc_diff then opt else acc
    ) options.(0) options in
    Some closest

(** Calculate call skew: (ATM_IV - 25Δ_Call_IV) / ATM_IV *)
let calculate_call_skew ~(calls : option_data array) ~(atm_iv : float) : float =
  match find_option_by_delta ~options:calls ~target_delta:0.25 with
  | None -> 0.0
  | Some call_25d ->
      if atm_iv > 0.0 then
        (atm_iv -. call_25d.implied_vol) /. atm_iv
      else 0.0

(** Calculate put skew: (ATM_IV - 25Δ_Put_IV) / ATM_IV *)
let calculate_put_skew ~(puts : option_data array) ~(atm_iv : float) : float =
  match find_option_by_delta ~options:puts ~target_delta:0.25 with
  | None -> 0.0
  | Some put_25d ->
      if atm_iv > 0.0 then
        (atm_iv -. put_25d.implied_vol) /. atm_iv
      else 0.0

(** Calculate z-score from historical skew series *)
let calculate_zscore ~(current : float) ~(history : float array) : float =
  let n = Array.length history in
  if n < 2 then 0.0
  else
    let mean = Array.fold_left (+.) 0.0 history /. float_of_int n in
    let variance =
      Array.fold_left (fun acc x ->
        let dev = x -. mean in
        acc +. (dev *. dev)
      ) 0.0 history /. float_of_int (n - 1)
    in
    let std = sqrt variance in
    if std > 0.0 then
      (current -. mean) /. std
    else 0.0

(** Compute skew metrics *)
let compute_skew_metrics
    ~(ticker : string)
    ~(calls : option_data array)
    ~(puts : option_data array)
    ~(atm_iv : float)
    ~(realized_vol : float)
    ~(call_skew_history : float array)
    ~(put_skew_history : float array)
    : skew_metrics =

  (* Calculate current skew *)
  let call_skew = calculate_call_skew ~calls ~atm_iv in
  let put_skew = calculate_put_skew ~puts ~atm_iv in

  (* Calculate z-scores *)
  let call_skew_zscore = calculate_zscore ~current:call_skew ~history:call_skew_history in
  let put_skew_zscore = calculate_zscore ~current:put_skew ~history:put_skew_history in

  (* Find 25 delta IVs *)
  let call_25d_iv = match find_option_by_delta ~options:calls ~target_delta:0.25 with
    | None -> atm_iv
    | Some opt -> opt.implied_vol
  in

  let put_25d_iv = match find_option_by_delta ~options:puts ~target_delta:0.25 with
    | None -> atm_iv
    | Some opt -> opt.implied_vol
  in

  (* Variance risk premium *)
  let vrp = atm_iv -. realized_vol in

  {
    ticker;
    date = "";  (* Will be filled by caller *)
    call_skew;
    call_skew_zscore;
    put_skew;
    put_skew_zscore;
    atm_iv;
    atm_call_25delta_iv = call_25d_iv;
    atm_put_25delta_iv = put_25d_iv;
    realized_vol_30d = realized_vol;
    vrp;
  }

(** Print skew metrics *)
let print_skew_metrics (skew : skew_metrics) : unit =
  Printf.printf "\n=== Skew Metrics: %s ===\n" skew.ticker;
  Printf.printf "ATM IV: %.2f%%\n" (skew.atm_iv *. 100.0);
  Printf.printf "Realized Vol (30d): %.2f%%\n" (skew.realized_vol_30d *. 100.0);
  Printf.printf "VRP: %.2f%%\n" (skew.vrp *. 100.0);
  Printf.printf "\nCall Skew: %.4f (z-score: %.2f)\n" skew.call_skew skew.call_skew_zscore;
  Printf.printf "  ATM IV: %.2f%% | 25Δ Call IV: %.2f%%\n"
    (skew.atm_iv *. 100.0) (skew.atm_call_25delta_iv *. 100.0);
  Printf.printf "\nPut Skew: %.4f (z-score: %.2f)\n" skew.put_skew skew.put_skew_zscore;
  Printf.printf "  ATM IV: %.2f%% | 25Δ Put IV: %.2f%%\n"
    (skew.atm_iv *. 100.0) (skew.atm_put_25delta_iv *. 100.0);

  if skew.call_skew_zscore < -2.0 then
    Printf.printf "\n✓ EXTREME CALL SKEW (z < -2) - Potential sell opportunity\n"
  else if skew.put_skew_zscore < -2.0 then
    Printf.printf "\n✓ EXTREME PUT SKEW (z < -2) - Potential sell opportunity\n"

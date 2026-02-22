(* Gamma scalping simulation engine *)

open Types

(** Helper functions **)

(* Calculate time to expiry at current timestamp *)
let time_to_expiry ~current_time ~entry_time ~initial_expiry =
  let elapsed = current_time -. entry_time in
  max 0.0 (initial_expiry -. elapsed)

(* Extract recent returns for vol-adaptive hedging

   Returns log returns from the last 'lookback' observations
*)
let get_recent_returns ~prices ~current_index ~lookback =
  let start_idx = max 0 (current_index - lookback) in
  let count = current_index - start_idx in

  if count < 2 then
    [||]
  else
    Array.init count (fun i ->
      let idx = start_idx + i in
      if idx + 1 <= current_index then
        let (_, p1) = prices.(idx) in
        let (_, p2) = prices.(idx + 1) in
        log (p2 /. p1)
      else
        0.0
    )

(** Main simulation **)

let run_simulation
    ~position_type
    ~intraday_prices
    ~entry_iv
    ~iv_timeseries
    ~hedging_strategy
    ~config
    ~expiry =

  let n = Array.length intraday_prices in

  if n = 0 then
    failwith "Simulation.run_simulation: empty price array"
  else if expiry <= 0.0 then
    failwith "Simulation.run_simulation: expiry must be positive"
  else

  (* Entry conditions *)
  let (entry_time, entry_spot) = intraday_prices.(0) in

  (* Build initial position and calculate entry premium and Greeks *)
  let (entry_premium, entry_greeks) = Positions.position_greeks
    ~position_type
    ~spot:entry_spot
    ~expiry
    ~volatility:entry_iv
    ~rate:config.rate
    ~dividend:config.dividend
    ~contracts:config.contracts
  in

  (* Initialize tracking *)
  let hedge_log = ref [] in
  let pnl_snapshots = ref [] in
  let last_hedge_time = ref entry_time in
  let current_delta = ref entry_greeks.delta in

  (* Hedge position tracking:
     net_hedge_shares = cumulative shares from all hedges
     hedge_cash = cumulative cash flows from hedge trades
     hedge_pnl = hedge_cash + net_hedge_shares * current_spot *)
  let net_hedge_shares = ref 0.0 in
  let hedge_cash = ref 0.0 in

  (* Initial P&L snapshot *)
  let initial_snapshot = Pnl_attribution.initial_pnl_snapshot
    ~timestamp:entry_time
    ~spot_price:entry_spot
    ~entry_premium
  in
  pnl_snapshots := [initial_snapshot];

  (* Helper: Get IV at timestamp (use entry IV if no timeseries provided) *)
  let get_iv_at_time t =
    match iv_timeseries with
    | None -> entry_iv
    | Some iv_data ->
        (* Find closest IV by timestamp *)
        let rec find_closest idx best_idx best_diff =
          if idx >= Array.length iv_data then
            let (_, iv) = iv_data.(best_idx) in
            iv
          else
            let (ts, _iv) = iv_data.(idx) in
            let diff = abs_float (ts -. t) in
            if diff < best_diff then
              find_closest (idx + 1) idx diff
            else
              find_closest (idx + 1) best_idx best_diff
        in
        if Array.length iv_data = 0 then
          entry_iv
        else
          find_closest 0 0 infinity
  in

  (* Simulation loop *)
  for i = 1 to n - 1 do
    let (current_time, current_spot) = intraday_prices.(i) in
    let (prev_time, prev_spot) = intraday_prices.(i - 1) in

    (* Time to expiry *)
    let tte = time_to_expiry ~current_time ~entry_time ~initial_expiry:expiry in

    if tte > 0.0 then begin
      (* Get current IV *)
      let current_iv = get_iv_at_time current_time in
      let prev_iv = get_iv_at_time prev_time in

      (* Recalculate Greeks at current spot and time *)
      let (current_option_value, current_greeks) = Positions.position_greeks
        ~position_type
        ~spot:current_spot
        ~expiry:tte
        ~volatility:current_iv
        ~rate:config.rate
        ~dividend:config.dividend
        ~contracts:config.contracts
      in

      (* Update delta *)
      current_delta := current_greeks.delta;

      (* Check if hedging is needed *)
      let recent_returns = match hedging_strategy with
        | VolAdaptive _ -> Some (get_recent_returns ~prices:intraday_prices ~current_index:i ~lookback:20)
        | _ -> None
      in

      let should_hedge = Hedging.should_hedge
        ~strategy:hedging_strategy
        ~current_delta:!current_delta
        ~current_time
        ~last_hedge_time:!last_hedge_time
        ~recent_returns
      in

      (* Execute hedge if needed *)
      let hedge_cost = ref 0.0 in
      if should_hedge then begin
        let hedge_event = Hedging.execute_hedge
          ~timestamp:current_time
          ~spot_price:current_spot
          ~current_delta:!current_delta
          ~transaction_cost_bps:config.transaction_cost_bps
        in

        hedge_cost := hedge_event.hedge_cost;

        (* Update hedge position tracking *)
        net_hedge_shares := !net_hedge_shares +. hedge_event.hedge_quantity;
        hedge_cash := !hedge_cash -. hedge_event.hedge_quantity *. current_spot;

        (* Record hedge event *)
        hedge_log := hedge_event :: !hedge_log;

        (* Update tracking *)
        last_hedge_time := current_time;
        current_delta := 0.0;  (* Delta is now neutralized *)
      end;

      (* Calculate time step in days *)
      let time_step_days = current_time -. prev_time in

      (* Current hedge P&L: mark-to-market of stock hedge position *)
      let current_hedge_pnl = !hedge_cash +. !net_hedge_shares *. current_spot in

      (* Update P&L snapshot *)
      let prev_snapshot = List.hd !pnl_snapshots in
      let new_snapshot = Pnl_attribution.update_pnl_snapshot
        ~previous:prev_snapshot
        ~current_greeks
        ~spot_current:current_spot
        ~spot_previous:prev_spot
        ~time_step_days
        ~iv_current:current_iv
        ~iv_previous:prev_iv
        ~option_value_current:current_option_value
        ~entry_premium
        ~hedge_cost:!hedge_cost
        ~hedge_pnl_current:current_hedge_pnl
      in

      pnl_snapshots := new_snapshot :: !pnl_snapshots;
    end
  done;

  (* Reverse lists (they were built backwards) *)
  let hedge_log_array = Array.of_list (List.rev !hedge_log) in
  let pnl_timeseries_array = Array.of_list (List.rev !pnl_snapshots) in

  (* Extract final P&L *)
  let final_snapshot = pnl_timeseries_array.(Array.length pnl_timeseries_array - 1) in
  let final_pnl = final_snapshot.total_pnl in
  let gamma_pnl_total = final_snapshot.gamma_pnl in
  let theta_pnl_total = final_snapshot.theta_pnl in
  let vega_pnl_total = final_snapshot.vega_pnl in
  let hedge_pnl_total = final_snapshot.hedge_pnl in
  let total_transaction_costs = final_snapshot.transaction_costs in

  (* Calculate metrics *)
  let num_hedges = Array.length hedge_log_array in
  let sharpe_ratio = Pnl_attribution.calculate_sharpe_ratio ~pnl_timeseries:pnl_timeseries_array in
  let max_drawdown = Pnl_attribution.calculate_max_drawdown ~pnl_timeseries:pnl_timeseries_array in
  let win_rate = Pnl_attribution.calculate_win_rate ~pnl_timeseries:pnl_timeseries_array in

  (* Average hedge interval *)
  let avg_hedge_interval_minutes =
    if num_hedges <= 1 then
      0.0
    else
      let total_time_days = (fst intraday_prices.(n - 1)) -. (fst intraday_prices.(0)) in
      let total_time_minutes = total_time_days *. 24.0 *. 60.0 in
      total_time_minutes /. float_of_int num_hedges
  in

  (* Return simulation result *)
  {
    position = position_type;
    entry_premium;
    entry_iv;
    expiry;
    final_pnl;
    gamma_pnl_total;
    theta_pnl_total;
    vega_pnl_total;
    hedge_pnl_total;
    num_hedges;
    total_transaction_costs;
    sharpe_ratio;
    max_drawdown;
    win_rate;
    avg_hedge_interval_minutes;
    hedge_log = hedge_log_array;
    pnl_timeseries = pnl_timeseries_array;
  }

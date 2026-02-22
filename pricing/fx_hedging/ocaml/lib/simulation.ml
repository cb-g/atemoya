(* FX Hedge Backtesting Simulation *)

open Types

(** Simulation helpers **)

(* Calculate returns from price series *)
let calculate_returns ~prices =
  let n = Array.length prices in
  if n < 2 then [||]
  else
    Array.init (n - 1) (fun i ->
      if prices.(i) = 0.0 then 0.0
      else (prices.(i + 1) -. prices.(i)) /. prices.(i)
    )

(* Sharpe ratio *)
let sharpe_ratio ~returns ~risk_free_rate =
  let n = Array.length returns in
  if n < 2 then None
  else
    let mean_return = Array.fold_left (+.) 0.0 returns /. float_of_int n in
    let mean_sq = Array.fold_left (fun acc r ->
      let dev = r -. mean_return in
      acc +. dev *. dev
    ) 0.0 returns in
    let std = sqrt (mean_sq /. float_of_int (n - 1)) in

    if std = 0.0 then None
    else
      let excess_return = mean_return -. risk_free_rate /. 252.0 in  (* Daily risk-free rate *)
      Some ((excess_return /. std) *. sqrt 252.0)  (* Annualize *)

(* Maximum drawdown *)
let max_drawdown ~cumulative_pnl =
  let n = Array.length cumulative_pnl in
  if n = 0 then 0.0
  else
    let max_dd = ref 0.0 in
    let peak = ref cumulative_pnl.(0) in

    Array.iter (fun pnl ->
      if pnl > !peak then peak := pnl;
      let dd = (!peak -. pnl) /. (abs_float !peak +. 1.0) in  (* Add 1 to avoid div by 0 *)
      if dd > !max_dd then max_dd := dd
    ) cumulative_pnl;

    !max_dd

(* Win rate *)
let win_rate ~daily_pnl =
  let n = Array.length daily_pnl in
  if n = 0 then 0.0
  else
    let wins = Array.fold_left (fun acc pnl -> if pnl > 0.0 then acc + 1 else acc) 0 daily_pnl in
    float_of_int wins /. float_of_int n

(** Main simulation **)

(* Run hedge backtest *)
let run_hedge_backtest
    ~exposure_usd
    ~fx_rates
    ~futures_prices
    ~hedge_strategy
    ~futures
    ~initial_margin_balance
    ~transaction_cost_bps =

  let n_fx = Array.length fx_rates in
  let n_fut = Array.length futures_prices in

  if n_fx = 0 || n_fut = 0 then
    failwith "Simulation.run_hedge_backtest: empty price data"
  else if n_fx <> n_fut then
    failwith "Simulation.run_hedge_backtest: fx_rates and futures_prices must have same length"
  else

  (* Initial setup *)
  let (initial_time, _initial_fx) = fx_rates.(0) in
  let (_, initial_futures) = futures_prices.(0) in

  (* Determine hedge ratio and rebalance interval *)
  let hedge_ratio = match hedge_strategy with
    | Static { hedge_ratio } -> hedge_ratio
    | _ -> -1.0  (* Default full hedge *)
  in

  (* Rebalance every 20 trading days to keep hedge aligned with drifting exposure *)
  let rebalance_interval = match hedge_strategy with
    | Dynamic { rebalance_interval_days; _ } -> rebalance_interval_days
    | _ -> 20
  in

  let cost_per_contract fut_price =
    transaction_cost_bps /. 10000.0 *. fut_price *. (futures : futures_contract).contract_size
  in

  (* Build initial hedge *)
  let initial_hedge = Hedge_strategies.static_futures_hedge
    ~exposure_usd
    ~hedge_ratio
    ~futures
    ~entry_date:initial_time
  in

  (* Extract initial position size *)
  let hedge_quantity = match initial_hedge with
    | FuturesHedge { quantity; _ } -> quantity
    | _ -> 0
  in

  (* Initialize tracking *)
  let snapshots = ref [] in
  let total_transaction_costs = ref 0.0 in
  let num_rebalances = ref 0 in

  (* Charge initial trade cost *)
  let initial_cost = float_of_int (abs hedge_quantity) *. cost_per_contract initial_futures in
  total_transaction_costs := initial_cost;

  (* Margin account *)
  let margin = ref (Margin.create_margin_account
    ~cash_balance:initial_margin_balance
    ~initial_margin_required:(Margin.initial_margin ~futures ~quantity:hedge_quantity)
    ~maintenance_margin_required:(Margin.maintenance_margin ~futures ~quantity:hedge_quantity)
  ) in

  let current_position = ref hedge_quantity in
  (* Track entry price for P&L — resets on rebalance *)
  let entry_price = ref initial_futures in
  let realized_hedge_pnl = ref 0.0 in

  (* Simulation loop *)
  for i = 0 to n_fx - 1 do
    let (timestamp, fx_rate) = fx_rates.(i) in
    let (_, fut_price) = futures_prices.(i) in

    (* Calculate exposure value (changes with FX rate) *)
    let initial_fx_rate = snd fx_rates.(0) in
    let fx_change = if i = 0 then 0.0 else (fx_rate -. initial_fx_rate) /. initial_fx_rate in
    let exposure_value = exposure_usd *. (1.0 +. fx_change) in

    (* Calculate hedge value: realized P&L from closed legs + unrealized from current *)
    let unrealized_pnl = if i = 0 then 0.0 else
      Futures.futures_pnl
        ~entry_price:!entry_price
        ~current_price:fut_price
        ~contract_size:futures.contract_size
        ~quantity:!current_position
    in
    let hedge_pnl = !realized_hedge_pnl +. unrealized_pnl in

    (* Net value (exposure + hedge) *)
    let net_value = exposure_value +. hedge_pnl in

    (* Calculate unhedged and hedged P&L *)
    let unhedged_pnl = exposure_value -. exposure_usd in
    let hedged_pnl = net_value -. exposure_usd -. !total_transaction_costs in

    (* Update margin (daily settlement) *)
    if i > 0 then begin
      let (_, prev_fut) = futures_prices.(i - 1) in
      let var_margin = Futures.variation_margin
        ~settlement_yesterday:prev_fut
        ~settlement_today:fut_price
        ~contract_size:futures.contract_size
        ~quantity:!current_position
      in
      margin := Margin.update_margin_account ~account:!margin ~variation_margin:var_margin
    end;

    (* Periodic rebalancing: recalculate contracts needed for current exposure *)
    if i > 0 && i mod rebalance_interval = 0 then begin
      let target_contracts = Exposure_analysis.futures_contracts_needed
        ~exposure_usd:exposure_value
        ~hedge_ratio
        ~futures_price:fut_price
        ~contract_size:futures.contract_size
      in
      let delta = target_contracts - !current_position in
      if delta <> 0 then begin
        (* Close out old position's unrealized P&L *)
        realized_hedge_pnl := !realized_hedge_pnl +. unrealized_pnl;
        entry_price := fut_price;
        let rebal_cost = float_of_int (abs delta) *. cost_per_contract fut_price in
        total_transaction_costs := !total_transaction_costs +. rebal_cost;
        current_position := target_contracts;
        num_rebalances := !num_rebalances + 1;
        margin := Margin.create_margin_account
          ~cash_balance:!margin.cash_balance
          ~initial_margin_required:(Margin.initial_margin ~futures ~quantity:target_contracts)
          ~maintenance_margin_required:(Margin.maintenance_margin ~futures ~quantity:target_contracts)
      end
    end;

    (* Record snapshot *)
    let snapshot = {
      timestamp;
      spot_rate = fx_rate;
      futures_price = fut_price;
      exposure_value;
      hedge_value = hedge_pnl;
      net_value;
      unhedged_pnl;
      hedged_pnl;
      margin_balance = !margin.cash_balance;
      cumulative_costs = !total_transaction_costs;
      futures_position = float_of_int !current_position;
    } in
    snapshots := snapshot :: !snapshots;
  done;

  (* Extract final values *)
  let snapshots_array = Array.of_list (List.rev !snapshots) in
  let final_snapshot = snapshots_array.(n_fx - 1) in

  (* Calculate metrics *)
  let unhedged_returns = calculate_returns
    ~prices:(Array.map (fun s -> s.exposure_value) snapshots_array)
  in
  let hedged_returns = calculate_returns
    ~prices:(Array.map (fun s -> s.net_value) snapshots_array)
  in

  let sharpe_unhedged = sharpe_ratio ~returns:unhedged_returns ~risk_free_rate:0.05 in
  let sharpe_hedged = sharpe_ratio ~returns:hedged_returns ~risk_free_rate:0.05 in

  let max_dd_unhedged = max_drawdown
    ~cumulative_pnl:(Array.map (fun s -> s.unhedged_pnl) snapshots_array)
  in
  let max_dd_hedged = max_drawdown
    ~cumulative_pnl:(Array.map (fun s -> s.hedged_pnl) snapshots_array)
  in

  let effectiveness = Optimization.hedge_effectiveness_ratio
    ~unhedged_returns
    ~hedged_returns
  in

  (* Return results *)
  let result = {
    unhedged_pnl = final_snapshot.unhedged_pnl;
    hedged_pnl = final_snapshot.hedged_pnl;
    hedge_pnl = final_snapshot.hedge_value;
    transaction_costs = !total_transaction_costs;
    num_rebalances = !num_rebalances;
    hedge_effectiveness = effectiveness;
    sharpe_unhedged;
    sharpe_hedged;
    max_drawdown_unhedged = max_dd_unhedged;
    max_drawdown_hedged = max_dd_hedged;
  } in
  (result, snapshots_array)

(* Run options backtest (simplified - similar structure) *)
let run_options_backtest
    ~exposure_usd
    ~fx_rates
    ~futures_prices
    ~hedge_strategy
    ~option
    ~initial_margin_balance
    ~transaction_cost_bps =

  (* For now, use similar logic to futures backtest *)
  (* TODO: Add proper options theta decay and Greeks updates *)

  let futures = option.underlying_futures in
  run_hedge_backtest
    ~exposure_usd
    ~fx_rates
    ~futures_prices
    ~hedge_strategy
    ~futures
    ~initial_margin_balance
    ~transaction_cost_bps

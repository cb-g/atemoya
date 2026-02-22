(* Hedge Strategies Implementation *)

open Types

(** Static hedging **)

(* Build static futures hedge *)
let static_futures_hedge ~exposure_usd ~hedge_ratio ~(futures : futures_contract) ~entry_date =
  let quantity = Exposure_analysis.futures_contracts_needed
    ~exposure_usd
    ~hedge_ratio
    ~futures_price:futures.futures_price
    ~contract_size:futures.contract_size
  in

  FuturesHedge {
    futures;
    quantity;
    entry_price = futures.futures_price;
    entry_date;
  }

(* Build static options hedge *)
let static_options_hedge ~exposure_usd ~hedge_ratio ~option ~entry_date =
  (* Calculate option delta *)
  let greeks = Futures_options.black_greeks
    ~option_type:option.option_type
    ~futures_price:option.underlying_futures.futures_price
    ~strike:option.strike
    ~expiry:option.expiry
    ~rate:0.05  (* Default rate *)
    ~volatility:option.volatility
  in

  let quantity = Exposure_analysis.options_contracts_needed
    ~exposure_usd
    ~hedge_ratio
    ~option_delta:greeks.delta
    ~futures_price:option.underlying_futures.futures_price
    ~contract_size:option.underlying_futures.contract_size
  in

  OptionsHedge {
    option;
    quantity;
    entry_premium = option.premium;
    entry_date;
  }

(** Dynamic hedging **)

(* Check if rebalancing is needed *)
let should_rebalance ~strategy ~current_delta ~target_delta ~last_rebalance_date ~current_date =
  match strategy with
  | Static _ ->
      false  (* Static hedge: never rebalance *)

  | Dynamic { rebalance_threshold; rebalance_interval_days; _ } ->
      (* Check delta threshold *)
      let delta_drift = abs_float (current_delta -. target_delta) in
      let threshold_breached = delta_drift > rebalance_threshold in

      (* Check time interval *)
      let days_elapsed = (current_date -. last_rebalance_date) *. 365.0 in
      let interval_breached = days_elapsed >= float_of_int rebalance_interval_days in

      threshold_breached || interval_breached

  | MinimumVariance _ ->
      false  (* Min variance: set once, don't rebalance frequently *)

  | OptimalCost _ ->
      false  (* Optimal cost: set once *)

(* Calculate rebalancing trade size

   Goal: Adjust position to achieve target delta

   Current Delta = Current_Position × Delta_per_Contract
   Target Delta = (Current_Position + Trade) × Delta_per_Contract

   Solve for Trade
*)
let rebalance_size ~current_position:_ ~current_delta ~target_delta ~exposure_usd ~futures_price ~contract_size =
  (* For futures, delta per contract ≈ futures_price × contract_size / exposure *)
  let delta_per_contract = (futures_price *. contract_size) /. exposure_usd in

  if abs_float delta_per_contract < 0.001 then
    0  (* Avoid division by zero *)
  else
    let delta_gap = target_delta -. current_delta in
    let contracts_needed = delta_gap /. delta_per_contract in

    (* Round to nearest integer *)
    int_of_float (contracts_needed +. (if contracts_needed >= 0.0 then 0.5 else -0.5))

(** Hedge evaluation **)

(* Calculate current delta of hedge *)
let hedge_delta ~hedge ~current_futures_price ~current_rate =
  match hedge with
  | FuturesHedge { futures; quantity; _ } ->
      (* Futures delta ≈ 1.0 per contract *)
      let notional_per_contract = current_futures_price *. futures.contract_size in
      float_of_int quantity *. notional_per_contract

  | OptionsHedge { option; quantity; _ } ->
      (* Calculate option delta *)
      let time_remaining = option.expiry in  (* Simplified - should decay over time *)
      if time_remaining <= 0.0 then
        0.0
      else
        let greeks = Futures_options.black_greeks
          ~option_type:option.option_type
          ~futures_price:current_futures_price
          ~strike:option.strike
          ~expiry:time_remaining
          ~rate:current_rate
          ~volatility:option.volatility
        in
        greeks.delta *. float_of_int quantity *. current_futures_price *. option.underlying_futures.contract_size

(* Hedge effectiveness

   R² = 1 - Var(hedged) / Var(unhedged)
*)
let hedge_effectiveness ~unhedged_returns ~hedged_returns =
  let n_unhedged = Array.length unhedged_returns in
  let n_hedged = Array.length hedged_returns in

  if n_unhedged = 0 || n_hedged = 0 then
    0.0
  else
    (* Calculate variance *)
    let variance returns =
      let n = Array.length returns in
      let mean = Array.fold_left (+.) 0.0 returns /. float_of_int n in
      let sum_sq_dev = Array.fold_left (fun acc r ->
        let dev = r -. mean in
        acc +. dev *. dev
      ) 0.0 returns in
      sum_sq_dev /. float_of_int n
    in

    let var_unhedged = variance unhedged_returns in
    let var_hedged = variance hedged_returns in

    if var_unhedged = 0.0 then
      0.0
    else
      1.0 -. (var_hedged /. var_unhedged)

(* Calculate hedge P&L *)
let hedge_pnl ~hedge ~current_futures_price ~current_rate =
  match hedge with
  | FuturesHedge { futures; quantity; entry_price; _ } ->
      Futures.futures_pnl
        ~entry_price
        ~current_price:current_futures_price
        ~contract_size:futures.contract_size
        ~quantity

  | OptionsHedge { option; quantity; entry_premium; _ } ->
      let time_remaining = option.expiry in  (* Simplified *)
      if time_remaining <= 0.0 then
        (* At expiry: intrinsic value - premium paid *)
        let intrinsic = Futures_options.intrinsic_value
          ~option_type:option.option_type
          ~futures_price:current_futures_price
          ~strike:option.strike
        in
        (intrinsic -. entry_premium) *. option.underlying_futures.contract_size *. float_of_int quantity
      else
        (* Before expiry: current value - premium paid *)
        let current_premium = Futures_options.black_price
          ~option_type:option.option_type
          ~futures_price:current_futures_price
          ~strike:option.strike
          ~expiry:time_remaining
          ~rate:current_rate
          ~volatility:option.volatility
        in
        (current_premium -. entry_premium) *. option.underlying_futures.contract_size *. float_of_int quantity

(** Roll management **)

(* Should roll futures contract? *)
let should_roll ~(futures : futures_contract) ~current_date:_ ~days_before_expiry =
  let time_to_expiry = futures.expiry in
  let days_to_expiry = time_to_expiry *. 365.0 in
  days_to_expiry <= float_of_int days_before_expiry

(* Execute roll to next contract *)
let roll_futures ~current_position ~new_futures ~current_date =
  match current_position with
  | FuturesHedge { futures; quantity; entry_price = _; entry_date = _ } ->
      (* Create new hedge position *)
      let new_hedge = FuturesHedge {
        futures = new_futures;
        quantity;
        entry_price = new_futures.futures_price;
        entry_date = current_date;
      } in

      (* Create roll event *)
      let roll = {
        timestamp = current_date;
        from_contract = futures.contract_month;
        to_contract = new_futures.contract_month;
        from_price = futures.futures_price;
        to_price = new_futures.futures_price;
        roll_cost = Futures.roll_cost
          ~futures_near:futures.futures_price
          ~futures_far:new_futures.futures_price
          ~contract_size:futures.contract_size
          ~quantity;
        quantity;
      } in

      (new_hedge, roll)

  | OptionsHedge _ ->
      failwith "Hedge_strategies.roll_futures: cannot roll options position"

(** Portfolio hedging **)

(* Build multi-currency hedge *)
let build_multi_currency_hedge ~exposures ~hedge_strategy ~futures_contracts ~entry_date =
  let hedge_ratio = match hedge_strategy with
    | Static { hedge_ratio } -> hedge_ratio
    | _ -> -1.0  (* Default to full hedge *)
  in

  Array.map (fun exp ->
    (* Find matching futures contract *)
    let matching_futures = Array.find_opt (fun fut ->
      fut.underlying.base = exp.currency
    ) futures_contracts in

    match matching_futures with
    | Some futures ->
        static_futures_hedge
          ~exposure_usd:exp.net_exposure_usd
          ~hedge_ratio
          ~futures
          ~entry_date
    | None ->
        failwith (Printf.sprintf "No futures contract found for %s"
          (currency_to_string exp.currency))
  ) exposures

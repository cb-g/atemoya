(** Portfolio optimization using spec-compliant LP solver *)

open Types

(** Calculate turnover between two weight vectors *)
let calculate_turnover ~current_weights ~new_weights =
  let all_tickers =
    List.sort_uniq compare
      (List.map fst current_weights.assets @ List.map fst new_weights.assets)
  in

  let asset_turnover =
    List.fold_left (fun acc ticker ->
      let current_w =
        match List.assoc_opt ticker current_weights.assets with
        | Some w -> w
        | None -> 0.0
      in
      let new_w =
        match List.assoc_opt ticker new_weights.assets with
        | Some w -> w
        | None -> 0.0
      in
      acc +. abs_float (new_w -. current_w)
    ) 0.0 all_tickers
  in

  let cash_turnover = abs_float (new_weights.cash -. current_weights.cash) in
  (asset_turnover +. cash_turnover) /. 2.0

(** Calculate transaction costs *)
let calculate_transaction_costs ~current_weights ~new_weights ~cost_bps =
  let turnover = calculate_turnover ~current_weights ~new_weights in
  turnover *. (cost_bps /. 10000.0)

(** Calculate portfolio returns given weights and asset returns *)
let calculate_portfolio_returns
    ~(weights : weights)
    ~(asset_returns_list : return_series list) : float array =
  let n_periods = Array.length (List.hd asset_returns_list).returns in
  let portfolio_returns = Array.make n_periods 0.0 in

  for t = 0 to n_periods - 1 do
    let period_return = ref 0.0 in

    List.iter (fun (return_series : return_series) ->
      let weight =
        match List.assoc_opt return_series.ticker weights.assets with
        | Some w -> w
        | None -> 0.0
      in
      period_return := !period_return +. (weight *. return_series.returns.(t))
    ) asset_returns_list;

    portfolio_returns.(t) <- !period_return
  done;

  portfolio_returns

(** Optimize portfolio weights using spec-compliant LP solver *)
let optimize
    ~params
    ~current_weights
    ~asset_returns_list
    ~benchmark_returns
    ~asset_betas
    ~regime
    ?n_random_starts:_
    ?n_gradient_refine:_
    () =

  (* Build LP problem *)
  let lp_problem =
    Lp_formulation.build_problem
      ~asset_returns_list
      ~benchmark_returns
      ~current_weights
      ~asset_betas
      ~params
      ~stress_weight:regime.stress_weight
  in

  (* Solve LP *)
  let lp_solution = Lp_formulation.solve_lp lp_problem in

  (* Convert solution back to weights format *)
  let tickers = Scenarios.get_tickers_ordered asset_returns_list in
  let assets = List.mapi (fun i ticker ->
    (ticker, lp_solution.asset_weights.(i))
  ) tickers in

  let final_weights = {
    assets;
    cash = lp_solution.cash_weight;
  } in

  (* Calculate risk metrics for output *)
  let portfolio_returns =
    calculate_portfolio_returns ~weights:final_weights ~asset_returns_list
  in
  let active_returns =
    Array.map2 (fun p b -> p -. b) portfolio_returns benchmark_returns
  in

  let risk_metrics =
    Risk.calculate_risk_metrics
      ~threshold:params.lpm1_threshold
      ~active_returns
      ~weights:final_weights
      ~asset_betas
  in

  let transaction_costs =
    calculate_transaction_costs
      ~current_weights
      ~new_weights:final_weights
      ~cost_bps:params.transaction_cost_bps
  in

  {
    weights = final_weights;
    objective_value = lp_solution.objective_value;
    risk_metrics;
    turnover = lp_solution.turnover;
    transaction_costs;
  }

(** Optimize portfolio twice: frictionless and constrained *)
let optimize_dual
    ~params
    ~current_weights
    ~asset_returns_list
    ~benchmark_returns
    ~asset_betas
    ~regime
    ?(n_random_starts=30)
    ?(n_gradient_refine=10)
    () =

  (* 1. Frictionless optimization (no turnover penalty) *)
  let frictionless_params = {
    params with
    turnover_penalty = 0.0;
    transaction_cost_bps = 0.0;
  } in

  let frictionless_result =
    optimize
      ~params:frictionless_params
      ~current_weights
      ~asset_returns_list
      ~benchmark_returns
      ~asset_betas
      ~regime
      ~n_random_starts
      ~n_gradient_refine
      ()
  in

  (* 2. Constrained optimization (with turnover penalty) *)
  let constrained_result =
    optimize
      ~params
      ~current_weights
      ~asset_returns_list
      ~benchmark_returns
      ~asset_betas
      ~regime
      ~n_random_starts
      ~n_gradient_refine
      ()
  in

  (* 3. Compute gap metrics *)
  let gap_distance =
    calculate_turnover
      ~current_weights:constrained_result.weights
      ~new_weights:frictionless_result.weights
  in

  let gap_lpm1 =
    constrained_result.risk_metrics.lpm1 -. frictionless_result.risk_metrics.lpm1
  in

  let gap_cvar =
    constrained_result.risk_metrics.cvar_95 -. frictionless_result.risk_metrics.cvar_95
  in

  let gap_beta =
    constrained_result.risk_metrics.portfolio_beta -. frictionless_result.risk_metrics.portfolio_beta
  in

  {
    frictionless = frictionless_result;
    constrained = constrained_result;
    gap_distance;
    gap_lpm1;
    gap_cvar;
    gap_beta;
  }

(** Decide whether to rebalance based on objective improvement *)
let should_rebalance
    ~current_result
    ~proposed_result
    ~threshold =

  let improvement = current_result.objective_value -. proposed_result.objective_value in

  let should_rebalance = improvement >= threshold in
  let reason =
    if should_rebalance then
      Printf.sprintf "Objective improvement %.6f >= threshold %.6f" improvement threshold
    else
      Printf.sprintf "Objective improvement %.6f < threshold %.6f" improvement threshold
  in

  {
    should_rebalance;
    reason;
    objective_improvement = improvement;
    current_objective = current_result.objective_value;
    proposed_objective = proposed_result.objective_value;
  }

(** LP formulation per specification *)

open Types

(** LP problem data structure *)
type lp_problem = {
  (* Problem dimensions *)
  n_assets : int;
  n_scenarios : int;  (* T weekly scenarios *)

  (* Scenario data *)
  asset_scenarios : float array array;  (* R[t,i]: T x N matrix *)
  benchmark_scenarios : float array;    (* b[t]: T vector *)
  cash_scenarios : float array;         (* r^c[t]: T vector *)

  (* Previous weights *)
  prev_weights : float array;  (* N assets *)
  prev_cash : float;

  (* Beta estimates *)
  asset_betas : float array;  (* N *)

  (* Regime state *)
  stress_weight : float;  (* s in [0,1] *)

  (* Hyperparameters *)
  lambda_lpm1 : float;
  lambda_cvar : float;
  lambda_beta : float;
  kappa : float;  (* c + gamma (combined cost + turnover penalty) *)
  lpm_threshold : float;  (* tau < 0 *)
  cvar_alpha : float;  (* 0.95 *)
  beta_target : float;  (* 0.65 *)
}

(** LP solution *)
type lp_solution = {
  asset_weights : float array;  (* w *)
  cash_weight : float;          (* w_c *)
  objective_value : float;
  lpm1_value : float;
  cvar_value : float;
  turnover : float;
  beta_penalty : float;
}

(** Export LP problem to JSON for Python solver *)
let export_to_json problem filename =

  (* Convert 2D array to JSON *)
  let matrix_to_json mat =
    `List (Array.to_list (Array.map (fun row ->
      `List (Array.to_list (Array.map (fun x -> `Float x) row))
    ) mat))
  in

  (* Convert 1D array to JSON *)
  let vector_to_json vec =
    `List (Array.to_list (Array.map (fun x -> `Float x) vec))
  in

  let json = `Assoc [
    ("n_assets", `Int problem.n_assets);
    ("n_scenarios", `Int problem.n_scenarios);
    ("asset_scenarios", matrix_to_json problem.asset_scenarios);
    ("benchmark_scenarios", vector_to_json problem.benchmark_scenarios);
    ("cash_scenarios", vector_to_json problem.cash_scenarios);
    ("prev_weights", vector_to_json problem.prev_weights);
    ("prev_cash", `Float problem.prev_cash);
    ("asset_betas", vector_to_json problem.asset_betas);
    ("stress_weight", `Float problem.stress_weight);
    ("lambda_lpm1", `Float problem.lambda_lpm1);
    ("lambda_cvar", `Float problem.lambda_cvar);
    ("lambda_beta", `Float problem.lambda_beta);
    ("kappa", `Float problem.kappa);
    ("lpm_threshold", `Float problem.lpm_threshold);
    ("cvar_alpha", `Float problem.cvar_alpha);
    ("beta_target", `Float problem.beta_target);
  ] in

  Yojson.Basic.to_file filename json

(** Import LP solution from JSON *)
let import_solution_from_json filename =
  let open Yojson.Basic.Util in

  let json = Yojson.Basic.from_file filename in

  let asset_weights = json |> member "asset_weights" |> to_list |> List.map to_float |> Array.of_list in
  let cash_weight = json |> member "cash_weight" |> to_float in
  let objective_value = json |> member "objective_value" |> to_float in
  let lpm1_value = json |> member "lpm1_value" |> to_float in
  let cvar_value = json |> member "cvar_value" |> to_float in
  let turnover = json |> member "turnover" |> to_float in
  let beta_penalty = json |> member "beta_penalty" |> to_float in

  {
    asset_weights;
    cash_weight;
    objective_value;
    lpm1_value;
    cvar_value;
    turnover;
    beta_penalty;
  }

(** Solve LP problem using Python solver *)
let solve_lp problem =
  (* Export problem *)
  let problem_file = "/tmp/lp_problem.json" in
  let solution_file = "/tmp/lp_solution.json" in

  export_to_json problem problem_file;

  (* Call Python solver with venv *)
  let solver_script = "pricing/regime_downside/python/solve_lp.py" in
  let python_path = ".venv/bin/python3" in
  let cmd = Printf.sprintf "%s %s %s %s" python_path solver_script problem_file solution_file in

  let exit_code = Sys.command cmd in

  if exit_code <> 0 then
    failwith "LP solver failed"
  else
    import_solution_from_json solution_file

(** Build LP problem from current state *)
let build_problem
    ~asset_returns_list
    ~benchmark_returns
    ~current_weights
    ~asset_betas
    ~params
    ~stress_weight =

  (* Convert to weekly scenarios *)
  let asset_scenarios = Scenarios.create_weekly_scenarios asset_returns_list in
  let benchmark_scenarios = Scenarios.create_weekly_benchmark benchmark_returns in

  let n_scenarios = Array.length benchmark_scenarios in
  let n_assets = List.length asset_returns_list in

  let cash_scenarios = Scenarios.create_weekly_cash n_scenarios in

  (* Extract previous weights in order *)
  let tickers = Scenarios.get_tickers_ordered asset_returns_list in
  let prev_weights = Array.of_list (List.map (fun ticker ->
    match List.assoc_opt ticker current_weights.assets with
    | Some w -> w
    | None -> 0.0
  ) tickers) in

  (* Extract betas in order *)
  let asset_betas_array = Array.of_list (List.map (fun ticker ->
    match List.assoc_opt ticker asset_betas with
    | Some b -> b
    | None -> 1.0  (* Default to market beta if missing *)
  ) tickers) in

  (* Combined trade penalty *)
  let kappa = params.transaction_cost_bps /. 10000.0 +. params.turnover_penalty in

  {
    n_assets;
    n_scenarios;
    asset_scenarios;
    benchmark_scenarios;
    cash_scenarios;
    prev_weights;
    prev_cash = current_weights.cash;
    asset_betas = asset_betas_array;
    stress_weight;
    lambda_lpm1 = params.lambda_lpm1;
    lambda_cvar = params.lambda_cvar;
    lambda_beta = params.beta_penalty;
    kappa;
    lpm_threshold = params.lpm1_threshold;
    cvar_alpha = 0.95;
    beta_target = params.target_beta;
  }

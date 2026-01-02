(** Main executable for regime-aware benchmark-relative downside optimization *)

open Regime_downside

(** Configuration *)
let data_dir = "pricing/regime_downside/data"
let output_dir = "pricing/regime_downside/output"
let log_dir = "pricing/regime_downside/log"

(** Ensure directories exist *)
let () =
  List.iter (fun dir ->
    if not (Sys.file_exists dir) then
      Unix.mkdir dir 0o755
  ) [output_dir; log_dir]

(** Get command line arguments *)
let tickers = ref ["AAPL"; "GOOGL"; "MSFT"; "NVDA"]
let start_date_idx = ref 1000  (* Start evaluation after 1000 days of history *)
let lookback_days = ref 252    (* Use 1 year of history for optimization *)
let init_mode = ref "equal_20" (* Initial allocation: cash, equal_20, or equal_0 *)

let () =
  let usage = "Usage: regime_downside [options]" in
  let specs = [
    ("-tickers", Arg.String (fun s ->
      tickers := List.map String.trim (String.split_on_char ',' s)),
      "Comma-separated list of tickers (default: AAPL,GOOGL,MSFT,NVDA)");
    ("-start", Arg.Set_int start_date_idx,
      "Index to start evaluation (default: 1000)");
    ("-lookback", Arg.Set_int lookback_days,
      "Lookback days for optimization (default: 252)");
    ("-init", Arg.Set_string init_mode,
      "Initial allocation: cash, equal_20, or equal_0 (default: equal_20)");
  ] in
  Arg.parse specs (fun _ -> ()) usage

let () =
  Printf.printf "Regime-Aware Benchmark-Relative Downside Optimization\n";
  Printf.printf "======================================================\n\n";

  (* Load parameters *)
  Printf.printf "Loading parameters...\n";
  let params_file = Filename.concat data_dir "params.json" in
  let params = Io.read_params_json ~filename:params_file in

  Printf.printf "Parameters loaded:\n";
  Printf.printf "  lambda_lpm1: %.4f\n" params.lambda_lpm1;
  Printf.printf "  lambda_cvar: %.4f\n" params.lambda_cvar;
  Printf.printf "  target_beta: %.2f\n" params.target_beta;
  Printf.printf "\n";

  (* Load benchmark data *)
  Printf.printf "Loading S&P 500 benchmark data...\n";
  let benchmark_file = Filename.concat data_dir "sp500_returns.csv" in
  let benchmark = Io.read_benchmark_csv ~filename:benchmark_file in
  Printf.printf "  Loaded %d days of benchmark data\n" (Array.length benchmark.returns);
  Printf.printf "\n";

  (* Load asset data *)
  Printf.printf "Loading asset return data...\n";
  let asset_returns_list = List.map (fun ticker ->
    let filename = Filename.concat data_dir (ticker ^ "_returns.csv") in
    Printf.printf "  Loading %s...\n" ticker;
    Io.read_returns_csv ~filename ~ticker
  ) !tickers in

  (* Find minimum data length across all assets *)
  let data_lengths = List.map (fun (asset : Types.return_series) ->
    (asset.ticker, Array.length asset.returns)
  ) asset_returns_list in
  let n_days = List.fold_left (fun min_len (_, len) ->
    min min_len len
  ) max_int data_lengths in

  Printf.printf "  Asset data lengths:\n";
  List.iter (fun (ticker, len) ->
    Printf.printf "    %s: %d days\n" ticker len
  ) data_lengths;
  Printf.printf "  Using minimum: %d days\n" n_days;
  Printf.printf "\n";

  (* Validate that we have enough data for the requested start index *)
  let required_days = !start_date_idx + !lookback_days in
  if n_days < required_days then begin
    Printf.eprintf "Error: Not enough data!\n";
    Printf.eprintf "  Minimum available: %d days\n" n_days;
    Printf.eprintf "  Required: start (%d) + lookback (%d) = %d days\n"
      !start_date_idx !lookback_days required_days;
    Printf.eprintf "  Suggestion: Use -start %d or less\n" (n_days - !lookback_days - 1);
    exit 1
  end;

  (* Truncate all assets to the minimum length (align to most recent n_days) *)
  let asset_returns_list = List.map (fun (asset : Types.return_series) ->
    let len = Array.length asset.returns in
    if len = n_days then
      asset
    else
      (* Take the most recent n_days from this asset *)
      let offset = len - n_days in
      ({
        ticker = asset.ticker;
        returns = Array.sub asset.returns offset n_days;
        dates = Array.sub asset.dates offset n_days;
      } : Types.return_series)
  ) asset_returns_list in

  (* Similarly truncate benchmark to match *)
  let benchmark : Types.benchmark =
    let len = Array.length benchmark.returns in
    if len = n_days then
      benchmark
    else
      let offset = len - n_days in
      ({
        returns = Array.sub benchmark.returns offset n_days;
        dates = Array.sub benchmark.dates offset n_days;
      } : Types.benchmark)
  in

  (* Initialize portfolio based on mode *)
  let n_assets = List.length !tickers in
  let initial_weights : Types.weights =
    match !init_mode with
    | "cash" ->
        Printf.printf "Initial portfolio: 100%% cash\n";
        {
          assets = List.map (fun ticker -> (ticker, 0.0)) !tickers;
          cash = 1.0;
        }
    | "equal_0" ->
        let weight = 1.0 /. float_of_int n_assets in
        Printf.printf "Initial portfolio: equal weights, 0%% cash\n";
        {
          assets = List.map (fun ticker -> (ticker, weight)) !tickers;
          cash = 0.0;
        }
    | "equal_20" | _ ->
        let weight = 0.8 /. float_of_int n_assets in
        Printf.printf "Initial portfolio: equal weights, 20%% cash\n";
        {
          assets = List.map (fun ticker -> (ticker, weight)) !tickers;
          cash = 0.2;
        }
  in

  List.iter (fun (ticker, w) ->
    Printf.printf "  %s: %.4f\n" ticker w
  ) initial_weights.assets;
  Printf.printf "  CASH: %.4f\n" initial_weights.cash;
  Printf.printf "\n";

  (* Set up logging *)
  let timestamp = Unix.time () |> Unix.gmtime in
  let log_filename = Printf.sprintf "%s/backtest_%04d%02d%02d_%02d%02d%02d.log"
    log_dir
    (timestamp.Unix.tm_year + 1900)
    (timestamp.Unix.tm_mon + 1)
    timestamp.Unix.tm_mday
    timestamp.Unix.tm_hour
    timestamp.Unix.tm_min
    timestamp.Unix.tm_sec
  in

  Printf.printf "Logging to: %s\n\n" log_filename;
  Printf.printf "Starting backtest...\n";
  Printf.printf "======================================================\n\n";

  (* Backtesting loop *)
  let current_weights = ref initial_weights in
  let dual_results = ref [] in
  let n_rebalances = ref 0 in
  let total_turnover = ref 0.0 in

  (* Progress tracking *)
  let total_evals = n_days - !start_date_idx in
  let start_time = Unix.gettimeofday () in

  for eval_idx = !start_date_idx to n_days - 1 do
    let eval_date = benchmark.dates.(eval_idx) in

    (* Progress logging *)
    let current_eval = eval_idx - !start_date_idx + 1 in
    let progress_pct = 100.0 *. (float_of_int current_eval) /. (float_of_int total_evals) in
    let elapsed_time = Unix.gettimeofday () -. start_time in
    let avg_time_per_eval = elapsed_time /. (float_of_int current_eval) in
    let remaining_evals = total_evals - current_eval in
    let est_remaining_time = avg_time_per_eval *. (float_of_int remaining_evals) in

    Printf.printf "\r[%d/%d] %.1f%% | %s | Elapsed: %.1fs | Remaining: ~%.1fs%!"
      current_eval total_evals progress_pct eval_date
      elapsed_time est_remaining_time;

    (* Get lookback window *)
    let lookback_start = max 0 (eval_idx - !lookback_days) in
    let lookback_end = eval_idx in

    (* Extract lookback returns *)
    let lookback_benchmark =
      Array.sub benchmark.returns lookback_start (lookback_end - lookback_start)
    in

    let lookback_assets = List.map (fun (rs : Types.return_series) ->
      let new_returns = Array.sub rs.returns lookback_start (lookback_end - lookback_start) in
      let new_dates = Array.sub rs.dates lookback_start (lookback_end - lookback_start) in
      ({ ticker = rs.ticker; returns = new_returns; dates = new_dates } : Types.return_series)
    ) asset_returns_list in

    (* Detect regime - use all data up to current point, not just lookback window *)
    let regime_benchmark =
      Array.sub benchmark.returns 0 (eval_idx + 1)
    in
    let regime =
      if Array.length regime_benchmark >= 756 then  (* Need at least 3 years *)
        Regime.detect_regime
          ~benchmark_returns:regime_benchmark
          ~lookback_years:3
          ~vol_window_days:20
          ~lower_percentile:0.70
          ~upper_percentile:0.75
      else
        (* Default to calm regime if not enough data *)
        { volatility = 0.15; stress_weight = 0.0; is_stress = false }
    in

    (* Estimate betas *)
    let asset_betas =
      Beta.estimate_all_betas
        ~asset_returns_list:lookback_assets
        ~benchmark_returns:lookback_benchmark
        ()
    in

    (* Optimize new weights (dual: frictionless and constrained) *)
    let dual_result =
      Optimization.optimize_dual
        ~params
        ~current_weights:!current_weights
        ~asset_returns_list:lookback_assets
        ~benchmark_returns:lookback_benchmark
        ~asset_betas
        ~regime
        ~n_random_starts:20  (* Faster with gradient refinement *)
        ~n_gradient_refine:5
        ()
    in

    (* Use constrained result for rebalancing decisions *)
    let proposed_result = dual_result.constrained in

    (* Calculate current portfolio metrics for comparison *)
    let current_result =
      let portfolio_returns =
        Optimization.calculate_portfolio_returns
          ~weights:!current_weights
          ~asset_returns_list:lookback_assets
      in
      let active_returns =
        Array.map2 (fun p b -> p -. b) portfolio_returns lookback_benchmark
      in
      let risk_metrics =
        Risk.calculate_risk_metrics
          ~threshold:params.lpm1_threshold
          ~active_returns
          ~weights:!current_weights
          ~asset_betas
      in
      (* Calculate objective value for current portfolio *)
      let beta_deviation = abs_float (risk_metrics.portfolio_beta -. params.target_beta) in
      let current_objective =
        params.lambda_lpm1 *. risk_metrics.lpm1 +.
        params.lambda_cvar *. risk_metrics.cvar_95 +.
        0.0 (* no turnover *) +.
        params.beta_penalty *. regime.stress_weight *. beta_deviation
      in
      ({
        weights = !current_weights;
        objective_value = current_objective;
        risk_metrics;
        turnover = 0.0;
        transaction_costs = 0.0;
      } : Types.optimization_result)
    in

    (* Decide whether to rebalance *)
    let decision =
      Optimization.should_rebalance
        ~current_result
        ~proposed_result
        ~threshold:params.rebalance_threshold
    in

    (* Create log entry *)
    let log_entry : Types.log_entry = {
      date = eval_date;
      regime;
      asset_betas;
      current_weights = !current_weights;
      proposed_weights = proposed_result.weights;
      risk_current = current_result.risk_metrics;
      risk_proposed = proposed_result.risk_metrics;
      decision;
      turnover = proposed_result.turnover;
      costs = proposed_result.transaction_costs;
    } in

    (* Write log *)
    Io.write_log_entry ~log_file:log_filename ~entry:log_entry;

    (* Update portfolio if rebalancing *)
    if decision.should_rebalance then begin
      current_weights := proposed_result.weights;
      n_rebalances := !n_rebalances + 1;
      total_turnover := !total_turnover +. proposed_result.turnover;

      Printf.printf "\n[%s] REBALANCE (%d)\n" eval_date !n_rebalances;
      Printf.printf "  Improvement: %.6f\n" decision.objective_improvement;
      Printf.printf "  Turnover: %.4f\n" proposed_result.turnover;
      Printf.printf "  Beta: %.4f (regime stress: %.2f)\n"
        proposed_result.risk_metrics.portfolio_beta
        regime.stress_weight;

      (* Display gap information *)
      Printf.printf "\n  Gap Analysis (Frictionless vs Constrained):\n";
      Printf.printf "    Distance: %.2f%% turnover\n" (dual_result.gap_distance *. 100.0);
      Printf.printf "    LPM1 diff: %+.6f\n" dual_result.gap_lpm1;
      Printf.printf "    CVaR diff: %+.6f\n" dual_result.gap_cvar;
      Printf.printf "    Beta diff: %+.4f\n" dual_result.gap_beta;
      Printf.printf "    Frictionless objective: %.6f\n" dual_result.frictionless.objective_value;
      Printf.printf "    Constrained objective: %.6f\n" dual_result.constrained.objective_value;
    end;

    (* Store dual result *)
    dual_results := (eval_date, dual_result) :: !dual_results

  done;

  (* Clear progress line and print completion *)
  Printf.printf "\n\n======================================================\n";
  Printf.printf "Backtest Complete!\n\n";

  (* Print summary statistics *)
  Printf.printf "Summary:\n";
  Printf.printf "  Total days evaluated: %d\n" (n_days - !start_date_idx);
  Printf.printf "  Number of rebalances: %d\n" !n_rebalances;
  Printf.printf "  Total turnover: %.4f\n" !total_turnover;
  Printf.printf "  Average turnover per rebalance: %.4f\n"
    (if !n_rebalances > 0 then !total_turnover /. float_of_int !n_rebalances else 0.0);
  Printf.printf "\n";

  (* Write results to CSV *)
  let results_file = Filename.concat output_dir "optimization_results.csv" in
  Printf.printf "Writing results to: %s\n" results_file;
  Io.write_dual_result_csv ~filename:results_file ~results:(List.rev !dual_results);

  Printf.printf "\nDone! Check the output directory for results.\n"

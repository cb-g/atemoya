(* Main CLI for Variance Swaps and VRP Trading *)

open Variance_swaps_lib

(* ========================================================================== *)
(* Helpers: compute RV using selected estimator *)
(* ========================================================================== *)

let compute_rv_from_ohlc ~estimator ~ohlc_data ~annualization_factor =
  let n = Array.length ohlc_data in
  if n < 2 then 0.0
  else
    let opens  = Array.map (fun (_, o, _, _, _) -> o) ohlc_data in
    let highs  = Array.map (fun (_, _, h, _, _) -> h) ohlc_data in
    let lows   = Array.map (fun (_, _, _, l, _) -> l) ohlc_data in
    let closes = Array.map (fun (_, _, _, _, c) -> c) ohlc_data in
    match estimator with
    | "cc" ->
        Realized_variance.compute_realized_variance ~prices:closes ~annualization_factor
    | "parkinson" ->
        Realized_variance.parkinson_estimator ~highs ~lows ~annualization_factor
    | "gk" ->
        Realized_variance.garman_klass_estimator ~opens ~highs ~lows ~closes ~annualization_factor
    | "rs" ->
        Realized_variance.rogers_satchell_estimator ~opens ~highs ~lows ~closes ~annualization_factor
    | "yz" ->
        Realized_variance.yang_zhang_estimator ~opens ~highs ~lows ~closes ~annualization_factor
    | _ ->
        Realized_variance.compute_realized_variance ~prices:closes ~annualization_factor

let compute_forecast ~forecast_method ~ohlc_data ~annualization_factor =
  let closes = Array.map (fun (_, _, _, _, c) -> c) ohlc_data in
  let n = Array.length closes in
  if n < 2 then 0.0
  else
    let returns = Array.init (n - 1) (fun i ->
      log (closes.(i + 1) /. closes.(i))
    ) in
    match forecast_method with
    | "ewma" ->
        Realized_variance.forecast_ewma ~returns ~lambda:0.94 ~annualization_factor
    | "garch" ->
        Realized_variance.forecast_garch ~returns
          ~omega:0.000001 ~alpha:0.08 ~beta:0.90 ~annualization_factor
    | _ -> (* "historical" — use plain RV as forecast *)
        compute_rv_from_ohlc ~estimator:"cc" ~ohlc_data ~annualization_factor

let estimator_name = function
  | "cc" -> "Close-to-Close"
  | "parkinson" -> "Parkinson"
  | "gk" -> "Garman-Klass"
  | "rs" -> "Rogers-Satchell"
  | "yz" -> "Yang-Zhang"
  | s -> s

let forecast_name = function
  | "ewma" -> "EWMA (λ=0.94)"
  | "garch" -> "GARCH(1,1)"
  | _ -> "Historical RV"

(* ========================================================================== *)
(* Main *)
(* ========================================================================== *)

let () =
  let ticker = ref "SPY" in
  let operation = ref "price" in
  let horizon_days = ref 30 in
  let notional = ref 100000.0 in
  let num_strikes = ref 20 in
  let estimator = ref "yz" in
  let forecast_method = ref "ewma" in

  let usage_msg = "Variance Swaps and VRP Trading Model" in
  let speclist = [
    ("-ticker", Arg.Set_string ticker, "Ticker symbol (default: SPY)");
    ("-op", Arg.Set_string operation, "Operation: price|vrp|signal|backtest|replicate (default: price)");
    ("-horizon", Arg.Set_int horizon_days, "Horizon in days (default: 30)");
    ("-notional", Arg.Set_float notional, "Variance notional (default: 100000)");
    ("-strikes", Arg.Set_int num_strikes, "Number of strikes in replication (default: 20)");
    ("-estimator", Arg.Set_string estimator, "RV estimator: cc|parkinson|gk|rs|yz (default: yz)");
    ("-forecast", Arg.Set_string forecast_method, "Forecast: historical|ewma|garch (default: ewma)");
  ] in

  Arg.parse speclist (fun _ -> ()) usage_msg;

  (* Ensure output directories exist *)
  Io.ensure_output_dirs ();

  let log_file = Printf.sprintf "pricing/variance_swaps/log/varswap_%s.log" !ticker in
  Io.write_log log_file (Printf.sprintf "=== Variance Swap Analysis: %s ===" !ticker);
  Io.write_log log_file (Printf.sprintf "Operation: %s" !operation);
  Io.write_log log_file (Printf.sprintf "Estimator: %s" (estimator_name !estimator));
  Io.write_log log_file (Printf.sprintf "Forecast: %s" (forecast_name !forecast_method));

  (* Read data *)
  let price_file = Printf.sprintf "pricing/variance_swaps/data/%s_prices.csv" !ticker in
  let vol_surface_file = Printf.sprintf "pricing/variance_swaps/data/%s_vol_surface.json" !ticker in
  let underlying_file = Printf.sprintf "pricing/variance_swaps/data/%s_underlying.json" !ticker in

  let ohlc_data = Io.read_ohlc_data price_file in
  let price_data = Io.read_price_data price_file in
  let vol_surface = Io.read_vol_surface vol_surface_file in
  let underlying_data = Io.read_underlying_data underlying_file in

  Io.write_log log_file (Printf.sprintf "Loaded %d price observations" (Array.length price_data));
  Io.write_log log_file (Printf.sprintf "Spot: $%.2f" underlying_data.spot_price);

  match !operation with
  | "price" ->
      (* Price variance swap *)
      Io.write_log log_file "Pricing variance swap using Carr-Madan formula";

      let expiry = float_of_int !horizon_days /. 365.0 in
      let strike_grid = Replication.optimize_strike_grid
        vol_surface
        underlying_data
        ~rate:0.05
        ~expiry
        ~target_variance_notional:!notional
        ~num_strikes:!num_strikes
      in

      let var_swap = Variance_swap_pricing.price_variance_swap
        vol_surface
        ~spot:underlying_data.spot_price
        ~expiry
        ~rate:0.05
        ~dividend:underlying_data.dividend_yield
        ~strike_grid
        ~ticker:!ticker
        ~notional:!notional
      in

      let output_file = Printf.sprintf "pricing/variance_swaps/output/%s_variance_swap.csv" !ticker in
      Io.write_variance_swap_csv output_file var_swap;

      Io.write_log log_file (Printf.sprintf "Variance Strike: %.6f (Vol Strike: %.4f)"
        var_swap.strike_var (sqrt var_swap.strike_var));
      Io.write_log log_file (Printf.sprintf "Vega Notional: $%.2f" var_swap.vega_notional);
      Io.write_log log_file (Printf.sprintf "Output: %s" output_file);

      Printf.printf "✓ Variance swap priced\n";
      Printf.printf "  Variance Strike: %.6f\n" var_swap.strike_var;
      Printf.printf "  Vol Strike: %.4f%%\n" (sqrt var_swap.strike_var *. 100.0);
      Printf.printf "  Vega Notional: $%.2f\n" var_swap.vega_notional

  | "vrp" ->
      (* Compute VRP *)
      Io.write_log log_file "Computing VRP";

      let realized_var = compute_rv_from_ohlc ~estimator:!estimator ~ohlc_data ~annualization_factor:252.0 in
      let forecast_var = compute_forecast ~forecast_method:!forecast_method ~ohlc_data ~annualization_factor:252.0 in

      let expiry = float_of_int !horizon_days /. 365.0 in
      let strike_grid = Variance_swap_pricing.generate_strike_grid
        ~spot:underlying_data.spot_price
        ~num_strikes:!num_strikes
        ~log_moneyness_range:(-0.3, 0.3)
      in

      let var_swap = Variance_swap_pricing.price_variance_swap
        vol_surface
        ~spot:underlying_data.spot_price
        ~expiry
        ~rate:0.05
        ~dividend:underlying_data.dividend_yield
        ~strike_grid
        ~ticker:!ticker
        ~notional:!notional
      in

      let vrp_obs = Vrp_calculation.compute_vrp
        ~ticker:!ticker
        ~horizon_days:!horizon_days
        ~implied_var:var_swap.strike_var
        ~forecast_realized_var:forecast_var
      in

      let output_file = Printf.sprintf "pricing/variance_swaps/output/%s_vrp_%s_%s.csv" !ticker !estimator !forecast_method in
      Io.write_vrp_observations_csv output_file [| vrp_obs |];

      Io.write_log log_file (Printf.sprintf "VRP: %.6f (%.2f%%)" vrp_obs.vrp vrp_obs.vrp_percent);
      Io.write_log log_file (Printf.sprintf "Implied Var: %.6f, Realized Var (est): %.6f, Forecast: %.6f"
        vrp_obs.implied_var realized_var forecast_var);

      Printf.printf "✓ VRP computed (%s + %s)\n" (estimator_name !estimator) (forecast_name !forecast_method);
      Printf.printf "  VRP: %.6f (%.2f%%)\n" vrp_obs.vrp vrp_obs.vrp_percent;
      Printf.printf "  Implied Variance: %.6f (%.2f%% vol)\n" vrp_obs.implied_var (sqrt vrp_obs.implied_var *. 100.0);
      Printf.printf "  Realized Variance: %.6f (%.2f%% vol, %s)\n" realized_var (sqrt realized_var *. 100.0) (estimator_name !estimator);
      Printf.printf "  Forecast Variance: %.6f (%.2f%% vol, %s)\n" forecast_var (sqrt forecast_var *. 100.0) (forecast_name !forecast_method)

  | "signal" ->
      (* Generate trading signal *)
      Io.write_log log_file "Generating VRP trading signal";

      let config = Types.default_config in
      let forecast_var = compute_forecast ~forecast_method:!forecast_method ~ohlc_data ~annualization_factor:252.0 in

      let expiry = float_of_int !horizon_days /. 365.0 in
      let strike_grid = Variance_swap_pricing.generate_strike_grid
        ~spot:underlying_data.spot_price
        ~num_strikes:!num_strikes
        ~log_moneyness_range:(-0.3, 0.3)
      in

      let var_swap = Variance_swap_pricing.price_variance_swap
        vol_surface
        ~spot:underlying_data.spot_price
        ~expiry
        ~rate:0.05
        ~dividend:underlying_data.dividend_yield
        ~strike_grid
        ~ticker:!ticker
        ~notional:!notional
      in

      let vrp_obs = Vrp_calculation.compute_vrp
        ~ticker:!ticker
        ~horizon_days:!horizon_days
        ~implied_var:var_swap.strike_var
        ~forecast_realized_var:forecast_var
      in

      let signal = Vrp_calculation.generate_signal vrp_obs config in

      let output_file = Printf.sprintf "pricing/variance_swaps/output/%s_signal_%s_%s.csv" !ticker !estimator !forecast_method in
      Io.write_signals_csv output_file [| signal |];

      let signal_str = match signal.signal_type with
        | Types.ShortVariance _ -> "SHORT VARIANCE"
        | Types.LongVariance _ -> "LONG VARIANCE"
        | Types.Neutral _ -> "NEUTRAL"
      in

      Io.write_log log_file (Printf.sprintf "Signal: %s (confidence: %.2f)" signal_str signal.confidence);
      Io.write_log log_file (Printf.sprintf "Position Size: $%.2f" signal.position_size);

      Printf.printf "✓ Signal generated (%s + %s)\n" (estimator_name !estimator) (forecast_name !forecast_method);
      Printf.printf "  Signal: %s\n" signal_str;
      Printf.printf "  Confidence: %.2f\n" signal.confidence;
      Printf.printf "  Position Size: $%.2f vega notional\n" signal.position_size;
      Printf.printf "  Implied Vol: %.2f%%  |  Forecast RV: %.2f%%\n"
        (sqrt var_swap.strike_var *. 100.0) (sqrt forecast_var *. 100.0)

  | "replicate" ->
      (* Build replication portfolio *)
      Io.write_log log_file "Building variance swap replication portfolio";

      let expiry = float_of_int !horizon_days /. 365.0 in
      let strike_grid = Replication.optimize_strike_grid
        vol_surface
        underlying_data
        ~rate:0.05
        ~expiry
        ~target_variance_notional:!notional
        ~num_strikes:!num_strikes
      in

      let portfolio = Replication.build_replication_portfolio
        vol_surface
        underlying_data
        ~rate:0.05
        ~expiry
        ~target_variance_notional:!notional
        ~strike_grid
      in

      let output_file = Printf.sprintf "pricing/variance_swaps/output/%s_replication.csv" !ticker in
      Io.write_replication_csv output_file portfolio;

      Io.write_log log_file (Printf.sprintf "Portfolio: %d legs" (Array.length portfolio.legs));
      Io.write_log log_file (Printf.sprintf "Total Cost: $%.2f" portfolio.total_cost);
      Io.write_log log_file (Printf.sprintf "Total Vega: %.2f" portfolio.total_vega);
      Io.write_log log_file (Printf.sprintf "Total Delta: %.4f" portfolio.total_delta);

      let is_delta_neutral = Replication.is_delta_neutral portfolio ~tolerance:0.01 in
      Io.write_log log_file (Printf.sprintf "Delta Neutral: %b" is_delta_neutral);

      Printf.printf "✓ Replication portfolio created\n";
      Printf.printf "  Number of Legs: %d\n" (Array.length portfolio.legs);
      Printf.printf "  Total Cost: $%.2f\n" portfolio.total_cost;
      Printf.printf "  Total Vega: %.2f\n" portfolio.total_vega;
      Printf.printf "  Total Delta: %.4f\n" portfolio.total_delta;
      Printf.printf "  Delta Neutral: %b\n" is_delta_neutral

  | "backtest" ->
      (* Backtest VRP strategy - create historical time series *)
      Io.write_log log_file (Printf.sprintf "Backtesting VRP strategy (estimator: %s, forecast: %s)"
        (estimator_name !estimator) (forecast_name !forecast_method));

      (* Use constant implied vol (no historical vol surface available) *)
      let atm_iv = 0.20 in
      let implied_var = atm_iv *. atm_iv in
      let num_windows = max 1 (Array.length ohlc_data - !horizon_days) in

      let vrp_time_series = Array.init num_windows (fun i ->
        let end_idx = i + !horizon_days in
        if end_idx >= Array.length ohlc_data then
          Vrp_calculation.compute_vrp
            ~ticker:!ticker
            ~horizon_days:!horizon_days
            ~implied_var
            ~forecast_realized_var:0.0
        else
          let window = Array.sub ohlc_data i !horizon_days in
          let forecast_var = match !forecast_method with
            | "ewma" | "garch" -> compute_forecast ~forecast_method:!forecast_method ~ohlc_data:window ~annualization_factor:252.0
            | _ -> compute_rv_from_ohlc ~estimator:!estimator ~ohlc_data:window ~annualization_factor:252.0
          in

          Vrp_calculation.compute_vrp
            ~ticker:!ticker
            ~horizon_days:!horizon_days
            ~implied_var
            ~forecast_realized_var:forecast_var
      ) in

      let output_file = Printf.sprintf "pricing/variance_swaps/output/%s_vrp_%s_%s.csv" !ticker !estimator !forecast_method in
      Io.write_vrp_observations_csv output_file vrp_time_series;

      Io.write_log log_file (Printf.sprintf "Generated %d VRP observations" (Array.length vrp_time_series));

      (* VRP significance tests *)
      let (mean_vrp, std_vrp, sharpe) = Vrp_calculation.vrp_statistics vrp_time_series in
      let t_significant = Vrp_calculation.is_vrp_significant vrp_time_series ~confidence_level:0.95 in
      let (w_significant, w_z, _) = Vrp_calculation.wilcoxon_signed_rank_test vrp_time_series ~confidence_level:0.95 in

      Printf.printf "✓ Backtest complete (%s + %s)\n" (estimator_name !estimator) (forecast_name !forecast_method);
      Printf.printf "  Generated %d VRP observations\n" (Array.length vrp_time_series);
      Printf.printf "  Mean VRP: %.4f (std: %.4f, Sharpe: %.2f)\n" mean_vrp std_vrp sharpe;
      Printf.printf "  T-test (95%%): %s\n" (if t_significant then "SIGNIFICANT" else "not significant");
      Printf.printf "  Wilcoxon signed-rank (95%%): %s (z=%.2f)\n" (if w_significant then "SIGNIFICANT" else "not significant") w_z;
      Printf.printf "  Output: %s\n" output_file

  | _ ->
      Printf.eprintf "Error: Unknown operation '%s'\n" !operation;
      Printf.eprintf "Valid operations: price, vrp, signal, replicate, backtest\n";
      exit 1

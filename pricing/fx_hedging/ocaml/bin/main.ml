(* Main CLI for FX Hedging *)

open Fx_hedging_lib

let () =
  (* Command-line arguments *)
  let operation = ref "backtest" in
  let currency_pair_str = ref "EUR/USD" in
  let exposure_usd = ref 500000.0 in
  let hedge_ratio = ref (-1.0) in
  let contract_code = ref "6E" in
  let initial_margin = ref 10000.0 in
  let transaction_cost_bps = ref 5.0 in
  let strike = ref 1.08 in
  let volatility = ref 0.12 in
  let expiry_days = ref 90 in
  let option_type = ref "call" in

  let usage_msg = "FX Hedging & Futures Options\n\n\
                   Usage: fx_hedging [options]\n\n\
                   Example:\n\
                   fx_hedging -operation backtest -exposure 500000 -pair EUR/USD -hedge-ratio -1.0\n\
                   fx_hedging -operation price -strike 1.10 -volatility 0.12 -expiry-days 30\n" in

  let speclist = [
    ("-operation", Arg.Set_string operation, "Operation: backtest|exposure|price (default: backtest)");
    ("-pair", Arg.Set_string currency_pair_str, "Currency pair (default: EUR/USD)");
    ("-exposure", Arg.Set_float exposure_usd, "USD exposure amount (default: 500000)");
    ("-hedge-ratio", Arg.Set_float hedge_ratio, "Hedge ratio (default: -1.0 = full hedge)");
    ("-contract", Arg.Set_string contract_code, "Futures contract code (default: 6E)");
    ("-margin", Arg.Set_float initial_margin, "Initial margin balance (default: 10000)");
    ("-cost-bps", Arg.Set_float transaction_cost_bps, "Transaction cost in bps (default: 5.0)");
    ("-strike", Arg.Set_float strike, "Strike price for options (default: 1.08)");
    ("-volatility", Arg.Set_float volatility, "Implied volatility for options (default: 0.12)");
    ("-expiry-days", Arg.Set_int expiry_days, "Days to expiry for options (default: 90)");
    ("-option-type", Arg.Set_string option_type, "Option type: call|put (default: call)");
  ] in

  Arg.parse speclist (fun _ -> ()) usage_msg;

  match !operation with
  | "backtest" ->
      (* Load data *)
      let fx_file = Printf.sprintf "pricing/fx_hedging/data/%s_spot.csv" (String.lowercase_ascii !contract_code) in
      let futures_file = Printf.sprintf "pricing/fx_hedging/data/%s_futures.csv" (String.lowercase_ascii !contract_code) in

      let fx_rates = Io.read_fx_rates fx_file in
      let futures_prices = Io.read_futures_prices futures_file in

      if Array.length fx_rates = 0 || Array.length futures_prices = 0 then begin
        Printf.eprintf "Error: No data found. Please run Python data fetching scripts first:\n";
        Printf.eprintf "  cd pricing/fx_hedging/python/fetch\n";
        Printf.eprintf "  python fetch_fx_data.py %s\n" !contract_code;
        exit 1
      end;

      (* Get contract specification *)
      let spec = Types.get_cme_spec !contract_code in

      Printf.printf "\n=== FX Hedging Simulation ===\n";
      Printf.printf "Operation: backtest\n";
      Printf.printf "Asset: %s\n" spec.name;
      Printf.printf "Exposure: $%.2f\n" !exposure_usd;
      Printf.printf "Hedge Ratio: %.2f\n" !hedge_ratio;
      Printf.printf "\nRunning backtest...\n\n";

      Printf.printf "Loaded %d observations\n" (Array.length fx_rates);
      Printf.printf "Loaded %d futures observations\n\n" (Array.length futures_prices);
      let (_, initial_spot) = fx_rates.(0) in
      let (_, initial_futures) = futures_prices.(0) in

      (* Build futures contract *)
      let futures = Futures.build_futures
        ~spec
        ~spot:initial_spot
        ~domestic_rate:0.05
        ~foreign_rate:0.03
        ~expiry:(90.0 /. 365.0)
        ~contract_month:"M24"
      in

      let futures = { futures with futures_price = initial_futures } in

      (* Build hedge strategy *)
      let strategy = Types.Static { hedge_ratio = !hedge_ratio } in

      (* Run backtest *)
      let (result, snapshots) = Simulation.run_hedge_backtest
        ~exposure_usd:!exposure_usd
        ~fx_rates
        ~futures_prices
        ~hedge_strategy:strategy
        ~futures
        ~initial_margin_balance:!initial_margin
        ~transaction_cost_bps:!transaction_cost_bps
      in

      (* Print results *)
      Printf.printf "=== Backtest Results ===\n";
      Printf.printf "Unhedged P&L: $%.2f\n" result.unhedged_pnl;
      Printf.printf "Hedged P&L: $%.2f\n" result.hedged_pnl;
      Printf.printf "Hedge P&L: $%.2f\n" result.hedge_pnl;
      Printf.printf "Transaction Costs: $%.2f\n" result.transaction_costs;
      Printf.printf "\nMetrics:\n";
      Printf.printf "  Hedge Effectiveness: %.2f%%\n" (result.hedge_effectiveness *. 100.0);
      Printf.printf "  Max Drawdown (Unhedged): %.2f%%\n" (result.max_drawdown_unhedged *. 100.0);
      Printf.printf "  Max Drawdown (Hedged): %.2f%%\n" (result.max_drawdown_hedged *. 100.0);

      (match result.sharpe_unhedged with
       | Some sr -> Printf.printf "  Sharpe Ratio (Unhedged): %.4f\n" sr
       | None -> Printf.printf "  Sharpe Ratio (Unhedged): N/A\n");

      (match result.sharpe_hedged with
       | Some sr -> Printf.printf "  Sharpe Ratio (Hedged): %.4f\n" sr
       | None -> Printf.printf "  Sharpe Ratio (Hedged): N/A\n");

      Printf.printf "\n";

      (* Write output files *)
      let output_dir = "pricing/fx_hedging/output" in
      let result_file = Printf.sprintf "%s/%s_backtest_summary.csv" output_dir !contract_code in
      let timeseries_file = Printf.sprintf "%s/%s_backtest.csv" output_dir !contract_code in

      Io.write_hedge_result ~filename:result_file ~result;
      Io.write_simulation_snapshots ~filename:timeseries_file ~snapshots;

      Printf.printf "Output files written to %s/\n" output_dir;
      Printf.printf "\nRun Python visualization:\n";
      Printf.printf "  cd pricing/fx_hedging/python/viz\n";
      Printf.printf "  python plot_hedge_performance.py %s\n" !contract_code;
      Printf.printf "\n✓ Backtest complete\n"

  | "exposure" ->
      Printf.printf "Running exposure analysis...\n\n";

      let portfolio_file = "pricing/fx_hedging/data/portfolio.csv" in
      let positions = Io.read_portfolio portfolio_file in

      if Array.length positions = 0 then begin
        Printf.eprintf "Error: No portfolio data found in %s\n" portfolio_file;
        exit 1
      end;

      let exposures = Exposure_analysis.calculate_portfolio_exposure ~positions in
      let total_value = Exposure_analysis.total_portfolio_value ~positions in

      Printf.printf "=== Portfolio FX Exposure ===\n";
      Printf.printf "Total Portfolio Value: $%.2f\n\n" total_value;

      Printf.printf "%-10s %15s %15s\n" "Currency" "Exposure (USD)" "% of Portfolio";
      Printf.printf "%s\n" (String.make 45 '-');

      Array.iter (fun (exp : Types.fx_exposure) ->
        Printf.printf "%-10s %15.2f %14.2f%%\n"
          (Types.currency_to_string exp.currency)
          exp.net_exposure_usd
          exp.pct_of_portfolio
      ) exposures;

      (* Write output *)
      let output_file = "pricing/fx_hedging/output/exposure_analysis.csv" in
      Io.write_exposure_analysis ~filename:output_file ~exposures;

      Printf.printf "\n✓ Exposure analysis complete\n"

  | "price" ->
      Printf.printf "Pricing forwards and futures options...\n\n";

      let spot = 1.10 in
      let strike_val = !strike in
      let expiry = (float_of_int !expiry_days) /. 365.0 in
      let domestic_rate = 0.05 in
      let foreign_rate = 0.03 in
      let vol = !volatility in
      let rate = 0.05 in
      let opt_type = if !option_type = "put" then Types.Put else Types.Call in
      let opt_label = if !option_type = "put" then "Put" else "Call" in

      Printf.printf "Parameters: K=%.4f, σ=%.2f%%, T=%dd, type=%s\n\n"
        strike_val (vol *. 100.0) !expiry_days opt_label;

      (* Forward rate *)
      let forward = Forwards.forward_rate ~spot ~domestic_rate ~foreign_rate ~maturity:expiry in
      Printf.printf "Forward Rate (%dd): %.6f\n" !expiry_days forward;

      (* Futures price (same as forward) *)
      let futures_price = Futures.futures_price ~spot ~domestic_rate ~foreign_rate ~maturity:expiry in
      Printf.printf "Futures Price: %.6f\n" futures_price;

      (* Black's model option pricing *)
      let call_price = Futures_options.black_price
        ~option_type:Types.Call
        ~futures_price
        ~strike:strike_val
        ~expiry
        ~rate
        ~volatility:vol
      in

      let put_price = Futures_options.black_price
        ~option_type:Types.Put
        ~futures_price
        ~strike:strike_val
        ~expiry
        ~rate
        ~volatility:vol
      in

      Printf.printf "\nFutures Options (K=%.4f, F=%.4f, T=%dd, σ=%.1f%%):\n"
        strike_val futures_price !expiry_days (vol *. 100.0);
      Printf.printf "  Call Premium: $%.6f\n" call_price;
      Printf.printf "  Put Premium: $%.6f\n" put_price;

      (* Greeks for requested option type *)
      let greeks = Futures_options.black_greeks
        ~option_type:opt_type
        ~futures_price
        ~strike:strike_val
        ~expiry
        ~rate
        ~volatility:vol
      in

      Printf.printf "\n%s Option Greeks:\n" opt_label;
      Printf.printf "  Delta: %.4f\n" greeks.delta;
      Printf.printf "  Gamma: %.6f\n" greeks.gamma;
      Printf.printf "  Theta: %.4f (per day)\n" greeks.theta;
      Printf.printf "  Vega: %.4f (per 1%% vol)\n" greeks.vega;
      Printf.printf "  Rho: %.4f (per 1%% rate)\n" greeks.rho;

      Printf.printf "\n✓ Pricing complete\n"

  | _ ->
      Printf.eprintf "Unknown operation: %s\n" !operation;
      Printf.eprintf "Valid operations: backtest, exposure, price\n";
      exit 1

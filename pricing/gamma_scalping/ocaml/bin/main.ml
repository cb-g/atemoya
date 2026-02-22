(* Main CLI for Gamma Scalping *)

open Gamma_scalping_lib

let () =
  (* Command-line arguments *)
  let ticker = ref "SPY" in
  let position_type_str = ref "straddle" in
  let strike = ref 0.0 in  (* 0.0 means ATM *)
  let call_strike = ref 0.0 in
  let put_strike = ref 0.0 in
  let expiry_days = ref 30 in
  let entry_iv = ref 0.20 in
  let strategy_str = ref "threshold" in
  let threshold = ref 0.10 in
  let interval_minutes = ref 240 in
  let transaction_cost_bps = ref 5.0 in
  let rate = ref 0.05 in
  let dividend = ref 0.0 in
  let contracts = ref 1 in

  let usage_msg = "Gamma Scalping - Volatility Trading Strategy\n\n\
                   Usage: gamma_scalping [options]\n\n\
                   Example:\n\
                   gamma_scalping -ticker SPY -position straddle -strike 500 -expiry 30 -iv 0.18 -strategy threshold -threshold 0.10\n" in

  let speclist = [
    ("-ticker", Arg.Set_string ticker, "Ticker symbol (default: SPY)");
    ("-position", Arg.Set_string position_type_str, "Position type: straddle|strangle|call|put (default: straddle)");
    ("-strike", Arg.Set_float strike, "Strike price for straddle/single option (0 = ATM, default: 0)");
    ("-call-strike", Arg.Set_float call_strike, "Call strike for strangle (0 = ATM+5%, default: 0)");
    ("-put-strike", Arg.Set_float put_strike, "Put strike for strangle (0 = ATM-5%, default: 0)");
    ("-expiry", Arg.Set_int expiry_days, "Days to expiration (default: 30)");
    ("-iv", Arg.Set_float entry_iv, "Entry implied volatility (default: 0.20)");
    ("-strategy", Arg.Set_string strategy_str, "Hedging strategy: threshold|time|hybrid|vol-adaptive (default: threshold)");
    ("-threshold", Arg.Set_float threshold, "Delta threshold for rehedging (default: 0.10)");
    ("-interval", Arg.Set_int interval_minutes, "Time interval in minutes for time-based hedging (default: 240)");
    ("-cost-bps", Arg.Set_float transaction_cost_bps, "Transaction cost in bps (default: 5.0)");
    ("-rate", Arg.Set_float rate, "Risk-free rate (default: 0.05)");
    ("-dividend", Arg.Set_float dividend, "Dividend yield (default: 0.0)");
    ("-contracts", Arg.Set_int contracts, "Number of contracts (default: 1)");
  ] in

  Arg.parse speclist (fun _ -> ()) usage_msg;

  Printf.printf "\n=== Gamma Scalping Simulation ===\n";
  Printf.printf "Ticker: %s\n" !ticker;
  Printf.printf "Position: %s\n" !position_type_str;
  Printf.printf "Expiry: %d days\n" !expiry_days;
  Printf.printf "Entry IV: %.2f%%\n" (!entry_iv *. 100.0);
  Printf.printf "Hedging Strategy: %s\n" !strategy_str;
  Printf.printf "\n";

  (* Load intraday price data *)
  let price_file = Printf.sprintf "pricing/gamma_scalping/data/%s_intraday.csv" !ticker in
  let intraday_prices = Io.read_intraday_prices price_file in

  if Array.length intraday_prices = 0 then begin
    Printf.eprintf "Error: No intraday price data found in %s\n" price_file;
    Printf.eprintf "Please run the data fetching script first:\n";
    Printf.eprintf "  uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker %s\n" !ticker;
    exit 1
  end;

  Printf.printf "Loaded %d intraday price observations\n" (Array.length intraday_prices);

  (* Get entry spot price *)
  let (_, entry_spot) = intraday_prices.(0) in
  Printf.printf "Entry spot: $%.2f\n\n" entry_spot;

  (* Build position type *)
  let position_type =
    match !position_type_str with
    | "straddle" ->
        let strike_price = if !strike = 0.0 then entry_spot else !strike in
        Types.Straddle { strike = strike_price }
    | "strangle" ->
        let call_strike_price = if !call_strike = 0.0 then entry_spot *. 1.05 else !call_strike in
        let put_strike_price = if !put_strike = 0.0 then entry_spot *. 0.95 else !put_strike in
        Types.Strangle { call_strike = call_strike_price; put_strike = put_strike_price }
    | "call" ->
        let strike_price = if !strike = 0.0 then entry_spot else !strike in
        Types.SingleOption { option_type = Types.Call; strike = strike_price }
    | "put" ->
        let strike_price = if !strike = 0.0 then entry_spot else !strike in
        Types.SingleOption { option_type = Types.Put; strike = strike_price }
    | _ ->
        Printf.eprintf "Unknown position type: %s\n" !position_type_str;
        exit 1
  in

  (* Build hedging strategy *)
  let hedging_strategy =
    match !strategy_str with
    | "threshold" -> Types.DeltaThreshold { threshold = !threshold }
    | "time" -> Types.TimeBased { interval_minutes = !interval_minutes }
    | "hybrid" -> Types.Hybrid { threshold = !threshold; interval_minutes = !interval_minutes }
    | "vol-adaptive" -> Types.VolAdaptive { low_threshold = 0.15; high_threshold = 0.30 }
    | _ ->
        Printf.eprintf "Unknown hedging strategy: %s\n" !strategy_str;
        exit 1
  in

  (* Build simulation config *)
  let config = {
    Types.transaction_cost_bps = !transaction_cost_bps;
    rate = !rate;
    dividend = !dividend;
    contracts = !contracts;
  } in

  (* Convert expiry to years *)
  let expiry_years = float_of_int !expiry_days /. 365.0 in

  (* Run simulation *)
  Printf.printf "Running simulation...\n";
  let result = Simulation.run_simulation
    ~position_type
    ~intraday_prices
    ~entry_iv:!entry_iv
    ~iv_timeseries:None  (* TODO: Support IV timeseries *)
    ~hedging_strategy
    ~config
    ~expiry:expiry_years
  in

  (* Print results *)
  Printf.printf "\n=== Simulation Results ===\n";
  Printf.printf "Entry Premium: $%.4f\n" result.entry_premium;
  Printf.printf "Final P&L: $%.4f\n" result.final_pnl;
  Printf.printf "\nP&L Attribution:\n";
  Printf.printf "  Gamma P&L: $%.4f\n" result.gamma_pnl_total;
  Printf.printf "  Theta P&L: $%.4f\n" result.theta_pnl_total;
  Printf.printf "  Vega P&L: $%.4f\n" result.vega_pnl_total;
  Printf.printf "  Hedge P&L: $%.4f\n" result.hedge_pnl_total;
  Printf.printf "  Transaction Costs: $%.4f\n" result.total_transaction_costs;
  Printf.printf "\nMetrics:\n";
  Printf.printf "  Number of Hedges: %d\n" result.num_hedges;
  Printf.printf "  Avg Hedge Interval: %.2f minutes\n" result.avg_hedge_interval_minutes;
  (match result.sharpe_ratio with
   | Some sr -> Printf.printf "  Sharpe Ratio: %.4f\n" sr
   | None -> Printf.printf "  Sharpe Ratio: N/A\n");
  Printf.printf "  Max Drawdown: %.2f%%\n" (result.max_drawdown *. 100.0);
  Printf.printf "  Win Rate: %.2f%%\n" (result.win_rate *. 100.0);
  Printf.printf "\n";

  (* Write output files *)
  let output_dir = Printf.sprintf "pricing/gamma_scalping/output" in
  let summary_file = Printf.sprintf "%s/%s_simulation.csv" output_dir !ticker in
  let pnl_file = Printf.sprintf "%s/%s_pnl_attribution.csv" output_dir !ticker in
  let hedge_file = Printf.sprintf "%s/%s_hedge_log.csv" output_dir !ticker in

  Io.write_simulation_summary ~filename:summary_file ~result;
  Io.write_pnl_timeseries ~filename:pnl_file ~pnl_timeseries:result.pnl_timeseries;
  Io.write_hedge_log ~filename:hedge_file ~hedge_log:result.hedge_log;

  Printf.printf "Output files written to %s/\n" output_dir;
  Printf.printf "\nRun Python visualization:\n";
  Printf.printf "  uv run pricing/gamma_scalping/python/viz/plot_pnl.py --ticker %s\n" !ticker;
  Printf.printf "\n✓ Simulation complete\n"

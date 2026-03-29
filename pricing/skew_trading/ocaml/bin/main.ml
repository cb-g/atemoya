(* Main CLI for Skew Trading *)

open Skew_trading_lib

let () =
  let ticker = ref "TSLA" in
  let operation = ref "measure" in
  let expiry_days = ref 30 in
  let notional = ref 10000.0 in
  let direction_str = ref "long" in
  let contracts = ref 1 in
  let strategy = ref "rr" in

  let usage_msg = "Skew Trading Model - Trade volatility skew using risk reversals, butterflies, and spreads" in
  let speclist = [
    ("-ticker", Arg.Set_string ticker, "Ticker symbol (default: TSLA)");
    ("-op", Arg.Set_string operation, "Operation: measure|signal|backtest|position (default: measure)");
    ("-expiry", Arg.Set_int expiry_days, "Days to expiry (default: 30)");
    ("-notional", Arg.Set_float notional, "Dollar notional for sizing (default: 10000)");
    ("-direction", Arg.Set_string direction_str, "Position direction: long|short (default: long)");
    ("-contracts", Arg.Set_int contracts, "Number of contracts per leg (default: 1)");
    ("-strategy", Arg.Set_string strategy, "Strategy: rr|butterfly (default: rr)");
  ] in

  Arg.parse speclist (fun _ -> ()) usage_msg;

  (* Ensure output directories exist *)
  Io.ensure_output_dirs ();

  let log_file = Printf.sprintf "pricing/skew_trading/log/skew_%s.log" !ticker in
  Io.write_log log_file (Printf.sprintf "=== Skew Trading Analysis: %s ===" !ticker);
  Io.write_log log_file (Printf.sprintf "Operation: %s" !operation);

  (* Read data *)
  let vol_surface_file = Printf.sprintf "pricing/skew_trading/data/%s_vol_surface.json" !ticker in
  let underlying_file = Printf.sprintf "pricing/skew_trading/data/%s_underlying.json" !ticker in
  let config_file = "pricing/skew_trading/data/config.json" in

  let vol_surface = Io.read_vol_surface vol_surface_file in
  let underlying_data = Io.read_underlying_data underlying_file in
  let config = Io.read_skew_config config_file in

  Io.write_log log_file (Printf.sprintf "Spot: $%.2f" underlying_data.spot_price);
  Io.write_log log_file (Printf.sprintf "Dividend Yield: %.2f%%" (underlying_data.dividend_yield *. 100.0));

  match !operation with
  | "measure" ->
      (* Measure current skew *)
      Io.write_log log_file "Measuring volatility skew";

      let expiry = float_of_int !expiry_days /. 365.0 in
      let rate = 0.05 in

      let skew_obs = Skew_measurement.compute_skew_observation
        vol_surface
        underlying_data
        ~rate
        ~expiry
      in

      let output_file = Printf.sprintf "pricing/skew_trading/output/%s_skew.csv" !ticker in
      Io.write_skew_observations_csv output_file [| skew_obs |];

      Io.write_log log_file (Printf.sprintf "RR25: %.4f%% (Call IV - Put IV)" (skew_obs.rr25 *. 100.0));
      Io.write_log log_file (Printf.sprintf "BF25: %.4f%% (Wings - ATM)" (skew_obs.bf25 *. 100.0));
      Io.write_log log_file (Printf.sprintf "Skew Slope: %.4f" skew_obs.skew_slope);
      Io.write_log log_file (Printf.sprintf "ATM Vol: %.2f%%" (skew_obs.atm_vol *. 100.0));
      Io.write_log log_file (Printf.sprintf "25Δ Put Vol: %.2f%%, Strike: $%.2f"
        (skew_obs.put_25d_vol *. 100.0) skew_obs.put_25d_strike);
      Io.write_log log_file (Printf.sprintf "25Δ Call Vol: %.2f%%, Strike: $%.2f"
        (skew_obs.call_25d_vol *. 100.0) skew_obs.call_25d_strike);
      Io.write_log log_file (Printf.sprintf "Output: %s" output_file);

      Printf.printf "✓ Skew measured\n";
      Printf.printf "  RR25: %.4f%% (negative = put skew)\n" (skew_obs.rr25 *. 100.0);
      Printf.printf "  BF25: %.4f%% (positive = smile)\n" (skew_obs.bf25 *. 100.0);
      Printf.printf "  ATM Vol: %.2f%%\n" (skew_obs.atm_vol *. 100.0);
      Printf.printf "  25Δ Put: %.2f%% @ $%.2f\n" (skew_obs.put_25d_vol *. 100.0) skew_obs.put_25d_strike;
      Printf.printf "  25Δ Call: %.2f%% @ $%.2f\n" (skew_obs.call_25d_vol *. 100.0) skew_obs.call_25d_strike

  | "signal" ->
      (* Generate trading signal *)
      Io.write_log log_file "Generating skew trading signal";

      let skew_obs_file =
        let timeseries = Printf.sprintf "pricing/skew_trading/data/%s_skew_timeseries.csv" !ticker in
        let history_yf = Printf.sprintf "pricing/skew_trading/data/%s_skew_history_yfinance.csv" !ticker in
        let history_td = Printf.sprintf "pricing/skew_trading/data/%s_skew_history_thetadata.csv" !ticker in
        if Sys.file_exists timeseries then timeseries
        else if Sys.file_exists history_yf then history_yf
        else if Sys.file_exists history_td then history_td
        else timeseries (* will fail with clear error *)
      in
      let historical_obs = Io.read_skew_observations skew_obs_file in

      if Array.length historical_obs < config.lookback_days then begin
        Printf.eprintf "Error: Not enough historical data (need %d observations, have %d)\n"
          config.lookback_days (Array.length historical_obs);
        exit 1
      end;

      let current_observation = historical_obs.(Array.length historical_obs - 1) in

      let signal = Signal_generation.mean_reversion_signal
        historical_obs
        ~current_observation
        ~config
      in

      let output_file = Printf.sprintf "pricing/skew_trading/output/%s_signal.csv" !ticker in
      Io.write_signals_csv output_file [| signal |];

      let signal_str = match signal.signal_type with
        | Types.LongSkew _ -> "LONG SKEW (buy call, sell put)"
        | Types.ShortSkew _ -> "SHORT SKEW (sell call, buy put)"
        | Types.Neutral _ -> "NEUTRAL"
      in

      let reason = match signal.signal_type with
        | Types.LongSkew { reason; _ } -> reason
        | Types.ShortSkew { reason; _ } -> reason
        | Types.Neutral { reason } -> reason
      in

      Io.write_log log_file (Printf.sprintf "Signal: %s" signal_str);
      Io.write_log log_file (Printf.sprintf "Reason: %s" reason);
      Io.write_log log_file (Printf.sprintf "Confidence: %.2f" signal.confidence);
      Io.write_log log_file (Printf.sprintf "Position Size: $%.2f" signal.position_size);
      Io.write_log log_file (Printf.sprintf "Output: %s" output_file);

      Printf.printf "✓ Signal generated\n";
      Printf.printf "  Signal: %s\n" signal_str;
      Printf.printf "  Reason: %s\n" reason;
      Printf.printf "  Confidence: %.2f\n" signal.confidence;
      Printf.printf "  Position Size: $%.2f\n" signal.position_size

  | "position" ->
      let expiry = float_of_int !expiry_days /. 365.0 in
      let rate = 0.05 in
      let spot = underlying_data.spot_price in
      let dividend = underlying_data.dividend_yield in

      let direction = match String.lowercase_ascii !direction_str with
        | "short" -> `Short
        | _ -> `Long
      in

      let raw_position = match String.lowercase_ascii !strategy with
        | "butterfly" | "bf" ->
            Io.write_log log_file "Building butterfly position";
            (* Use 25Δ put, ATM, 25Δ call as strikes *)
            let call_strike = match Skew_measurement.find_delta_strike Call ~target_delta:0.25 ~spot ~expiry ~rate ~dividend vol_surface with
              | Some k -> k | None -> spot *. 1.05 in
            let put_strike = match Skew_measurement.find_delta_strike Put ~target_delta:(-0.25) ~spot ~expiry ~rate ~dividend vol_surface with
              | Some k -> k | None -> spot *. 0.95 in
            let atm_strike = spot in
            Skew_strategies.build_butterfly
              vol_surface underlying_data ~rate ~expiry
              ~strikes:(put_strike, atm_strike, call_strike)
              ~notional:!notional
        | _ ->
            Io.write_log log_file "Building risk reversal position";
            Skew_strategies.build_risk_reversal
              vol_surface underlying_data ~rate ~expiry
              ~delta_target:0.25 ~direction ~notional:!notional
      in

      (* Rescale to exact contract count *)
      let position =
        if !contracts > 0 then
          let target_qty = float_of_int !contracts in
          let current_qty = abs_float raw_position.Types.legs.(0).Types.quantity in
          let scale = if current_qty > 0.0 then target_qty /. current_qty else 1.0 in
          let rescale_leg leg = { leg with Types.quantity = leg.Types.quantity *. scale } in
          (* For SHORT WINGS (sell butterfly), flip all signs *)
          let dir_flip = match String.lowercase_ascii !strategy, direction with
            | ("butterfly" | "bf"), `Short -> -1.0
            | _ -> 1.0
          in
          let final_scale = scale *. dir_flip in
          let rescale_leg_dir leg = { (rescale_leg leg) with Types.quantity = leg.Types.quantity *. final_scale } in
          { raw_position with
            Types.legs = Array.map rescale_leg_dir raw_position.Types.legs;
            total_cost = raw_position.Types.total_cost *. final_scale;
            total_delta = raw_position.Types.total_delta *. final_scale;
            total_vega = raw_position.Types.total_vega *. final_scale;
            total_gamma = raw_position.Types.total_gamma *. final_scale;
          }
        else raw_position
      in

      let output_file = Printf.sprintf "pricing/skew_trading/output/%s_position.csv" !ticker in
      Io.write_positions_csv output_file [| position |];

      let strategy_label = match String.lowercase_ascii !strategy with
        | "butterfly" | "bf" -> "butterfly"
        | _ -> "risk reversal"
      in
      let dir_label = match direction with `Long -> "LONG" | `Short -> "SHORT" in

      Io.write_log log_file (Printf.sprintf "Strategy: %s %s" dir_label strategy_label);
      Io.write_log log_file (Printf.sprintf "Number of Legs: %d" (Array.length position.legs));
      Io.write_log log_file (Printf.sprintf "Total Cost: $%.2f" position.total_cost);
      Io.write_log log_file (Printf.sprintf "Total Delta: %.4f" position.total_delta);
      Io.write_log log_file (Printf.sprintf "Total Vega: %.2f" position.total_vega);
      Io.write_log log_file (Printf.sprintf "Total Gamma: %.4f" position.total_gamma);
      Io.write_log log_file (Printf.sprintf "Output: %s" output_file);

      Printf.printf "✓ %s %s position built\n" dir_label strategy_label;
      Printf.printf "  Legs: %d\n" (Array.length position.legs);
      Array.iteri (fun i leg ->
        let opt_str = match leg.Types.option_type with Types.Call -> "CALL" | Types.Put -> "PUT" in
        let dir = if leg.Types.quantity > 0.0 then "BUY" else "SELL" in
        Printf.printf "  Leg %d: %s %.0f %s strike=$%.2f expiry=%.0fd price=$%.2f\n"
          (i + 1) dir (abs_float leg.Types.quantity) opt_str
          leg.Types.strike (leg.Types.expiry *. 365.0) leg.Types.entry_price
      ) position.legs;
      Printf.printf "  Cost: $%.2f\n" position.total_cost;
      Printf.printf "  Delta: %.4f\n" position.total_delta;
      Printf.printf "  Vega: %.2f\n" position.total_vega;
      Printf.printf "  Gamma: %.4f\n" position.total_gamma

  | "backtest" ->
      (* Backtest mean reversion strategy *)
      Io.write_log log_file "Backtesting skew mean reversion strategy";

      let skew_obs_file =
        let timeseries = Printf.sprintf "pricing/skew_trading/data/%s_skew_timeseries.csv" !ticker in
        let history_yf = Printf.sprintf "pricing/skew_trading/data/%s_skew_history_yfinance.csv" !ticker in
        let history_td = Printf.sprintf "pricing/skew_trading/data/%s_skew_history_thetadata.csv" !ticker in
        if Sys.file_exists timeseries then timeseries
        else if Sys.file_exists history_yf then history_yf
        else if Sys.file_exists history_td then history_td
        else timeseries
      in

      let skew_observations = Io.read_skew_observations skew_obs_file in

      if Array.length skew_observations < config.lookback_days then begin
        Printf.eprintf "Error: Not enough historical data (need %d observations, have %d)\n"
          config.lookback_days (Array.length skew_observations);
        exit 1
      end;

      (* Create dummy spot prices and vol surfaces for backtest *)
      let n = Array.length skew_observations in
      let spot_prices = Array.make n underlying_data.spot_price in
      let vol_surfaces = Array.init n (fun i ->
        (skew_observations.(i).Types.timestamp, vol_surface)
      ) in

      let pnl_history = Signal_generation.backtest_strategy
        ~skew_observations
        ~spot_prices
        ~vol_surfaces
        ~config
      in

      let output_file = Printf.sprintf "pricing/skew_trading/output/%s_backtest.csv" !ticker in
      Io.write_pnl_csv output_file pnl_history;

      let final_pnl = if Array.length pnl_history > 0 then
        pnl_history.(Array.length pnl_history - 1)
      else
        {
          Types.timestamp = 0.0;
          position = None;
          mark_to_market = 0.0;
          realized_pnl = 0.0;
          cumulative_pnl = 0.0;
          sharpe_ratio = None;
          max_drawdown = None;
          sortino_ratio = None;
          return_skewness = None;
        }
      in

      let fmt_metric name = function
        | Some v -> Printf.sprintf "%s: %.2f" name v
        | None -> Printf.sprintf "%s: N/A" name
      in

      Io.write_log log_file (Printf.sprintf "Backtest complete: %d observations" (Array.length pnl_history));
      Io.write_log log_file (Printf.sprintf "Cumulative P&L: $%.2f" final_pnl.cumulative_pnl);
      Io.write_log log_file (fmt_metric "Sharpe Ratio" final_pnl.sharpe_ratio);
      Io.write_log log_file (fmt_metric "Max Drawdown" final_pnl.max_drawdown);
      Io.write_log log_file (fmt_metric "Sortino Ratio" final_pnl.sortino_ratio);
      Io.write_log log_file (fmt_metric "Return Skewness" final_pnl.return_skewness);
      Io.write_log log_file (Printf.sprintf "Output: %s" output_file);

      Printf.printf "✓ Backtest complete\n";
      Printf.printf "  Observations: %d\n" (Array.length pnl_history);
      Printf.printf "  Cumulative P&L: $%.2f\n" final_pnl.cumulative_pnl;
      Printf.printf "  %s\n" (fmt_metric "Sharpe Ratio" final_pnl.sharpe_ratio);
      Printf.printf "  %s\n" (fmt_metric "Max Drawdown" final_pnl.max_drawdown);
      Printf.printf "  %s\n" (fmt_metric "Sortino Ratio" final_pnl.sortino_ratio);
      Printf.printf "  %s\n" (fmt_metric "Return Skewness" final_pnl.return_skewness)

  | _ ->
      Printf.eprintf "Error: Unknown operation '%s'\n" !operation;
      Printf.eprintf "Valid operations: measure, signal, position, backtest\n";
      exit 1

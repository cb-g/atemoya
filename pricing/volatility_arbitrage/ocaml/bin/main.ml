(* Volatility Arbitrage CLI *)

open Volatility_arbitrage

let () =
  (* Command-line arguments *)
  let ticker = ref "" in
  let operation = ref "realized_vol" in
  let data_dir = ref "pricing/volatility_arbitrage/data" in
  let output_dir = ref "pricing/volatility_arbitrage/output" in
  let rv_window = ref 21 in
  let estimator = ref "yang_zhang" in
  let forecast_method = ref "garch" in
  let forecast_horizon = ref 30 in

  let speclist = [
    ("-ticker", Arg.Set_string ticker, "Ticker symbol (e.g., AAPL)");
    ("-operation", Arg.Set_string operation,
     "Operation: realized_vol, forecast_vol, detect_arbitrage, compare_iv_rv, all");
    ("-data-dir", Arg.Set_string data_dir, "Data directory");
    ("-output-dir", Arg.Set_string output_dir, "Output directory");
    ("-rv-window", Arg.Set_int rv_window, "Realized vol window (days, default: 21)");
    ("-estimator", Arg.Set_string estimator,
     "RV estimator: close_to_close, parkinson, garman_klass, rogers_satchell, yang_zhang (default)");
    ("-forecast-method", Arg.Set_string forecast_method,
     "Forecast method: garch, ewma, har, historical (default: garch)");
    ("-forecast-horizon", Arg.Set_int forecast_horizon, "Forecast horizon (days, default: 30)");
  ] in

  let usage_msg = "Volatility Arbitrage Model - detect vol mispricing and arbitrage opportunities" in
  Arg.parse speclist (fun _ -> ()) usage_msg;

  (* Validate inputs *)
  if !ticker = "" then begin
    Printf.eprintf "Error: -ticker is required\n";
    exit 1
  end;

  Printf.printf "=== Volatility Arbitrage Analysis: %s ===\n" !ticker;
  Printf.printf "Operation: %s\n\n" !operation;

  try
    (* File paths *)
    let ohlc_file = Printf.sprintf "%s/%s_ohlc.csv" !data_dir !ticker in
    let underlying_file = Printf.sprintf "%s/%s_underlying.csv" !data_dir !ticker in
    let vol_surface_file = Printf.sprintf "%s/%s_vol_surface.json" !data_dir !ticker in

    (* Load data *)
    let has_ohlc = Sys.file_exists ohlc_file in
    let has_underlying = Sys.file_exists underlying_file in
    let has_vol_surface = Sys.file_exists vol_surface_file in

    (* Operation: Compute realized volatility *)
    if !operation = "realized_vol" || !operation = "all" then begin
      Printf.printf "[1/4] Computing realized volatility...\n";

      if not has_ohlc then begin
        Printf.eprintf "Error: OHLC data not found at %s\n" ohlc_file;
        Printf.eprintf "Run: uv run pricing/volatility_arbitrage/python/fetch/fetch_historical.py --ticker %s\n" !ticker;
        exit 1
      end;

      let ohlc_data = Io.read_ohlc_csv ~filename:ohlc_file in
      Printf.printf "  Loaded %d OHLC bars\n" (Array.length ohlc_data);

      (* Compute RV using selected estimator *)
      let rv_data = match !estimator with
        | "close_to_close" -> Realized_vol.close_to_close ohlc_data ~window_days:!rv_window
        | "parkinson" -> Realized_vol.parkinson ohlc_data ~window_days:!rv_window
        | "garman_klass" -> Realized_vol.garman_klass ohlc_data ~window_days:!rv_window
        | "rogers_satchell" -> Realized_vol.rogers_satchell ohlc_data ~window_days:!rv_window
        | "yang_zhang" -> Realized_vol.yang_zhang ohlc_data ~window_days:!rv_window
        | _ ->
            Printf.eprintf "Unknown estimator: %s\n" !estimator;
            exit 1
      in

      Printf.printf "  Computed %d realized vol estimates\n" (Array.length rv_data);

      (* Get latest *)
      match Realized_vol.get_latest_rv rv_data with
      | Some rv ->
          Printf.printf "  Latest RV (%s, %d-day): %.2f%%\n"
            (match rv.estimator with
             | Types.CloseToClose -> "Close-to-Close"
             | Parkinson -> "Parkinson"
             | GarmanKlass -> "Garman-Klass"
             | RogersSatchell -> "Rogers-Satchell"
             | YangZhang -> "Yang-Zhang")
            rv.window_days
            (rv.volatility *. 100.0);

          (* Save to CSV *)
          let rv_output_file = Printf.sprintf "%s/%s_realized_vol.csv" !output_dir !ticker in
          Io.write_realized_vol_csv ~filename:rv_output_file ~realized_vols:rv_data;
          Printf.printf "  Saved to %s\n\n" rv_output_file

      | None ->
          Printf.eprintf "  No realized vol estimates computed\n\n"
    end;

    (* Operation: Forecast volatility *)
    if !operation = "forecast_vol" || !operation = "all" then begin
      Printf.printf "[2/4] Forecasting volatility...\n";

      let rv_file = Printf.sprintf "%s/%s_realized_vol.csv" !output_dir !ticker in
      if not (Sys.file_exists rv_file) then begin
        Printf.eprintf "Error: Realized vol file not found. Run with -operation realized_vol first.\n";
        exit 1
      end;

      let rv_data = Io.read_realized_vol_csv ~filename:rv_file in
      Printf.printf "  Loaded %d RV observations\n" (Array.length rv_data);

      (* Generate forecast *)
      let forecast = match !forecast_method with
        | "historical" ->
            Vol_forecast.historical_forecast ~realized_vols:rv_data ~window_days:!rv_window

        | "har" ->
            Vol_forecast.har_forecast ~realized_vols:rv_data ~horizon_days:!forecast_horizon

        | "ewma" ->
            (* Need returns for EWMA *)
            if not has_ohlc then begin
              Printf.eprintf "Error: OHLC data needed for EWMA. File: %s\n" ohlc_file;
              exit 1
            end;
            let ohlc_data = Io.read_ohlc_csv ~filename:ohlc_file in
            let closes = Array.map (fun bar -> bar.Types.close) ohlc_data in
            let n = Array.length closes in
            let returns = Array.init (n - 1) (fun i -> log (closes.(i+1) /. closes.(i))) in
            Vol_forecast.ewma_forecast ~returns ~lambda:0.94 ~horizon_days:!forecast_horizon

        | "garch" ->
            (* Need returns for GARCH *)
            if not has_ohlc then begin
              Printf.eprintf "Error: OHLC data needed for GARCH. File: %s\n" ohlc_file;
              exit 1
            end;
            let ohlc_data = Io.read_ohlc_csv ~filename:ohlc_file in
            let closes = Array.map (fun bar -> bar.Types.close) ohlc_data in
            let n = Array.length closes in
            let returns = Array.init (n - 1) (fun i -> log (closes.(i+1) /. closes.(i))) in

            let params = Vol_forecast.estimate_garch_params ~returns in
            let current_var = Vol_forecast.ewma_variance ~returns ~lambda:0.94 in
            Vol_forecast.garch_forecast ~params ~current_variance:current_var ~horizon_days:!forecast_horizon

        | _ ->
            Printf.eprintf "Unknown forecast method: %s\n" !forecast_method;
            exit 1
      in

      Printf.printf "  %d-day forecast (%s): %.2f%%\n"
        forecast.horizon_days
        (match forecast.forecast_type with
         | Types.GARCH _ -> "GARCH"
         | EWMA _ -> "EWMA"
         | HAR _ -> "HAR"
         | Historical _ -> "Historical")
        (forecast.forecast_vol *. 100.0);

      (match forecast.confidence_interval with
       | Some (lower, upper) ->
           Printf.printf "  95%% CI: [%.2f%%, %.2f%%]\n"
             (lower *. 100.0) (upper *. 100.0)
       | None -> ());

      (* Save forecast *)
      let forecast_file = Printf.sprintf "%s/%s_vol_forecast.json" !output_dir !ticker in
      Io.write_vol_forecast_json ~filename:forecast_file ~forecast;
      Printf.printf "  Saved to %s\n\n" forecast_file
    end;

    (* Operation: Detect arbitrage *)
    if !operation = "detect_arbitrage" || !operation = "all" then begin
      Printf.printf "[3/4] Detecting arbitrage opportunities...\n";

      if not (has_vol_surface && has_underlying) then begin
        Printf.eprintf "Error: Vol surface and underlying data required\n";
        Printf.eprintf "  Vol surface: %s (exists: %b)\n" vol_surface_file has_vol_surface;
        Printf.eprintf "  Underlying: %s (exists: %b)\n" underlying_file has_underlying;
        exit 1
      end;

      let vol_surface = Io.read_vol_surface ~filename:vol_surface_file in
      let underlying = Io.read_underlying_data ~filename:underlying_file in
      let config = Types.default_config in

      Printf.printf "  Spot: $%.2f\n" underlying.spot_price;
      Printf.printf "  Dividend yield: %.2f%%\n" (underlying.dividend_yield *. 100.0);

      (* Scan for arbitrage *)
      let signals = Arbitrage.scan_for_arbitrage vol_surface
        ~iv_observations:[||]  (* Could load if available *)
        ~underlying
        ~rate:0.05  (* Assume 5% risk-free rate *)
        ~config
      in

      Printf.printf "  Found %d arbitrage opportunities\n" (Array.length signals);

      if Array.length signals > 0 then begin
        (* Sort by profit *)
        let sorted_signals = Arbitrage.sort_by_profit signals in

        Printf.printf "\n  Top opportunities:\n";
        Array.iteri (fun i (signal : Types.arbitrage_signal) ->
          if i < 5 then begin  (* Show top 5 *)
            Printf.printf "    %d. %s: $%.2f expected profit (confidence: %.0f%%)\n"
              (i + 1)
              (match signal.arb_type with
               | Types.ButterflyViolation _ -> "Butterfly"
               | CalendarViolation _ -> "Calendar"
               | PutCallParity _ -> "Put-Call Parity"
               | VerticalSpread _ -> "Vertical Spread")
              signal.expected_profit
              (signal.confidence *. 100.0)
          end
        ) sorted_signals;

        (* Save signals *)
        let signals_file = Printf.sprintf "%s/%s_arbitrage_signals.csv" !output_dir !ticker in
        Io.write_arbitrage_signals_csv ~filename:signals_file ~signals:sorted_signals;
        Printf.printf "\n  Saved to %s\n\n" signals_file
      end else begin
        Printf.printf "  No arbitrage violations detected.\n\n"
      end
    end;

    (* Operation: Compare IV vs RV *)
    if !operation = "compare_iv_rv" || !operation = "all" then begin
      Printf.printf "[4/4] Comparing implied vs realized volatility...\n";

      (* This would require ATM IV data, which we'll add in Python *)
      Printf.printf "  IV vs RV comparison available via visualization scripts.\n";
      Printf.printf "  Run: uv run pricing/volatility_arbitrage/python/viz/plot_iv_vs_rv.py --ticker %s\n\n" !ticker
    end;

    Printf.printf "✓ Analysis complete for %s\n" !ticker;
    Printf.printf "  Results saved to %s/\n" !output_dir

  with
  | Sys_error msg ->
      Printf.eprintf "System error: %s\n" msg;
      exit 1
  | Failure msg ->
      Printf.eprintf "Error: %s\n" msg;
      exit 1
  | e ->
      Printf.eprintf "Unexpected error: %s\n" (Printexc.to_string e);
      exit 1

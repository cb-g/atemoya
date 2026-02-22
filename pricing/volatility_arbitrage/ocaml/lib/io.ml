(* I/O implementation for volatility arbitrage *)

open Types

(* Read OHLC CSV: timestamp,open,high,low,close,volume *)
let read_ohlc_csv ~filename =
  let rows = Csv.load filename in
  match rows with
  | [] -> [||]
  | _header :: data_rows ->
      Array.of_list (List.filter_map (fun row ->
        match row with
        | [timestamp_str; open_str; high_str; low_str; close_str; volume_str] ->
            (try
              Some {
                timestamp = float_of_string timestamp_str;
                open_ = float_of_string open_str;
                high = float_of_string high_str;
                low = float_of_string low_str;
                close = float_of_string close_str;
                volume = float_of_string volume_str;
              }
            with Failure _ -> None)
        | _ -> None
      ) data_rows)

(* Read IV observations CSV: timestamp,ticker,strike,expiry,option_type,implied_vol,bid,ask *)
let read_iv_observations ~filename =
  let rows = Csv.load filename in
  match rows with
  | [] -> [||]
  | _header :: data_rows ->
      Array.of_list (List.filter_map (fun row ->
        match row with
        | [timestamp_str; ticker; strike_str; expiry_str; option_type_str; iv_str; bid_str; ask_str] ->
            (try
              let option_type = if option_type_str = "call" then Call else Put in
              let bid = float_of_string bid_str in
              let ask = float_of_string ask_str in
              Some {
                timestamp = float_of_string timestamp_str;
                ticker;
                strike = float_of_string strike_str;
                expiry = float_of_string expiry_str;
                option_type;
                implied_vol = float_of_string iv_str;
                bid;
                ask;
                mid_price = (bid +. ask) /. 2.0;
              }
            with Failure _ -> None)
        | _ -> None
      ) data_rows)

(* Read underlying data CSV: ticker,spot_price,dividend_yield *)
let read_underlying_data ~filename =
  let rows = Csv.load filename in
  match rows with
  | _header :: [ticker; spot_str; div_str] :: _ ->
      {
        ticker;
        spot_price = float_of_string spot_str;
        dividend_yield = float_of_string div_str;
      }
  | _ -> failwith "Invalid underlying data CSV format"

(* Read vol surface JSON *)
let read_vol_surface ~filename =
  let json = Yojson.Safe.from_file filename in
  let open Yojson.Safe.Util in

  let surface_type = json |> member "type" |> to_string in

  match surface_type with
  | "SVI" ->
      let params_json = json |> member "params" |> to_list in
      let params = List.map (fun p ->
        {
          expiry = p |> member "expiry" |> to_float;
          a = p |> member "a" |> to_float;
          b = p |> member "b" |> to_float;
          rho = p |> member "rho" |> to_float;
          m = p |> member "m" |> to_float;
          sigma = p |> member "sigma" |> to_float;
        }
      ) params_json in
      SVI (Array.of_list params)

  | "SABR" ->
      let params_json = json |> member "params" |> to_list in
      let params = List.map (fun p ->
        {
          expiry = p |> member "expiry" |> to_float;
          alpha = p |> member "alpha" |> to_float;
          beta = p |> member "beta" |> to_float;
          rho = p |> member "rho" |> to_float;
          nu = p |> member "nu" |> to_float;
        }
      ) params_json in
      SABR (Array.of_list params)

  | _ -> failwith "Unknown vol surface type"

(* Read realized vol CSV: timestamp,estimator,volatility,window_days *)
let read_realized_vol_csv ~filename =
  let rows = Csv.load filename in
  match rows with
  | [] -> [||]
  | _header :: data_rows ->
      Array.of_list (List.filter_map (fun row ->
        match row with
        | [timestamp_str; estimator_str; volatility_str; window_str] ->
            (try
              let estimator = match estimator_str with
                | "CloseToClose" -> CloseToClose
                | "Parkinson" -> Parkinson
                | "GarmanKlass" -> GarmanKlass
                | "RogersSatchell" -> RogersSatchell
                | "YangZhang" -> YangZhang
                | _ -> YangZhang
              in
              Some {
                timestamp = float_of_string timestamp_str;
                estimator;
                volatility = float_of_string volatility_str;
                window_days = int_of_string window_str;
              }
            with Failure _ -> None)
        | _ -> None
      ) data_rows)

(* Write realized vol CSV *)
let write_realized_vol_csv ~filename ~realized_vols =
  let header = ["timestamp"; "estimator"; "volatility"; "window_days"] in
  let rows = Array.map (fun rv ->
    let estimator_str = match rv.estimator with
      | CloseToClose -> "CloseToClose"
      | Parkinson -> "Parkinson"
      | GarmanKlass -> "GarmanKlass"
      | RogersSatchell -> "RogersSatchell"
      | YangZhang -> "YangZhang"
    in
    [
      string_of_float rv.timestamp;
      estimator_str;
      string_of_float rv.volatility;
      string_of_int rv.window_days;
    ]
  ) realized_vols |> Array.to_list in

  Csv.save filename (header :: rows)

(* Write arbitrage signals CSV *)
let write_arbitrage_signals_csv ~filename ~signals =
  let header = ["timestamp"; "ticker"; "type"; "details"; "confidence"; "expected_profit"] in
  let rows = Array.map (fun signal ->
    let (arb_type_str, details) = match signal.arb_type with
      | ButterflyViolation { lower_strike; middle_strike; upper_strike; violation_amount } ->
          ("Butterfly",
           Printf.sprintf "K1=%.2f K2=%.2f K3=%.2f violation=%.2f"
             lower_strike middle_strike upper_strike violation_amount)
      | CalendarViolation { strike; near_expiry; far_expiry; violation_amount } ->
          ("Calendar",
           Printf.sprintf "K=%.2f T1=%.3f T2=%.3f violation=%.2f"
             strike near_expiry far_expiry violation_amount)
      | PutCallParity { strike; expiry; violation_amount } ->
          ("PutCallParity",
           Printf.sprintf "K=%.2f T=%.3f violation=%.2f"
             strike expiry violation_amount)
      | VerticalSpread { lower_strike; upper_strike; expiry; violation_amount } ->
          ("VerticalSpread",
           Printf.sprintf "K1=%.2f K2=%.2f T=%.3f violation=%.2f"
             lower_strike upper_strike expiry violation_amount)
    in
    [
      string_of_float signal.timestamp;
      signal.ticker;
      arb_type_str;
      details;
      string_of_float signal.confidence;
      string_of_float signal.expected_profit;
    ]
  ) signals |> Array.to_list in

  Csv.save filename (header :: rows)

(* Write trading signals CSV *)
let write_trading_signals_csv ~filename ~signals =
  let header = ["timestamp"; "type"; "ticker"; "details"; "confidence"; "expected_sharpe"; "max_position_size"] in
  let rows = Array.map (fun signal ->
    let (signal_type_str, ticker, details) = match signal.signal_type with
      | ArbitrageSignal arb ->
          ("Arbitrage", arb.ticker, "See arbitrage signals CSV")
      | VolMispricingSignal { ticker; implied_vol; forecast_vol; mispricing_pct; _ } ->
          ("VolMispricing", ticker,
           Printf.sprintf "IV=%.1f%% FV=%.1f%% mispricing=%.1f%%"
             (implied_vol *. 100.0) (forecast_vol *. 100.0) mispricing_pct)
      | DispersionSignal disp ->
          ("Dispersion", disp.index_ticker,
           Printf.sprintf "impl_corr=%.2f expected_pnl=%.2f" disp.implied_correlation disp.expected_pnl)
      | VarianceSignal vs ->
          ("Variance", vs.ticker,
           Printf.sprintf "strike_var=%.4f vega_notional=%.2f" vs.strike_var vs.vega_notional)
    in

    let sharpe_str = match signal.expected_sharpe with
      | Some s -> string_of_float s
      | None -> "N/A"
    in

    [
      string_of_float signal.timestamp;
      signal_type_str;
      ticker;
      details;
      string_of_float signal.confidence;
      sharpe_str;
      string_of_float signal.max_position_size;
    ]
  ) signals |> Array.to_list in

  Csv.save filename (header :: rows)

(* Write vol forecast JSON *)
let write_vol_forecast_json ~filename ~forecast =
  let forecast_type_json = match forecast.forecast_type with
    | GARCH { omega; alpha; beta } ->
        `Assoc [
          ("type", `String "GARCH");
          ("omega", `Float omega);
          ("alpha", `Float alpha);
          ("beta", `Float beta);
        ]
    | EWMA { lambda } ->
        `Assoc [
          ("type", `String "EWMA");
          ("lambda", `Float lambda);
        ]
    | HAR { beta_d; beta_w; beta_m } ->
        `Assoc [
          ("type", `String "HAR");
          ("beta_d", `Float beta_d);
          ("beta_w", `Float beta_w);
          ("beta_m", `Float beta_m);
        ]
    | Historical { window } ->
        `Assoc [
          ("type", `String "Historical");
          ("window", `Int window);
        ]
  in

  let ci_json = match forecast.confidence_interval with
    | Some (lower, upper) ->
        `Assoc [("lower", `Float lower); ("upper", `Float upper)]
    | None -> `Null
  in

  let json = `Assoc [
    ("timestamp", `Float forecast.timestamp);
    ("forecast_type", forecast_type_json);
    ("forecast_vol", `Float forecast.forecast_vol);
    ("confidence_interval", ci_json);
    ("horizon_days", `Int forecast.horizon_days);
  ] in

  Yojson.Safe.to_file filename json

(* Write config JSON *)
let write_config_json ~filename ~config =
  let json = `Assoc [
    ("min_arbitrage_profit", `Float config.min_arbitrage_profit);
    ("min_vol_mispricing_pct", `Float config.min_vol_mispricing_pct);
    ("max_transaction_cost_bps", `Float config.max_transaction_cost_bps);
    ("target_sharpe_ratio", `Float config.target_sharpe_ratio);
    ("rebalance_threshold_delta", `Float config.rebalance_threshold_delta);
    ("garch_window_days", `Int config.garch_window_days);
    ("rv_window_days", `Int config.rv_window_days);
    ("mc_paths", `Int config.mc_paths);
    ("mc_steps_per_day", `Int config.mc_steps_per_day);
  ] in

  Yojson.Safe.to_file filename json

(* Read config JSON *)
let read_config_json ~filename =
  let json = Yojson.Safe.from_file filename in
  let open Yojson.Safe.Util in

  {
    min_arbitrage_profit = json |> member "min_arbitrage_profit" |> to_float;
    min_vol_mispricing_pct = json |> member "min_vol_mispricing_pct" |> to_float;
    max_transaction_cost_bps = json |> member "max_transaction_cost_bps" |> to_float;
    target_sharpe_ratio = json |> member "target_sharpe_ratio" |> to_float;
    rebalance_threshold_delta = json |> member "rebalance_threshold_delta" |> to_float;
    garch_window_days = json |> member "garch_window_days" |> to_int;
    rv_window_days = json |> member "rv_window_days" |> to_int;
    mc_paths = json |> member "mc_paths" |> to_int;
    mc_steps_per_day = json |> member "mc_steps_per_day" |> to_int;
  }

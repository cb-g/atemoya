(* I/O operations for skew trading *)

open Types

(* ========================================================================== *)
(* CSV Reading *)
(* ========================================================================== *)

let read_option_chain filename =
  try
    let ic = open_in filename in
    let lines = ref [] in
    begin
      try
        (* Skip header *)
        let _ = input_line ic in
        while true do
          let line = input_line ic in
          lines := line :: !lines
        done
      with End_of_file -> close_in ic
    end;

    let parsed = List.filter_map (fun line ->
      let parts = String.split_on_char ',' line in
      match parts with
      | strike_str :: expiry_str :: bid_str :: ask_str :: volume_str :: _ ->
          begin try
            let strike = float_of_string strike_str in
            let expiry = float_of_string expiry_str in
            let bid = float_of_string bid_str in
            let ask = float_of_string ask_str in
            let volume = int_of_string volume_str in
            Some (strike, expiry, bid, ask, volume)
          with Failure _ -> None
          end
      | _ -> None
    ) (List.rev !lines) in

    Array.of_list parsed
  with Sys_error _ -> [||]

let read_skew_observations filename =
  try
    let ic = open_in filename in
    let lines = ref [] in
    begin
      try
        (* Skip header *)
        let _ = input_line ic in
        while true do
          let line = input_line ic in
          lines := line :: !lines
        done
      with End_of_file -> close_in ic
    end;

    let parsed = List.filter_map (fun line ->
      let parts = String.split_on_char ',' line in
      match parts with
      | ts_str :: ticker :: expiry_str :: rr25_str :: bf25_str :: slope_str :: atm_str
        :: put_vol_str :: call_vol_str :: put_strike_str :: call_strike_str :: _ ->
          begin try
            Some {
              timestamp = float_of_string ts_str;
              ticker;
              expiry = float_of_string expiry_str;
              rr25 = float_of_string rr25_str;
              bf25 = float_of_string bf25_str;
              skew_slope = float_of_string slope_str;
              atm_vol = float_of_string atm_str;
              put_25d_vol = float_of_string put_vol_str;
              call_25d_vol = float_of_string call_vol_str;
              put_25d_strike = float_of_string put_strike_str;
              call_25d_strike = float_of_string call_strike_str;
            }
          with Failure _ -> None
          end
      | _ -> None
    ) (List.rev !lines) in

    Array.of_list parsed
  with Sys_error _ -> [||]

(* ========================================================================== *)
(* JSON Reading *)
(* ========================================================================== *)

let read_vol_surface filename =
  try
    let json = Yojson.Safe.from_file filename in
    let open Yojson.Safe.Util in

    let model_type = json |> member "model" |> to_string in

    match model_type with
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
    | _ ->
        (* Default fallback *)
        SVI [||]
  with Sys_error _ | Yojson.Safe.Util.Type_error _ | Yojson.Json_error _ ->
    SVI [||]

let read_underlying_data filename =
  try
    let json = Yojson.Safe.from_file filename in
    let open Yojson.Safe.Util in

    {
      ticker = json |> member "ticker" |> to_string;
      spot_price = json |> member "spot_price" |> to_float;
      dividend_yield = json |> member "dividend_yield" |> to_float;
    }
  with Sys_error _ | Yojson.Safe.Util.Type_error _ | Yojson.Json_error _ ->
    { ticker = "UNKNOWN"; spot_price = 100.0; dividend_yield = 0.0 }

let read_skew_config filename =
  try
    let json = Yojson.Safe.from_file filename in
    let open Yojson.Safe.Util in

    {
      rr25_mean_reversion_threshold = json |> member "rr25_mean_reversion_threshold" |> to_float;
      min_confidence = json |> member "min_confidence" |> to_float;
      target_vega_notional = json |> member "target_vega_notional" |> to_float;
      max_gamma_risk = json |> member "max_gamma_risk" |> to_float;
      transaction_cost_bps = json |> member "transaction_cost_bps" |> to_float;
      delta_hedge = json |> member "delta_hedge" |> to_bool;
      lookback_days = json |> member "lookback_days" |> to_int;
    }
  with Sys_error _ | Yojson.Safe.Util.Type_error _ | Yojson.Json_error _ ->
    (* Default configuration *)
    {
      rr25_mean_reversion_threshold = 2.0;
      min_confidence = 0.5;
      target_vega_notional = 10000.0;
      max_gamma_risk = 500.0;
      transaction_cost_bps = 5.0;
      delta_hedge = true;
      lookback_days = 60;
    }

(* ========================================================================== *)
(* CSV Writing *)
(* ========================================================================== *)

let write_skew_observations_csv filename (observations : skew_observation array) =
  let oc = open_out filename in
  Printf.fprintf oc "timestamp,ticker,expiry,rr25,bf25,skew_slope,atm_vol,put_25d_vol,call_25d_vol,put_25d_strike,call_25d_strike\n";
  Array.iter (fun (obs : skew_observation) ->
    Printf.fprintf oc "%.0f,%s,%.4f,%.6f,%.6f,%.6f,%.4f,%.4f,%.4f,%.2f,%.2f\n"
      obs.timestamp
      obs.ticker
      obs.expiry
      obs.rr25
      obs.bf25
      obs.skew_slope
      obs.atm_vol
      obs.put_25d_vol
      obs.call_25d_vol
      obs.put_25d_strike
      obs.call_25d_strike
  ) observations;
  close_out oc

let write_signals_csv filename signals =
  let oc = open_out filename in
  Printf.fprintf oc "timestamp,ticker,signal_type,reason,confidence,position_size\n";
  Array.iter (fun signal ->
    let (signal_type_str, reason) = match signal.signal_type with
      | LongSkew { reason; _ } -> ("LONG_SKEW", reason)
      | ShortSkew { reason; _ } -> ("SHORT_SKEW", reason)
      | Neutral { reason } -> ("NEUTRAL", reason)
    in
    Printf.fprintf oc "%.0f,%s,%s,\"%s\",%.2f,%.2f\n"
      signal.timestamp
      signal.ticker
      signal_type_str
      (String.escaped reason)
      signal.confidence
      signal.position_size
  ) signals;
  close_out oc

let write_positions_csv filename positions =
  let oc = open_out filename in
  Printf.fprintf oc "ticker,strategy_type,num_legs,total_cost,total_delta,total_vega,total_gamma\n";
  Array.iter (fun pos ->
    let strategy_str = match pos.strategy_type with
      | RiskReversal _ -> "RISK_REVERSAL"
      | Butterfly _ -> "BUTTERFLY"
      | RatioSpread _ -> "RATIO_SPREAD"
      | CalendarSpread _ -> "CALENDAR_SPREAD"
    in
    Printf.fprintf oc "%s,%s,%d,%.2f,%.4f,%.2f,%.4f\n"
      pos.ticker
      strategy_str
      (Array.length pos.legs)
      pos.total_cost
      pos.total_delta
      pos.total_vega
      pos.total_gamma
  ) positions;
  close_out oc

let write_pnl_csv filename pnl_array =
  let oc = open_out filename in
  Printf.fprintf oc "timestamp,has_position,mark_to_market,realized_pnl,cumulative_pnl,sharpe_ratio,max_drawdown,sortino_ratio,return_skewness\n";
  let fmt_opt = function Some v -> Printf.sprintf "%.3f" v | None -> "" in
  Array.iter (fun pnl ->
    let has_position = match pnl.position with Some _ -> "1" | None -> "0" in
    Printf.fprintf oc "%.0f,%s,%.2f,%.2f,%.2f,%s,%s,%s,%s\n"
      pnl.timestamp
      has_position
      pnl.mark_to_market
      pnl.realized_pnl
      pnl.cumulative_pnl
      (fmt_opt pnl.sharpe_ratio)
      (fmt_opt pnl.max_drawdown)
      (fmt_opt pnl.sortino_ratio)
      (fmt_opt pnl.return_skewness)
  ) pnl_array;
  close_out oc

(* ========================================================================== *)
(* JSON Writing *)
(* ========================================================================== *)

let write_skew_stats_json filename (mean, std, p25, p75) =
  let json = `Assoc [
    ("mean", `Float mean);
    ("std", `Float std);
    ("percentile_25", `Float p25);
    ("percentile_75", `Float p75);
    ("z_score_threshold_2", `Float (mean +. 2.0 *. std));
    ("z_score_threshold_minus2", `Float (mean -. 2.0 *. std));
  ] in
  Yojson.Safe.to_file filename json

let write_vol_surface_json filename vol_surface =
  let json = match vol_surface with
    | SVI params ->
        let params_list = Array.to_list params |> List.map (fun p ->
          `Assoc [
            ("expiry", `Float p.expiry);
            ("a", `Float p.a);
            ("b", `Float p.b);
            ("rho", `Float p.rho);
            ("m", `Float p.m);
            ("sigma", `Float p.sigma);
          ]
        ) in
        `Assoc [
          ("model", `String "SVI");
          ("params", `List params_list);
        ]
  in
  Yojson.Safe.to_file filename json

(* ========================================================================== *)
(* Logging *)
(* ========================================================================== *)

let write_log filename message =
  let timestamp = Unix.time () |> Unix.localtime in
  let time_str = Printf.sprintf "%04d-%02d-%02d %02d:%02d:%02d"
    (timestamp.Unix.tm_year + 1900)
    (timestamp.Unix.tm_mon + 1)
    timestamp.Unix.tm_mday
    timestamp.Unix.tm_hour
    timestamp.Unix.tm_min
    timestamp.Unix.tm_sec
  in

  let oc = open_out_gen [Open_creat; Open_append; Open_text] 0o644 filename in
  Printf.fprintf oc "[%s] %s\n" time_str message;
  close_out oc

(* ========================================================================== *)
(* Directory Management *)
(* ========================================================================== *)

let ensure_output_dirs () =
  let dirs = [
    "pricing/skew_trading/data";
    "pricing/skew_trading/output";
    "pricing/skew_trading/log";
  ] in
  List.iter (fun dir ->
    if not (Sys.file_exists dir) then
      Unix.mkdir dir 0o755
  ) dirs

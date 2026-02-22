(* I/O operations for variance swaps *)

open Types

(* ========================================================================== *)
(* CSV Reading *)
(* ========================================================================== *)

let read_price_data filename =
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
      | date_str :: close_str :: _ ->
          begin try
            let date = float_of_string date_str in
            let close = float_of_string close_str in
            Some (date, close)
          with Failure _ -> None
          end
      | _ -> None
    ) (List.rev !lines) in

    Array.of_list parsed
  with Sys_error _ -> [||]

let read_ohlc_data filename =
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
      | date_str :: open_str :: high_str :: low_str :: close_str :: _ ->
          begin try
            let date = float_of_string date_str in
            let open_p = float_of_string open_str in
            let high = float_of_string high_str in
            let low = float_of_string low_str in
            let close = float_of_string close_str in
            Some (date, open_p, high, low, close)
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

(* ========================================================================== *)
(* CSV Writing *)
(* ========================================================================== *)

let write_variance_swap_csv filename (var_swap : variance_swap) =
  let oc = open_out filename in
  Printf.fprintf oc "ticker,notional,strike_var,strike_vol,expiry,vega_notional,entry_date,entry_spot\n";
  Printf.fprintf oc "%s,%.2f,%.6f,%.4f,%.4f,%.2f,%.0f,%.2f\n"
    var_swap.ticker
    var_swap.notional
    var_swap.strike_var
    (sqrt var_swap.strike_var)
    var_swap.expiry
    var_swap.vega_notional
    var_swap.entry_date
    var_swap.entry_spot;
  close_out oc

let write_vrp_observations_csv filename (observations : vrp_observation array) =
  let oc = open_out filename in
  Printf.fprintf oc "timestamp,ticker,horizon_days,implied_var,forecast_realized_var,vrp,vrp_percent\n";
  Array.iter (fun (obs : vrp_observation) ->
    Printf.fprintf oc "%.0f,%s,%d,%.6f,%.6f,%.6f,%.2f\n"
      obs.timestamp
      obs.ticker
      obs.horizon_days
      obs.implied_var
      obs.forecast_realized_var
      obs.vrp
      obs.vrp_percent
  ) observations;
  close_out oc

let write_signals_csv filename signals =
  let oc = open_out filename in
  Printf.fprintf oc "timestamp,ticker,signal_type,reason,confidence,position_size,expected_sharpe\n";
  Array.iter (fun signal ->
    let (signal_type_str, reason) = match signal.signal_type with
      | ShortVariance { reason; _ } -> ("SHORT", reason)
      | LongVariance { reason; _ } -> ("LONG", reason)
      | Neutral { reason } -> ("NEUTRAL", reason)
    in
    let sharpe_str = match signal.expected_sharpe with
      | Some s -> Printf.sprintf "%.2f" s
      | None -> ""
    in
    Printf.fprintf oc "%.0f,%s,%s,%s,%.2f,%.2f,%s\n"
      signal.timestamp
      signal.ticker
      signal_type_str
      (String.escaped reason)
      signal.confidence
      signal.position_size
      sharpe_str
  ) signals;
  close_out oc

let write_replication_csv filename portfolio =
  let oc = open_out filename in
  Printf.fprintf oc "option_type,strike,expiry,weight,price,delta,vega\n";
  Array.iter (fun leg ->
    let opt_type_str = match leg.option_type with Call -> "CALL" | Put -> "PUT" in
    Printf.fprintf oc "%s,%.2f,%.4f,%.4f,%.4f,%.4f,%.4f\n"
      opt_type_str
      leg.strike
      leg.expiry
      leg.weight
      leg.price
      leg.delta
      leg.vega
  ) portfolio.legs;
  close_out oc;

  (* Also write summary *)
  let summary_file = filename ^ ".summary" in
  let oc_summary = open_out summary_file in
  Printf.fprintf oc_summary "ticker,%s\n" portfolio.ticker;
  Printf.fprintf oc_summary "target_variance_notional,%.2f\n" portfolio.target_variance_notional;
  Printf.fprintf oc_summary "num_legs,%d\n" (Array.length portfolio.legs);
  Printf.fprintf oc_summary "total_cost,%.2f\n" portfolio.total_cost;
  Printf.fprintf oc_summary "total_vega,%.2f\n" portfolio.total_vega;
  Printf.fprintf oc_summary "total_delta,%.4f\n" portfolio.total_delta;
  close_out oc_summary

let write_pnl_csv filename pnl_array =
  let oc = open_out filename in
  Printf.fprintf oc "timestamp,has_position,realized_var,mtm_pnl,cumulative_pnl,sharpe_ratio\n";
  Array.iter (fun pnl ->
    let has_position = match pnl.position with Some _ -> "1" | None -> "0" in
    let sharpe_str = match pnl.sharpe_ratio with
      | Some s -> Printf.sprintf "%.3f" s
      | None -> ""
    in
    Printf.fprintf oc "%.0f,%s,%.6f,%.2f,%.2f,%s\n"
      pnl.timestamp
      has_position
      pnl.realized_var_to_date
      pnl.mark_to_market_pnl
      pnl.cumulative_pnl
      sharpe_str
  ) pnl_array;
  close_out oc

(* ========================================================================== *)
(* JSON Writing *)
(* ========================================================================== *)

let write_vrp_stats_json filename (mean_vrp, std_vrp, sharpe_ratio) =
  let json = `Assoc [
    ("mean_vrp", `Float mean_vrp);
    ("std_vrp", `Float std_vrp);
    ("sharpe_ratio", `Float sharpe_ratio);
    ("annualized_mean", `Float (mean_vrp *. 252.0));
    ("annualized_std", `Float (std_vrp *. sqrt 252.0));
  ] in
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

let rec mkdir_p dir =
  if not (Sys.file_exists dir) then begin
    let parent = Filename.dirname dir in
    if parent <> dir then mkdir_p parent;
    (try Unix.mkdir dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ())
  end

let ensure_output_dirs () =
  let dirs = [
    "pricing/variance_swaps/data";
    "pricing/variance_swaps/output";
    "pricing/variance_swaps/log";
  ] in
  List.iter mkdir_p dirs

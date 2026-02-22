(** I/O for liquidity analysis - JSON reading/writing *)

open Types

let read_file filename =
  let ic = open_in filename in
  let n = in_channel_length ic in
  let s = really_input_string ic n in
  close_in ic;
  s

let write_file filename content =
  let oc = open_out filename in
  output_string oc content;
  close_out oc

(** Parse JSON array to float array *)
let parse_float_array json =
  match json with
  | `List lst ->
    Array.of_list (List.map (function
      | `Float f -> f
      | `Int i -> float_of_int i
      | _ -> 0.0) lst)
  | _ -> [||]

(** Parse JSON array to string array *)
let parse_string_array json =
  match json with
  | `List lst ->
    Array.of_list (List.map (function
      | `String s -> s
      | _ -> "") lst)
  | _ -> [||]

(** Parse JSON number to float (handles both int and float) *)
let json_to_float json =
  let open Yojson.Basic.Util in
  match json with
  | `Float f -> f
  | `Int i -> float_of_int i
  | _ -> to_float json  (* Will raise if not a number *)

(** Parse single ticker data from JSON *)
let parse_ticker_data json : ticker_data option =
  try
    let open Yojson.Basic.Util in
    let ticker = json |> member "ticker" |> to_string in
    let shares = json_to_float (json |> member "shares_outstanding") in
    let mcap = json_to_float (json |> member "market_cap") in
    let dates = parse_string_array (json |> member "dates") in
    let open_p = parse_float_array (json |> member "open") in
    let high = parse_float_array (json |> member "high") in
    let low = parse_float_array (json |> member "low") in
    let close = parse_float_array (json |> member "close") in
    let volume = parse_float_array (json |> member "volume") in
    Some {
      ticker;
      shares_outstanding = shares;
      market_cap = mcap;
      ohlcv = { dates; open_prices = open_p; high; low; close; volume };
    }
  with e ->
    Printf.eprintf "Parse error: %s\n" (Printexc.to_string e);
    None

(** Load market data from JSON file *)
let load_market_data filename : ticker_data list =
  let content = read_file filename in
  let json = Yojson.Basic.from_string content in
  let open Yojson.Basic.Util in
  let tickers_json = json |> member "tickers" |> to_list in
  List.filter_map parse_ticker_data tickers_json

(** Convert analysis result to JSON *)
let result_to_json (r : analysis_result) : Yojson.Basic.t =
  `Assoc [
    ("ticker", `String r.ticker);
    ("price", `Float r.price);
    ("market_cap", `Float r.market_cap);
    ("avg_volume", `Float r.avg_volume);
    ("avg_dollar_volume", `Float r.avg_dollar_volume);
    ("liquidity_score", `Float r.liquidity.liquidity_score);
    ("liquidity_tier", `String r.liquidity.liquidity_tier);
    ("amihud_ratio", `Float r.liquidity.amihud_ratio);
    ("turnover_ratio", `Float r.liquidity.turnover_ratio);
    ("relative_volume", `Float r.liquidity.relative_volume);
    ("volume_volatility", `Float r.liquidity.volume_volatility);
    ("spread_proxy", `Float r.liquidity.spread_proxy);
    ("obv_strength", `Float r.signals.obv_strength);
    ("obv_signal", `String r.signals.obv_signal);
    ("volume_surge", `Bool r.signals.volume_surge);
    ("surge_magnitude", `Float r.signals.surge_magnitude);
    ("volume_trend", `String r.signals.volume_trend);
    ("volume_trend_slope", `Float r.signals.volume_trend_slope);
    ("vp_correlation", `Float r.signals.vp_correlation);
    ("vp_confirmation", `String r.signals.vp_confirmation);
    ("smart_money_flow", `Float r.signals.smart_money_flow);
    ("smart_money_signal", `String r.signals.smart_money_signal);
    ("signal_score", `Float r.signals.signal_score);
    ("composite_signal", `String r.signals.composite_signal);
  ]

(** Save results to JSON file *)
let save_results filename (results : analysis_result list) =
  let json = `Assoc [
    ("results", `List (List.map result_to_json results))
  ] in
  let content = Yojson.Basic.pretty_to_string json in
  write_file filename content

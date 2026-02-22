(** Portfolio I/O Module *)

open Types

(** Safe JSON value extraction *)
let to_float_safe j =
  match j with
  | `Float f -> f
  | `Int i -> float_of_int i
  | _ -> 0.0

let to_int_safe j =
  match j with
  | `Int i -> i
  | `Float f -> int_of_float f
  | _ -> 0

let to_string_safe j =
  match j with
  | `String s -> s
  | _ -> ""

let to_float_opt j =
  match j with
  | `Float f -> Some f
  | `Int i -> Some (float_of_int i)
  | `Null -> None
  | _ -> None

(** Parse position type from string *)
let parse_position_type (s : string) : position_type =
  match String.lowercase_ascii s with
  | "long" -> Long
  | "short" -> Short
  | "watching" -> Watching
  | _ -> Watching

(** Parse a thesis argument from JSON *)
let parse_thesis_arg (json : Yojson.Basic.t) : thesis_arg =
  let open Yojson.Basic.Util in
  {
    arg = json |> member "arg" |> to_string_safe;
    weight = json |> member "weight" |> to_int_safe;
  }

(** Parse price levels from JSON *)
let parse_price_levels (json : Yojson.Basic.t) : price_levels =
  let open Yojson.Basic.Util in
  {
    buy_target = json |> member "buy_target" |> to_float_opt;
    sell_target = json |> member "sell_target" |> to_float_opt;
    stop_loss = json |> member "stop_loss" |> to_float_opt;
  }

(** Parse position info from JSON *)
let parse_position_info (json : Yojson.Basic.t) : position_info =
  let open Yojson.Basic.Util in
  {
    pos_type = json |> member "type" |> to_string_safe |> parse_position_type;
    shares = json |> member "shares" |> to_float_safe;
    avg_cost = json |> member "avg_cost" |> to_float_safe;
  }

(** Parse a portfolio position from JSON *)
let parse_portfolio_position (json : Yojson.Basic.t) : portfolio_position =
  let open Yojson.Basic.Util in
  {
    ticker = json |> member "ticker" |> to_string_safe;
    name = json |> member "name" |> to_string_safe;
    position = json |> member "position" |> parse_position_info;
    levels = json |> member "levels" |> parse_price_levels;
    bull = json |> member "bull" |> to_list |> List.map parse_thesis_arg;
    bear = json |> member "bear" |> to_list |> List.map parse_thesis_arg;
    catalysts = json |> member "catalysts" |> to_list |> List.map to_string_safe;
    notes = json |> member "notes" |> to_string_safe;
  }

(** Load portfolio from JSON file *)
let load_portfolio (filename : string) : portfolio_position list =
  let json = Yojson.Basic.from_file filename in
  let open Yojson.Basic.Util in
  json |> member "positions" |> to_list |> List.map parse_portfolio_position

(** Parse market data from JSON *)
let parse_market_data (json : Yojson.Basic.t) : market_data =
  let open Yojson.Basic.Util in
  {
    current_price = json |> member "current_price" |> to_float_safe;
    prev_close = json |> member "prev_close" |> to_float_safe;
    change_1d_pct = json |> member "change_1d_pct" |> to_float_safe;
    change_5d_pct = json |> member "change_5d_pct" |> to_float_safe;
    high_52w = json |> member "high_52w" |> to_float_safe;
    low_52w = json |> member "low_52w" |> to_float_safe;
    fetch_time = json |> member "fetch_time" |> to_string_safe;
  }

(** Load market data from JSON file *)
let load_market_data (filename : string) : (string * market_data) list =
  if not (Sys.file_exists filename) then []
  else
    let json = Yojson.Basic.from_file filename in
    let open Yojson.Basic.Util in
    json |> member "tickers" |> to_list |> List.filter_map (fun t ->
      let error = t |> member "error" in
      match error with
      | `String _ -> None
      | _ ->
        let symbol = t |> member "symbol" |> to_string_safe in
        Some (symbol, parse_market_data t)
    )

(** Priority to string *)
let priority_to_string (p : priority) : string =
  match p with
  | Urgent -> "URGENT"
  | High -> "HIGH"
  | Normal -> "NORMAL"
  | Info -> "INFO"

(** Price alert to string *)
let alert_to_string (alert : price_alert) : string =
  match alert with
  | HitBuyTarget (current, target) ->
    Printf.sprintf "Hit buy target! $%.2f (target was $%.2f)" current target
  | HitSellTarget (current, target) ->
    Printf.sprintf "Hit sell target! $%.2f (target was $%.2f)" current target
  | HitStopLoss (current, stop) ->
    Printf.sprintf "STOP LOSS TRIGGERED! $%.2f (stop was $%.2f)" current stop
  | NearBuyTarget (current, target) ->
    Printf.sprintf "Approaching buy target: $%.2f (target $%.2f)" current target
  | NearStopLoss (current, stop) ->
    Printf.sprintf "WARNING: Near stop loss! $%.2f (stop $%.2f)" current stop
  | AboveCostBasis (current, cost, pct) ->
    Printf.sprintf "Up %.1f%% from cost basis ($%.2f -> $%.2f)" pct cost current
  | BelowCostBasis (current, cost, pct) ->
    Printf.sprintf "Down %.1f%% from cost basis ($%.2f -> $%.2f)" (abs_float pct) cost current

(** Position type to string *)
let position_type_to_string (pt : position_type) : string =
  match pt with
  | Long -> "Long"
  | Short -> "Short"
  | Watching -> "Watching"

(** Print position header *)
let print_position_header (pos : portfolio_position) (market : market_data option) (pnl_pct : float option) : unit =
  let price_str = match market with
    | Some m -> Printf.sprintf "$%.2f" m.current_price
    | None -> "(no data)"
  in
  let pnl_str = match pnl_pct with
    | Some p when p >= 0.0 -> Printf.sprintf " \027[32m+%.1f%%\027[0m" p
    | Some p -> Printf.sprintf " \027[31m%.1f%%\027[0m" p
    | None -> ""
  in
  let pos_str = match pos.position.pos_type with
    | Watching -> "Watching"
    | Long -> Printf.sprintf "Long %.0f @ $%.2f" pos.position.shares pos.position.avg_cost
    | Short -> Printf.sprintf "Short %.0f @ $%.2f" pos.position.shares pos.position.avg_cost
  in
  Printf.printf "\n\027[1m%s\027[0m - %s (now %s%s)\n" pos.ticker pos_str price_str pnl_str

(** Print thesis with weights *)
let print_thesis (bull : thesis_arg list) (bear : thesis_arg list) (score : thesis_score) : unit =
  let bull_sorted = List.sort (fun a b -> compare b.weight a.weight) bull in
  let bear_sorted = List.sort (fun a b -> compare b.weight a.weight) bear in

  Printf.printf "\n";
  Printf.printf "\027[32mBULL CASE (score: %d)\027[0m               \027[31mBEAR CASE (score: %d)\027[0m\n"
    score.bull_score score.bear_score;
  Printf.printf "%s\n" (String.make 70 '-');

  let max_len = max (List.length bull_sorted) (List.length bear_sorted) in
  for i = 0 to max_len - 1 do
    let bull_str =
      if i < List.length bull_sorted then
        let a = List.nth bull_sorted i in
        let truncated = if String.length a.arg > 30 then String.sub a.arg 0 27 ^ "..." else a.arg in
        Printf.sprintf "[%d] %s" a.weight truncated
      else ""
    in
    let bear_str =
      if i < List.length bear_sorted then
        let a = List.nth bear_sorted i in
        let truncated = if String.length a.arg > 30 then String.sub a.arg 0 27 ^ "..." else a.arg in
        Printf.sprintf "[%d] %s" a.weight truncated
      else ""
    in
    Printf.printf "%-35s %s\n" bull_str bear_str
  done;

  (* Net conviction *)
  let conviction_color =
    if score.net_score > 5 then "\027[32m"
    else if score.net_score < -5 then "\027[31m"
    else "\027[33m"
  in
  Printf.printf "\nNet Conviction: %s%+d (%s)\027[0m\n"
    conviction_color score.net_score score.conviction

(** Print price levels *)
let print_levels (levels : price_levels) (_current : float option) : unit =
  let level_str parts = String.concat " | " (List.filter (fun s -> s <> "") parts) in
  let buy_str = match levels.buy_target with Some p -> Printf.sprintf "Buy $%.2f" p | None -> "" in
  let stop_str = match levels.stop_loss with Some p -> Printf.sprintf "Stop $%.2f" p | None -> "" in
  let sell_str = match levels.sell_target with Some p -> Printf.sprintf "Target $%.2f" p | None -> "" in
  let s = level_str [buy_str; stop_str; sell_str] in
  if s <> "" then Printf.printf "Price Levels: %s\n" s

(** Print catalysts *)
let print_catalysts (catalysts : string list) : unit =
  if List.length catalysts > 0 then
    Printf.printf "Catalysts: %s\n" (String.concat ", " catalysts)

(** Print notes *)
let print_notes (notes : string) : unit =
  if notes <> "" then
    Printf.printf "Notes: %s\n" notes

(** Print alerts *)
let print_alerts (alerts : triggered_alert list) : unit =
  if List.length alerts > 0 then begin
    Printf.printf "\n\027[33mALERTS:\027[0m\n";
    List.iter (fun a ->
      let color = match a.priority with
        | Urgent -> "\027[31m"
        | High -> "\027[33m"
        | Normal -> "\027[0m"
        | Info -> "\027[36m"
      in
      Printf.printf "  %s[%s] %s\027[0m\n" color (priority_to_string a.priority) a.message
    ) alerts
  end

(** Print full position analysis *)
let print_position_analysis (analysis : position_analysis) : unit =
  print_position_header analysis.position analysis.market analysis.pnl_pct;
  print_thesis analysis.position.bull analysis.position.bear analysis.thesis;
  let current = match analysis.market with Some m -> Some m.current_price | None -> None in
  print_levels analysis.position.levels current;
  print_catalysts analysis.position.catalysts;
  print_notes analysis.position.notes;
  print_alerts analysis.alerts;
  Printf.printf "%s\n" (String.make 70 '=')

(** Print portfolio summary *)
let print_portfolio_summary (analysis : portfolio_analysis) : unit =
  Printf.printf "\n";
  Printf.printf "\027[1m%s\027[0m\n" (String.make 70 '=');
  Printf.printf "\027[1m                    PORTFOLIO TRACKER - %s\027[0m\n" analysis.run_time;
  Printf.printf "\027[1m%s\027[0m\n" (String.make 70 '=');

  List.iter print_position_analysis analysis.positions;

  (* Summary stats *)
  if List.length analysis.all_alerts > 0 then begin
    Printf.printf "\n\027[33m>>> %d TOTAL ALERTS <<<\027[0m\n" (List.length analysis.all_alerts);
    List.iter (fun a ->
      Printf.printf "  [%s] %s: %s\n" (priority_to_string a.priority) a.ticker a.message
    ) analysis.all_alerts
  end

(** Save portfolio analysis to JSON *)
let save_analysis (analysis : portfolio_analysis) (filename : string) : unit =
  let alert_to_json (a : triggered_alert) : Yojson.Basic.t =
    `Assoc [
      ("ticker", `String a.ticker);
      ("priority", `String (priority_to_string a.priority));
      ("message", `String a.message);
    ]
  in
  let float_opt_to_json = function
    | Some v -> `Float v
    | None -> `Null
  in
  let position_to_json (p : position_analysis) : Yojson.Basic.t =
    `Assoc [
      ("ticker", `String p.position.ticker);
      ("name", `String p.position.name);
      ("position_type", `String (position_type_to_string p.position.position.pos_type));
      ("shares", `Float p.position.position.shares);
      ("avg_cost", `Float p.position.position.avg_cost);
      ("current_price", match p.market with Some m -> `Float m.current_price | None -> `Null);
      ("pnl_pct", match p.pnl_pct with Some v -> `Float v | None -> `Null);
      ("pnl_abs", match p.pnl_abs with Some v -> `Float v | None -> `Null);
      ("bull_score", `Int p.thesis.bull_score);
      ("bear_score", `Int p.thesis.bear_score);
      ("net_conviction", `Int p.thesis.net_score);
      ("conviction_label", `String p.thesis.conviction);
      ("levels", `Assoc [
        ("buy_target", float_opt_to_json p.position.levels.buy_target);
        ("sell_target", float_opt_to_json p.position.levels.sell_target);
        ("stop_loss", float_opt_to_json p.position.levels.stop_loss);
      ]);
      ("market", match p.market with
        | Some m -> `Assoc [
            ("current_price", `Float m.current_price);
            ("prev_close", `Float m.prev_close);
            ("change_1d_pct", `Float m.change_1d_pct);
            ("change_5d_pct", `Float m.change_5d_pct);
            ("high_52w", `Float m.high_52w);
            ("low_52w", `Float m.low_52w);
          ]
        | None -> `Null);
      ("alerts", `List (List.map alert_to_json p.alerts));
    ]
  in
  let json = `Assoc [
    ("run_time", `String analysis.run_time);
    ("position_count", `Int (List.length analysis.positions));
    ("total_alerts", `Int (List.length analysis.all_alerts));
    ("positions", `List (List.map position_to_json analysis.positions));
    ("alerts", `List (List.map alert_to_json analysis.all_alerts));
  ]
  in
  let out_channel = open_out filename in
  Yojson.Basic.pretty_to_channel out_channel json;
  close_out out_channel

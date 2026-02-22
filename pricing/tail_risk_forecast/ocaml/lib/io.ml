(** JSON I/O and console output for tail risk forecasting *)

open Types

let pct x = Printf.sprintf "%.2f%%" (x *. 100.0)
let bps x = Printf.sprintf "%.1f bps" (x *. 10000.0)

(* JSON helpers *)
let get_string json key =
  match json with
  | `Assoc lst -> (
      match List.assoc_opt key lst with
      | Some (`String s) -> Some s
      | _ -> None)
  | _ -> None

let get_float json key =
  match json with
  | `Assoc lst -> (
      match List.assoc_opt key lst with
      | Some (`Float f) -> Some f
      | Some (`Int i) -> Some (float_of_int i)
      | _ -> None)
  | _ -> None

let get_list json key =
  match json with
  | `Assoc lst -> (
      match List.assoc_opt key lst with
      | Some (`List l) -> Some l
      | _ -> None)
  | _ -> None

let read_intraday_data (path : string) : intraday_data option =
  try
    let content = In_channel.with_open_text path In_channel.input_all in
    let json = Yojson.Basic.from_string content in

    let ticker = get_string json "ticker" |> Option.value ~default:"" in
    let start_date = get_string json "start_date" |> Option.value ~default:"" in
    let end_date = get_string json "end_date" |> Option.value ~default:"" in
    let interval = get_string json "interval" |> Option.value ~default:"5m" in

    (* Parse daily_data: array of { date, close, returns: [...] } *)
    let daily_data = get_list json "daily_data" |> Option.value ~default:[] in

    let parse_day day_json =
      let date = get_string day_json "date" |> Option.value ~default:"" in
      let close = get_float day_json "close" |> Option.value ~default:0.0 in
      let returns_json = get_list day_json "returns" |> Option.value ~default:[] in
      let returns = Array.of_list (List.filter_map (fun r ->
        match r with
        | `Float f -> Some { timestamp = ""; ret = f }
        | `Int i -> Some { timestamp = ""; ret = float_of_int i }
        | _ -> None
      ) returns_json) in
      (date, close, returns)
    in

    let parsed_days = List.map parse_day daily_data in
    let bars = Array.of_list (List.map (fun (_, _, r) -> r) parsed_days) in
    let daily_closes = Array.of_list (List.map (fun (d, c, _) -> (d, c)) parsed_days) in

    Some { ticker; start_date; end_date; interval; bars; daily_closes }
  with
  | _ -> None

let write_result_json (path : string) (result : analysis_result) : unit =
  let forecast = result.forecast in
  let har = result.har_model in

  let json = `Assoc [
    ("ticker", `String result.ticker);
    ("analysis_date", `String result.analysis_date);
    ("har_model", `Assoc [
      ("constant", `Float har.c);
      ("beta_daily", `Float har.beta_d);
      ("beta_weekly", `Float har.beta_w);
      ("beta_monthly", `Float har.beta_m);
      ("r_squared", `Float har.r_squared);
    ]);
    ("forecast", `Assoc [
      ("date", `String forecast.date);
      ("rv_forecast", `Float forecast.rv_forecast);
      ("vol_forecast", `Float forecast.vol_forecast);
      ("var_95", `Float forecast.var_95);
      ("var_99", `Float forecast.var_99);
      ("es_95", `Float forecast.es_95);
      ("es_99", `Float forecast.es_99);
      ("jump_adjusted", `Bool forecast.jump_adjusted);
    ]);
    ("jump_intensity", `Float (Jump_detection.jump_intensity result.recent_jumps));
    ("total_observations", `Int (Array.length result.rv_series));
  ] in

  let content = Yojson.Basic.pretty_to_string json in
  Out_channel.with_open_text path (fun oc -> Out_channel.output_string oc content)

let print_har_summary (har : har_coefficients) : unit =
  Printf.printf "\nHAR-RV Model Coefficients:\n";
  Printf.printf "────────────────────────────────────────\n";
  Printf.printf "  Constant (c):     %12.6f\n" har.c;
  Printf.printf "  Daily (β_d):      %12.4f\n" har.beta_d;
  Printf.printf "  Weekly (β_w):     %12.4f\n" har.beta_w;
  Printf.printf "  Monthly (β_m):    %12.4f\n" har.beta_m;
  Printf.printf "  R²:               %12.2f%%\n" (har.r_squared *. 100.0)

let print_jump_summary (jumps : jump_indicator array) : unit =
  let n = Array.length jumps in
  let jump_count = Array.fold_left (fun acc j -> if j.is_jump then acc + 1 else acc) 0 jumps in
  let intensity = float_of_int jump_count /. float_of_int (max 1 n) in

  Printf.printf "\nJump Analysis:\n";
  Printf.printf "────────────────────────────────────────\n";
  Printf.printf "  Total days:       %12d\n" n;
  Printf.printf "  Jump days:        %12d\n" jump_count;
  Printf.printf "  Jump intensity:   %12.1f%%\n" (intensity *. 100.0);

  (* Recent jumps *)
  let recent = Jump_detection.count_recent_jumps jumps 20 in
  Printf.printf "  Jumps (last 20d): %12d\n" recent

let print_forecast (result : analysis_result) : unit =
  let f = result.forecast in

  Printf.printf "\n";
  Printf.printf "═══════════════════════════════════════════════════════════════\n";
  Printf.printf "                TAIL RISK FORECAST - %s\n" result.ticker;
  Printf.printf "═══════════════════════════════════════════════════════════════\n";
  Printf.printf "Analysis Date: %s\n" result.analysis_date;

  print_har_summary result.har_model;
  print_jump_summary result.recent_jumps;

  Printf.printf "\nVolatility Forecast (Next Day):\n";
  Printf.printf "────────────────────────────────────────\n";
  Printf.printf "  RV forecast:      %s\n" (bps f.rv_forecast);
  Printf.printf "  Vol forecast:     %s\n" (pct f.vol_forecast);
  Printf.printf "  Annualized vol:   %s\n" (pct (f.vol_forecast *. sqrt 252.0));
  if f.jump_adjusted then
    Printf.printf "  ⚠ Jump-adjusted:  Recent variance jumps detected\n";

  Printf.printf "\nValue-at-Risk (loss threshold):\n";
  Printf.printf "────────────────────────────────────────\n";
  Printf.printf "  VaR 95%%:          %s   (5%% chance of exceeding)\n" (pct f.var_95);
  Printf.printf "  VaR 99%%:          %s   (1%% chance of exceeding)\n" (pct f.var_99);

  Printf.printf "\nExpected Shortfall (avg loss if exceeded):\n";
  Printf.printf "────────────────────────────────────────\n";
  Printf.printf "  ES 95%%:           %s   (avg loss in worst 5%%)\n" (pct f.es_95);
  Printf.printf "  ES 99%%:           %s   (avg loss in worst 1%%)\n" (pct f.es_99);

  Printf.printf "\n═══════════════════════════════════════════════════════════════\n"

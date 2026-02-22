(** I/O operations for perpetual futures pricing. *)

open Types

(* JSON parsing helpers *)
let get_string json key =
  match json with
  | `Assoc lst -> (
      match List.assoc_opt key lst with
      | Some (`String s) -> s
      | _ -> "")
  | _ -> ""

let get_float json key =
  match json with
  | `Assoc lst -> (
      match List.assoc_opt key lst with
      | Some (`Float f) -> f
      | Some (`Int i) -> float_of_int i
      | _ -> 0.0)
  | _ -> 0.0

let get_float_opt json key =
  match json with
  | `Assoc lst -> (
      match List.assoc_opt key lst with
      | Some (`Float f) -> Some f
      | Some (`Int i) -> Some (float_of_int i)
      | _ -> None)
  | _ -> None

let get_int json key =
  match json with
  | `Assoc lst -> (
      match List.assoc_opt key lst with
      | Some (`Int i) -> i
      | Some (`Float f) -> int_of_float f
      | _ -> 0)
  | _ -> 0

(** Read market data from JSON file *)
let read_market_data (filepath : string) : market_data =
  let ic = open_in filepath in
  let content = really_input_string ic (in_channel_length ic) in
  close_in ic;

  let json = Yojson.Basic.from_string content in
  {
    symbol = get_string json "symbol";
    spot = get_float json "spot";
    mark_price = get_float json "mark_price";
    index_price = get_float json "index_price";
    funding_rate = get_float json "funding_rate";
    funding_interval_hours = get_int json "funding_interval_hours";
    open_interest = get_float_opt json "open_interest";
    volume_24h = get_float_opt json "volume_24h";
    timestamp = get_string json "timestamp";
  }

(** Write pricing result to JSON *)
let write_pricing_result (filepath : string) (result : pricing_result) : unit =
  let json = `Assoc [
    ("spot_price", `Float result.spot_price);
    ("futures_price", `Float result.futures_price);
    ("basis", `Float result.basis);
    ("basis_pct", `Float result.basis_pct);
    ("fair_funding_rate", `Float result.fair_funding_rate);
    ("perfect_iota", `Float result.perfect_iota);
  ] in

  let oc = open_out filepath in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc

(** Write analysis result to JSON *)
let write_analysis_result (filepath : string) (result : analysis_result) : unit =
  let market_json = `Assoc [
    ("symbol", `String result.market.symbol);
    ("spot", `Float result.market.spot);
    ("mark_price", `Float result.market.mark_price);
    ("index_price", `Float result.market.index_price);
    ("funding_rate", `Float result.market.funding_rate);
    ("funding_interval_hours", `Int result.market.funding_interval_hours);
    ("timestamp", `String result.market.timestamp);
  ] in

  let theoretical_json = `Assoc [
    ("spot_price", `Float result.theoretical.spot_price);
    ("futures_price", `Float result.theoretical.futures_price);
    ("basis", `Float result.theoretical.basis);
    ("basis_pct", `Float result.theoretical.basis_pct);
    ("fair_funding_rate", `Float result.theoretical.fair_funding_rate);
    ("perfect_iota", `Float result.theoretical.perfect_iota);
  ] in

  let json = `Assoc [
    ("market", market_json);
    ("theoretical", theoretical_json);
    ("mispricing", `Float result.mispricing);
    ("mispricing_pct", `Float result.mispricing_pct);
    ("arbitrage_signal", `String result.arbitrage_signal);
  ] in

  let oc = open_out filepath in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc

(** Write everlasting option grid to CSV *)
let write_option_grid (filepath : string) (grid : (float * float * float) list) : unit =
  let oc = open_out filepath in
  Printf.fprintf oc "spot,call,put\n";
  List.iter (fun (spot, call, put) ->
    Printf.fprintf oc "%.6f,%.6f,%.6f\n" spot call put
  ) grid;
  close_out oc

(* ANSI color codes *)
let reset = "\027[0m"
let bold = "\027[1m"
let red = "\027[31m"
let green = "\027[32m"
let _yellow = "\027[33m"
let blue = "\027[34m"
let cyan = "\027[36m"

(** Print pricing dashboard *)
let print_pricing_dashboard (contract_type : contract_type) (result : pricing_result) : unit =
  Printf.printf "\n%s%s══════════════════════════════════════════════════════════════%s\n" bold blue reset;
  Printf.printf "%s%s              PERPETUAL FUTURES PRICING%s\n" bold blue reset;
  Printf.printf "%s%s══════════════════════════════════════════════════════════════%s\n\n" bold blue reset;

  Printf.printf "%sContract Type:%s %s\n\n" bold reset (contract_type_to_string contract_type);

  Printf.printf "%sPRICES%s\n" bold reset;
  Printf.printf "──────────────────────────────────────────────────────────────\n";
  Printf.printf "Spot Price:          %s$%.2f%s\n" cyan result.spot_price reset;
  Printf.printf "Futures Price:       %s$%.2f%s\n" cyan result.futures_price reset;

  let basis_color = if result.basis > 0.0 then green else if result.basis < 0.0 then red else reset in
  Printf.printf "Basis (f - x):       %s$%.4f%s\n" basis_color result.basis reset;
  Printf.printf "Basis (%%):           %s%.4f%%%s\n" basis_color result.basis_pct reset;

  Printf.printf "\n%sFUNDING%s\n" bold reset;
  Printf.printf "──────────────────────────────────────────────────────────────\n";
  Printf.printf "Fair Funding Rate:   %.6f (annual)\n" result.fair_funding_rate;
  Printf.printf "Perfect iota:        %.6f\n" result.perfect_iota;
  Printf.printf "\n"

(** Print everlasting option result *)
let print_option_result (opt_type : option_type) (result : option_result) : unit =
  Printf.printf "\n%s%s══════════════════════════════════════════════════════════════%s\n" bold blue reset;
  Printf.printf "%s%s              EVERLASTING %s OPTION%s\n" bold blue (String.uppercase_ascii (option_type_to_string opt_type)) reset;
  Printf.printf "%s%s══════════════════════════════════════════════════════════════%s\n\n" bold blue reset;

  Printf.printf "%sPRICING%s\n" bold reset;
  Printf.printf "──────────────────────────────────────────────────────────────\n";
  Printf.printf "Underlying:          %s$%.2f%s\n" cyan result.underlying reset;
  Printf.printf "Option Price:        %s$%.4f%s\n" green result.option_price reset;
  Printf.printf "Intrinsic Value:     $%.4f\n" result.intrinsic;
  Printf.printf "Time Value:          $%.4f\n" result.time_value;

  Printf.printf "\n%sGREEKS%s\n" bold reset;
  Printf.printf "──────────────────────────────────────────────────────────────\n";
  Printf.printf "Delta:               %.4f\n" result.delta;
  Printf.printf "\n"

(** Print analysis result with market comparison *)
let print_analysis (result : analysis_result) : unit =
  Printf.printf "\n%s%s══════════════════════════════════════════════════════════════%s\n" bold blue reset;
  Printf.printf "%s%s           PERPETUAL FUTURES ANALYSIS: %s%s\n" bold blue result.market.symbol reset;
  Printf.printf "%s%s══════════════════════════════════════════════════════════════%s\n\n" bold blue reset;

  Printf.printf "%sMARKET DATA%s\n" bold reset;
  Printf.printf "──────────────────────────────────────────────────────────────\n";
  Printf.printf "Spot (Index):        %s$%.2f%s\n" cyan result.market.index_price reset;
  Printf.printf "Mark Price:          %s$%.2f%s\n" cyan result.market.mark_price reset;
  Printf.printf "Funding Rate (%dh):   %.4f%%\n" result.market.funding_interval_hours (result.market.funding_rate *. 100.0);

  Printf.printf "\n%sTHEORETICAL%s\n" bold reset;
  Printf.printf "──────────────────────────────────────────────────────────────\n";
  Printf.printf "Model Futures Price: $%.2f\n" result.theoretical.futures_price;
  Printf.printf "Model Basis:         $%.4f (%.4f%%)\n"
    result.theoretical.basis result.theoretical.basis_pct;

  Printf.printf "\n%sARBITRAGE ANALYSIS%s\n" bold reset;
  Printf.printf "──────────────────────────────────────────────────────────────\n";

  let signal_color = match result.arbitrage_signal with
    | "LONG" -> green
    | "SHORT" -> red
    | _ -> reset
  in
  Printf.printf "Mispricing:          $%.4f (%.4f%%)\n" result.mispricing result.mispricing_pct;
  Printf.printf "Signal:              %s%s%s\n" signal_color result.arbitrage_signal reset;

  Printf.printf "\n%sTimestamp: %s%s\n\n" cyan result.market.timestamp reset

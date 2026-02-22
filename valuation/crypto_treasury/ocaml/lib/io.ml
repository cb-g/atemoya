(** JSON parsing and output formatting for crypto treasury *)

open Types

(* Handle both int and float JSON values *)
let to_number json =
  match json with
  | `Float f -> f
  | `Int i -> float_of_int i
  | _ -> 0.0

let to_int_value json =
  match json with
  | `Int i -> i
  | `Float f -> int_of_float f
  | _ -> 0

(** Parse holdings.json file, returning a (ticker -> holdings_entry) association list *)
let parse_holdings filename : (string * holdings_entry) list =
  let json = Yojson.Basic.from_file filename in
  let holdings_obj = Yojson.Basic.Util.(json |> member "holdings") in
  match holdings_obj with
  | `Assoc entries ->
    List.map (fun (ticker, entry) ->
      let m = Yojson.Basic.Util.member in
      let h : holdings_entry = {
        h_name = Yojson.Basic.Util.(entry |> m "name" |> to_string);
        btc_holdings = to_int_value (entry |> m "btc_holdings");
        btc_avg_cost = to_number (entry |> m "btc_avg_cost");
        eth_holdings = to_int_value (entry |> m "eth_holdings");
        eth_avg_cost = to_number (entry |> m "eth_avg_cost");
      } in
      (ticker, h)
    ) entries
  | _ -> failwith "Expected 'holdings' to be a JSON object"

(** Serialize mnav_metrics to JSON *)
let mnav_metrics_to_json (m : mnav_metrics) : Yojson.Basic.t =
  `Assoc [
    ("ticker", `String m.ticker);
    ("name", `String m.name);
    ("price", `Float m.price);
    ("market_cap", `Float m.market_cap);
    ("shares_outstanding", `Float m.shares_outstanding);
    ("holding_type", `String (string_of_holding_type m.holding_type));

    ("btc_holdings", `Int m.btc_holdings);
    ("btc_price", `Float m.btc_price);
    ("btc_value", `Float m.btc_value);
    ("btc_per_share", `Float m.btc_per_share);
    ("implied_btc_price", `Float m.implied_btc_price);
    ("btc_avg_cost", `Float m.btc_avg_cost);
    ("btc_unrealized_gain", `Float m.btc_unrealized_gain);
    ("btc_unrealized_gain_pct", `Float m.btc_unrealized_gain_pct);

    ("eth_holdings", `Int m.eth_holdings);
    ("eth_price", `Float m.eth_price);
    ("eth_value", `Float m.eth_value);
    ("eth_per_share", `Float m.eth_per_share);
    ("implied_eth_price", `Float m.implied_eth_price);
    ("eth_avg_cost", `Float m.eth_avg_cost);
    ("eth_unrealized_gain", `Float m.eth_unrealized_gain);
    ("eth_unrealized_gain_pct", `Float m.eth_unrealized_gain_pct);

    ("nav", `Float m.nav);
    ("nav_per_share", `Float m.nav_per_share);
    ("mnav", `Float m.mnav);
    ("premium_pct", `Float m.premium_pct);
    ("total_unrealized_gain", `Float m.total_unrealized_gain);
    ("debt_to_nav", `Float m.debt_to_nav);
    ("signal", `String (string_of_signal m.signal));
    ("signal_color", `String (signal_color m.signal));
  ]

(** Save results to JSON file *)
let save_results ~btc_price ~eth_price ~timestamp (results : mnav_metrics list) filename =
  let json = `Assoc [
    ("btc_price", `Float btc_price);
    ("eth_price", `Float eth_price);
    ("timestamp", `String timestamp);
    ("results", `List (List.map mnav_metrics_to_json results));
  ] in
  let oc = open_out filename in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc

(** Print a single metrics result to stdout *)
let print_metrics (m : mnav_metrics) =
  Printf.printf "\n========================================\n";
  Printf.printf "Crypto Treasury Valuation: %s\n" m.ticker;
  Printf.printf "========================================\n\n";
  Printf.printf "Company: %s\n" m.name;
  Printf.printf "Industry: Crypto Treasury (%s)\n\n" (string_of_holding_type m.holding_type);
  Printf.printf "Market Data:\n";
  Printf.printf "  Stock Price: $%.2f\n" m.price;
  Printf.printf "  Market Cap: %s\n" (Mnav.format_currency m.market_cap);
  Printf.printf "  Shares Outstanding: %.0f\n" m.shares_outstanding;

  if m.btc_holdings > 0 then begin
    Printf.printf "\nBitcoin Holdings:\n";
    Printf.printf "  BTC Holdings: %d BTC\n" m.btc_holdings;
    Printf.printf "  BTC Price: $%.2f\n" m.btc_price;
    Printf.printf "  BTC Value: %s\n" (Mnav.format_currency m.btc_value);
    Printf.printf "  BTC/Share: %.6f BTC\n" m.btc_per_share;
    if m.btc_avg_cost > 0.0 then begin
      Printf.printf "  Avg Cost: $%.2f/BTC\n" m.btc_avg_cost;
      Printf.printf "  Unrealized Gain: %s (%+.1f%%)\n"
        (Mnav.format_currency m.btc_unrealized_gain) m.btc_unrealized_gain_pct
    end
  end;

  if m.eth_holdings > 0 then begin
    Printf.printf "\nEthereum Holdings:\n";
    Printf.printf "  ETH Holdings: %d ETH\n" m.eth_holdings;
    Printf.printf "  ETH Price: $%.2f\n" m.eth_price;
    Printf.printf "  ETH Value: %s\n" (Mnav.format_currency m.eth_value);
    Printf.printf "  ETH/Share: %.6f ETH\n" m.eth_per_share;
    if m.eth_avg_cost > 0.0 then begin
      Printf.printf "  Avg Cost: $%.2f/ETH\n" m.eth_avg_cost;
      Printf.printf "  Unrealized Gain: %s (%+.1f%%)\n"
        (Mnav.format_currency m.eth_unrealized_gain) m.eth_unrealized_gain_pct
    end
  end;

  Printf.printf "\nNAV Metrics:\n";
  Printf.printf "  Total NAV: %s\n" (Mnav.format_currency m.nav);
  Printf.printf "  NAV per Share: $%.2f\n" m.nav_per_share;
  Printf.printf "  mNAV: %.3fx\n" m.mnav;
  Printf.printf "  Premium/Discount: %+.1f%%\n" m.premium_pct;

  if m.btc_holdings > 0 then
    Printf.printf "  Implied BTC Price: $%.2f\n" m.implied_btc_price;
  if m.eth_holdings > 0 then
    Printf.printf "  Implied ETH Price: $%.2f\n" m.implied_eth_price;

  if m.debt_to_nav > 0.0 then begin
    Printf.printf "\nLeverage:\n";
    Printf.printf "  Debt/NAV: %.2fx\n" m.debt_to_nav
  end;

  Printf.printf "\nInvestment Signal: %s\n" (string_of_signal m.signal);

  if m.mnav < 1.0 then begin
    Printf.printf "  Trading at %.1f%% discount to crypto holdings.\n"
      (abs_float m.premium_pct);
    match m.holding_type with
    | BTC ->
      Printf.printf "  Buying stock = buying BTC at $%.0f (vs $%.0f spot).\n"
        m.implied_btc_price m.btc_price
    | ETH ->
      Printf.printf "  Buying stock = buying ETH at $%.0f (vs $%.0f spot).\n"
        m.implied_eth_price m.eth_price
    | Mixed ->
      Printf.printf "  Buying stock = buying crypto at %.2fx NAV.\n" m.mnav
  end else begin
    Printf.printf "  Trading at %.1f%% premium to crypto holdings.\n" m.premium_pct;
    Printf.printf "  Market pricing in future accumulation or management premium.\n"
  end

(** Print summary table *)
let print_summary_table (results : mnav_metrics list) =
  Printf.printf "\n%s\n" (String.make 120 '=');
  Printf.printf "Crypto Treasury Valuation Summary\n";
  Printf.printf "%s\n" (String.make 120 '=');
  Printf.printf "%-8s %-6s %10s %10s %10s %12s %8s %10s %-12s\n"
    "Ticker" "Type" "Price" "BTC" "ETH" "NAV" "mNAV" "Premium" "Signal";
  Printf.printf "%s\n" (String.make 120 '-');
  List.iter (fun (m : mnav_metrics) ->
    let btc_str = if m.btc_holdings > 0 then string_of_int m.btc_holdings else "-" in
    let eth_str = if m.eth_holdings > 0 then string_of_int m.eth_holdings else "-" in
    Printf.printf "%-8s %-6s $%8.2f %10s %10s %12s %7.3fx %+9.1f%% %-12s\n"
      m.ticker
      (string_of_holding_type m.holding_type)
      m.price
      btc_str
      eth_str
      (Mnav.format_currency m.nav)
      m.mnav
      m.premium_pct
      (string_of_signal m.signal)
  ) results;
  Printf.printf "%s\n" (String.make 120 '=')

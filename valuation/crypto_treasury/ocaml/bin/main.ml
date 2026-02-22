(** Crypto Treasury CLI

    mNAV model for companies holding BTC/ETH as treasury assets.
    Reads holdings from JSON, fetches market data via Python,
    computes NAV, mNAV, and investment signals. *)

open Crypto_treasury

let usage = {|
Crypto Treasury Valuation - mNAV Model

Usage:
  crypto_treasury <results_json>           Display pre-computed results
  crypto_treasury --data-dir <dir>         Load holdings and results

Options:
  --data-dir DIR   Directory containing holdings.json
  --help           Show this help message
|}

let display_results filename =
  try
    let json = Yojson.Basic.from_file filename in
    let m = Yojson.Basic.Util.member in
    let btc_price = Io.to_number (json |> m "btc_price") in
    let eth_price = Io.to_number (json |> m "eth_price") in
    Printf.printf "BTC Price: $%.2f\n" btc_price;
    Printf.printf "ETH Price: $%.2f\n\n" eth_price;

    let results_json = Yojson.Basic.Util.(json |> m "results" |> to_list) in
    let results = List.filter_map (fun rj ->
      try
        let s = Yojson.Basic.Util.to_string in
        let ticker = rj |> m "ticker" |> s in
        let name = rj |> m "name" |> s in
        let price = Io.to_number (rj |> m "price") in
        let market_cap = Io.to_number (rj |> m "market_cap") in
        let shares = Io.to_number (rj |> m "shares_outstanding") in
        let btc_h = Io.to_int_value (rj |> m "btc_holdings") in
        let eth_h = Io.to_int_value (rj |> m "eth_holdings") in

        let company : Types.company_data = {
          ticker; name; price; market_cap;
          shares_outstanding = shares;
          industry = "Crypto Treasury";
          total_debt = Io.to_number (rj |> m "total_debt");
          total_cash = 0.0;
        } in

        let metrics = Mnav.calculate_mnav_metrics
          ~company ~btc_holdings:btc_h ~btc_price
          ~eth_holdings:eth_h ~eth_price
          ~btc_avg_cost:(Io.to_number (rj |> m "btc_avg_cost"))
          ~eth_avg_cost:(Io.to_number (rj |> m "eth_avg_cost"))
        in
        Some metrics
      with _ -> None
    ) results_json in

    let sorted = Mnav.sort_by_mnav results in
    List.iter Io.print_metrics sorted;
    Io.print_summary_table sorted

  with
  | Sys_error msg ->
    Printf.eprintf "Error reading file: %s\n" msg;
    exit 1
  | Yojson.Json_error msg ->
    Printf.eprintf "Error parsing JSON: %s\n" msg;
    exit 1

let () =
  let args = Array.to_list Sys.argv |> List.tl in
  match args with
  | [] | ["--help"] | ["-h"] ->
    print_string usage
  | [filename] ->
    display_results filename
  | _ ->
    Printf.eprintf "Error: Invalid arguments. Use --help for usage.\n";
    exit 1

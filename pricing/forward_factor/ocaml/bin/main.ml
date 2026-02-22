(** Forward Factor Scanner - Main Entry Point *)

open Forward_factor

(** Example: Create sample expiration data for testing *)
let create_sample_expirations ticker =
  (* Simulating AAPL with backwardation: front IV > back IV *)
  let front_30 = {
    Types.ticker;
    expiration = "2026-02-06";
    dte = 30;
    atm_iv = 0.35;  (* 35% IV *)
    atm_strike = 180.0;
    atm_call_price = 4.50;
    atm_put_price = 4.30;
    delta_35_call_strike = 185.0;
    delta_35_call_price = 2.50;
    delta_35_put_strike = 175.0;
    delta_35_put_price = 2.30;
  } in

  let back_60 = {
    Types.ticker;
    expiration = "2026-03-08";
    dte = 60;
    atm_iv = 0.28;  (* 28% IV - lower than front, creates backwardation *)
    atm_strike = 180.0;
    atm_call_price = 6.80;
    atm_put_price = 6.50;
    delta_35_call_strike = 185.0;
    delta_35_call_price = 4.20;
    delta_35_put_strike = 175.0;
    delta_35_put_price = 4.00;
  } in

  let back_90 = {
    Types.ticker;
    expiration = "2026-04-07";
    dte = 90;
    atm_iv = 0.26;  (* 26% IV - even lower *)
    atm_strike = 180.0;
    atm_call_price = 8.50;
    atm_put_price = 8.20;
    delta_35_call_strike = 185.0;
    delta_35_call_price = 5.80;
    delta_35_put_strike = 175.0;
    delta_35_put_price = 5.50;
  } in

  [front_30; back_60; back_90]

let () =
  Printf.printf "\n";
  Printf.printf "╔════════════════════════════════════════════════════════════════╗\n";
  Printf.printf "║           Forward Factor Strategy Scanner v1.0                 ║\n";
  Printf.printf "║  Term Structure Calendar Spread Opportunity Finder             ║\n";
  Printf.printf "╚════════════════════════════════════════════════════════════════╝\n";
  Printf.printf "\n";

  (* Strategy overview *)
  Printf.printf "Strategy Overview:\n";
  Printf.printf "  Entry Signal: Forward Factor (FF) ≥ 0.20 (20%% backwardation)\n";
  Printf.printf "  Position: ATM call calendar spreads\n";
  Printf.printf "  Backtest: 27%% CAGR, 2.42 Sharpe (quarter Kelly)\n";
  Printf.printf "  Best DTE Pair: 60-90 days\n";
  Printf.printf "\n";

  (* Create sample data for demonstration *)
  let aapl_exps = create_sample_expirations "AAPL" in
  let msft_exps = create_sample_expirations "MSFT" in
  let universe = [aapl_exps; msft_exps] in

  (* Scan universe *)
  Printf.printf "Scanning universe for FF ≥ 0.20...\n";
  let recommendations = Scanner.scan_universe
    ~universe
    ~dte_pairs:Scanner.default_dte_pairs
    ~threshold:Types.default_ff_threshold
  in

  (* Print results *)
  Scanner.print_scanner_summary recommendations;

  (* Print detailed recommendations *)
  if List.length recommendations > 0 then begin
    Printf.printf "Detailed Analysis:\n";
    Printf.printf "%s\n" (String.make 64 '=');
    List.iter Scanner.print_recommendation recommendations
  end;

  Printf.printf "\n";
  Printf.printf "Note: This is a demonstration with sample data.\n";
  Printf.printf "For live scanning, use the Python data fetcher to get real options chains.\n";
  Printf.printf "\n"

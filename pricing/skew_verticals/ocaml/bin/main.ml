(** Skew-Based Vertical Spreads Scanner *)

open Skew_verticals_lib

let () =
  (* Parse command line *)
  if Array.length Sys.argv < 2 then begin
    Printf.printf "Usage: %s <ticker> [--expiration YYYY-MM-DD]\n" Sys.argv.(0);
    Printf.printf "\nScans for skew-based vertical spread opportunities.\n";
    Printf.printf "\nRequires data files in pricing/skew_verticals/data/:\n";
    Printf.printf "  - <ticker>_<exp>_calls.csv\n";
    Printf.printf "  - <ticker>_<exp>_puts.csv\n";
    Printf.printf "  - <ticker>_<exp>_metadata.csv\n";
    Printf.printf "  - <ticker>_prices.csv\n";
    Printf.printf "  - SPY_prices.csv\n";
    Printf.printf "\nRun Python fetchers first:\n";
    Printf.printf "  python3 pricing/skew_verticals/python/fetch/fetch_options_chain.py --ticker <ticker>\n";
    Printf.printf "  python3 pricing/skew_verticals/python/fetch/fetch_prices.py --ticker <ticker>\n";
    exit 1;
  end;

  let ticker = Sys.argv.(1) in
  let data_dir = "pricing/skew_verticals/data" in

  Printf.printf "\n╔════════════════════════════════════════════════════╗\n";
  Printf.printf "║  SKEW VERTICAL SPREADS SCANNER                     ║\n";
  Printf.printf "╚════════════════════════════════════════════════════╝\n";
  Printf.printf "\nScanning: %s\n" ticker;

  (* Find data files - use most recently modified metadata file *)
  let find_latest_expiration () =
    let cmd = Printf.sprintf "ls -t %s/%s_*_metadata.csv 2>/dev/null | head -1" data_dir ticker in
    let ic = Unix.open_process_in cmd in
    let file = try input_line ic with End_of_file -> "" in
    let _ = Unix.close_process_in ic in
    if file = "" then None
    else
      (* Extract expiration from filename *)
      let basename = Filename.basename file in
      let parts = String.split_on_char '_' basename in
      match parts with
      | _ :: exp :: _ :: _ -> Some exp
      | _ -> None
  in

  let expiration = match find_latest_expiration () with
    | Some exp -> exp
    | None ->
        Printf.printf "✗ No options data found. Run fetchers first.\n";
        exit 1
  in

  Printf.printf "Using expiration: %s\n" expiration;

  (* Load data *)
  let calls_file = Printf.sprintf "%s/%s_%s_calls.csv" data_dir ticker expiration in
  let puts_file = Printf.sprintf "%s/%s_%s_puts.csv" data_dir ticker expiration in
  let meta_file = Printf.sprintf "%s/%s_%s_metadata.csv" data_dir ticker expiration in
  let prices_file = Printf.sprintf "%s/%s_prices.csv" data_dir ticker in
  let spy_file = Printf.sprintf "%s/SPY_prices.csv" data_dir in

  Printf.printf "\nLoading options chain...\n";

  let calls = Io.load_options_csv ~file_path:calls_file in
  let puts = Io.load_options_csv ~file_path:puts_file in
  let (_, spot, exp_date, days, atm_strike) = Io.load_metadata_csv ~file_path:meta_file in

  let chain : Types.options_chain = {
    ticker;
    spot_price = spot;
    expiration = exp_date;
    days_to_expiry = days;
    calls;
    puts;
    atm_strike;
  } in

  Io.print_chain_summary chain;

  (* Load price data *)
  Printf.printf "\nLoading price history...\n";
  let stock_prices = Io.load_prices_csv ~file_path:prices_file in
  let market_prices = Io.load_prices_csv ~file_path:spy_file in

  Printf.printf "  Stock: %d days\n" (Array.length stock_prices);
  Printf.printf "  Market: %d days\n" (Array.length market_prices);

  (* Calculate skew metrics *)
  Printf.printf "\nCalculating skew metrics...\n";

  (* For demo, use simple ATM IV calculation *)
  let atm_iv =
    let atm_calls = Array.to_list calls |> List.filter (fun (c : Types.option_data) ->
      abs_float (c.strike -. atm_strike) < 5.0
    ) in
    if List.length atm_calls > 0 then
      (List.hd atm_calls).implied_vol
    else 0.20
  in

  (* Simple realized vol estimate from price history *)
  let realized_vol =
    let n = Array.length stock_prices in
    if n < 21 then 0.15
    else
      let returns = Array.init (n - 1) (fun i ->
        let p0 = snd stock_prices.(i) in
        let p1 = snd stock_prices.(i + 1) in
        (p1 -. p0) /. p0
      ) in
      let variance = Array.fold_left (fun acc r -> acc +. (r *. r)) 0.0 returns
        /. float_of_int (Array.length returns) in
      sqrt (variance *. 252.0)
  in

  (* Dummy historical skew (in real implementation, track this over time) *)
  let call_skew_history = Array.init 30 (fun _ -> 0.05 +. Random.float 0.05) in
  let put_skew_history = Array.init 30 (fun _ -> 0.05 +. Random.float 0.05) in

  let skew = Skew.compute_skew_metrics
    ~ticker
    ~calls
    ~puts
    ~atm_iv
    ~realized_vol
    ~call_skew_history
    ~put_skew_history
  in

  (* Calculate momentum *)
  Printf.printf "Calculating momentum...\n";

  let momentum = Momentum.compute_momentum
    ~ticker
    ~stock_prices
    ~market_prices
    ~rank_1m:0
    ~rank_3m:0
    ~percentile:50.0
  in

  (* Evaluate all four spread types and pick the best by expected value *)
  Printf.printf "\nSearching for optimal vertical spread...\n";

  let min_rr_credit = 0.10 in  (* Credit spreads have inherently lower R/R *)

  let min_rr_debit = 1.5 in  (* Debit spreads - 1.5:1 is realistic for high-vol stocks *)

  let candidates =
    if momentum.momentum_score > 0.0 then begin
      Printf.printf "  Momentum: BULLISH - evaluating bull spreads\n";
      [
        ("bull_call", Spreads.find_best_bull_call ~chain ~skew ~min_reward_risk:min_rr_debit);
        ("bull_put", Spreads.find_best_bull_put ~chain ~skew ~min_reward_risk:min_rr_credit);
      ]
    end else begin
      Printf.printf "  Momentum: BEARISH - evaluating bear spreads\n";
      [
        ("bear_put", Spreads.find_best_bear_put ~chain ~skew ~min_reward_risk:min_rr_debit);
        ("bear_call", Spreads.find_best_bear_call ~chain ~skew ~min_reward_risk:min_rr_credit);
      ]
    end
  in

  (* Pick the spread with highest expected value *)
  let spread_opt =
    let valid_spreads = List.filter_map (fun (_, opt) -> opt) candidates in
    if List.length valid_spreads = 0 then None
    else
      let best = List.fold_left (fun acc s ->
        match acc with
        | None -> Some s
        | Some best ->
            if s.Types.expected_value > best.Types.expected_value then Some s
            else Some best
      ) None valid_spreads in
      best
  in

  (match spread_opt with
   | Some s -> Printf.printf "  Best spread: %s (EV: $%.2f)\n" s.spread_type s.expected_value
   | None -> Printf.printf "  No valid spreads found\n");

  let _spread_type = match spread_opt with Some s -> s.spread_type | None -> "none" in

  (* Generate recommendation *)
  let recommendation = Scanner.make_recommendation
    ~chain
    ~skew
    ~momentum
    ~spread:spread_opt
    ~skew_threshold:(-2.0)
  in

  (* Print results *)
  Scanner.print_recommendation recommendation ~spot;

  (* Save results to JSON *)
  let output_dir = "pricing/skew_verticals/output" in
  Scanner.save_to_json recommendation ~output_dir;

  Printf.printf "\n"

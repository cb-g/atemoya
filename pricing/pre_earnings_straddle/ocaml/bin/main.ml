(** Pre-Earnings Straddle Scanner *)

open Pre_earnings_straddle_lib

let () =
  (* Parse command line *)
  if Array.length Sys.argv < 2 then begin
    Printf.printf "Usage: %s <ticker>\n" Sys.argv.(0);
    Printf.printf "\nScans for pre-earnings straddle opportunities.\n";
    Printf.printf "\nRequires data files in pricing/pre_earnings_straddle/data/:\n";
    Printf.printf "  - <ticker>_opportunity.csv (current straddle data)\n";
    Printf.printf "  - earnings_history.csv (historical implied/realized moves)\n";
    Printf.printf "  - model_coefficients.csv (trained model, optional)\n";
    Printf.printf "\nRun Python fetchers first:\n";
    Printf.printf "  python3 pricing/pre_earnings_straddle/python/fetch/fetch_straddle_data.py --ticker <ticker>\n";
    exit 1;
  end;

  let ticker = Sys.argv.(1) in
  let data_dir = "pricing/pre_earnings_straddle/data" in

  Printf.printf "\n╔════════════════════════════════════════════════════╗\n";
  Printf.printf "║  PRE-EARNINGS STRADDLE SCANNER                     ║\n";
  Printf.printf "╚════════════════════════════════════════════════════╝\n";
  Printf.printf "\nScanning: %s\n" ticker;

  (* Load model coefficients *)
  let coef_file = Printf.sprintf "%s/model_coefficients.csv" data_dir in
  let coefficients = Model.load_coefficients ~file_path:coef_file in

  Printf.printf "\nUsing model coefficients:\n";
  Printf.printf "  Intercept: %.4f\n" coefficients.intercept;
  Printf.printf "  Coef 1 (Implied/Last Implied): %.4f\n" coefficients.coef_implied_vs_last_implied;
  Printf.printf "  Coef 2 (Implied-Last Realized): %.4f\n" coefficients.coef_implied_vs_last_realized;
  Printf.printf "  Coef 3 (Implied/Avg Implied): %.4f\n" coefficients.coef_implied_vs_avg_implied;
  Printf.printf "  Coef 4 (Implied-Avg Realized): %.4f\n" coefficients.coef_implied_vs_avg_realized;

  (* Load current opportunity *)
  Printf.printf "\nLoading straddle opportunity...\n";
  let opp_file = Printf.sprintf "%s/%s_opportunity.csv" data_dir ticker in
  let opportunity = Io.load_opportunity ~file_path:opp_file in

  match opportunity with
  | None ->
      Printf.printf "✗ No opportunity data found. Run fetcher first.\n";
      exit 1
  | Some opp ->
      Printf.printf "✓ Loaded opportunity for %s (earnings: %s, %d days)\n"
        opp.ticker opp.earnings_date opp.days_to_earnings;

      (* Load historical earnings data *)
      Printf.printf "\nLoading historical earnings data...\n";
      let history_file = Printf.sprintf "%s/earnings_history.csv" data_dir in
      let historical_events = Io.load_earnings_history ~file_path:history_file ~ticker in

      Printf.printf "✓ Loaded %d historical earnings events\n" (Array.length historical_events);

      if Array.length historical_events = 0 then begin
        Printf.printf "✗ No historical data available. Cannot calculate signals.\n";
        exit 1
      end;

      (* Calculate signals *)
      Printf.printf "\nCalculating signals...\n";
      let signals = Signals.calculate_signals
        ~ticker
        ~current_implied:opp.current_implied_move
        ~historical_events
      in

      match signals with
      | None ->
          Printf.printf "✗ Could not calculate signals\n";
          exit 1
      | Some sigs ->
          (* Make recommendation *)
          let recommendation = Scanner.make_recommendation
            ~opportunity:opp
            ~signals:sigs
            ~coefficients
            ~min_predicted_return:0.0  (* Filter to positive predicted return *)
            ~target_kelly_fraction:0.04  (* Use 4% of Kelly *)
          in

          (* Print results *)
          Scanner.print_recommendation recommendation;

          Printf.printf "\n"

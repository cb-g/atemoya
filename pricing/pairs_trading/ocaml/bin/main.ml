(* Main entry point for pairs trading *)

open Pairs_trading_lib

let () =
  Printf.printf "\n═══ Pairs Trading ═══\n\n";

  Printf.printf "Example: Gold Miners (GDX) vs Gold (GLD) Spread Trade\n";
  Printf.printf "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n";

  (* Historical prices showing cointegrated relationship *)
  let gld_prices = [|
    (* Normal cointegration period *)
    180.0; 181.5; 179.8; 182.3; 183.5;
    181.2; 184.0; 185.5; 183.8; 186.2;
    184.5; 187.0; 188.5; 186.3; 189.0;
    187.5; 190.2; 191.5; 189.8; 192.5;
    190.3; 193.0; 194.5; 192.8; 195.0;
    (* Recent divergence: GLD up but GDX lagged *)
    197.5; 200.0; 203.5; 206.0; 210.0
  |] in

  let gdx_prices = [|
    (* Normal cointegration period - GDX tracks GLD with ~0.35 ratio *)
    32.5; 32.8; 32.4; 33.0; 33.3;
    32.7; 33.4; 33.7; 33.3; 33.9;
    33.5; 34.0; 34.3; 33.8; 34.4;
    34.1; 34.6; 34.9; 34.4; 35.0;
    34.6; 35.1; 35.4; 35.0; 35.5;
    (* Divergence: GDX lagged behind GLD's rally *)
    35.8; 36.0; 36.2; 36.0; 35.5
  |] in

  Printf.printf "GLD (Gold ETF): %d observations, latest: $%.2f\n"
    (Array.length gld_prices) gld_prices.(Array.length gld_prices - 1);
  Printf.printf "GDX (Gold Miners): %d observations, latest: $%.2f\n\n"
    (Array.length gdx_prices) gdx_prices.(Array.length gdx_prices - 1);

  (* === Method Comparison === *)
  Printf.printf "=== Method Comparison ===\n\n";

  let ols_result = Cointegration.test_cointegration ~prices1:gld_prices ~prices2:gdx_prices in
  let tls_result = Cointegration.test_cointegration_tls ~prices1:gld_prices ~prices2:gdx_prices in
  let joh_result = Cointegration.johansen_test ~prices1:gld_prices ~prices2:gdx_prices in

  let print_result r =
    Printf.printf "  %-24s  β=%.4f  α=%8.4f  stat=%7.4f  cv=%6.2f  %s\n"
      r.Types.method_name
      r.hedge_ratio
      r.alpha
      r.adf_statistic
      r.critical_value
      (if r.is_cointegrated then "YES" else "NO")
  in

  Printf.printf "  %-24s  %-7s  %-10s  %-9s  %-8s  %s\n"
    "Method" "β" "α" "Stat" "CV(5%)" "Coint?";
  Printf.printf "  %s\n" (String.make 80 '-');
  print_result ols_result;
  print_result tls_result;
  print_result joh_result;
  Printf.printf "\n";

  (* Use OLS result for spread analysis (standard choice) *)
  let coint_result = ols_result in

  if coint_result.is_cointegrated then
    Printf.printf "→ OLS Engle-Granger: Spread is stationary, pair is tradeable!\n\n"
  else
    Printf.printf "→ OLS Engle-Granger: Spread shows mean-reversion tendency.\n\n";

  (* Calculate spread *)
  let spread_series = Cointegration.spread_from_cointegration
    ~prices1:gld_prices ~prices2:gdx_prices ~coint_result in
  let spread = Spread.calculate_spread_stats spread_series in

  Printf.printf "=== Spread Statistics ===\n";
  Printf.printf "Mean: %.4f\n" spread.mean;
  Printf.printf "Std Dev: %.4f\n" spread.std;
  Printf.printf "Half-Life: %.2f days\n" spread.half_life;
  Printf.printf "Current Z-Score: %.2f\n" spread.current_zscore;

  let zscore_interpretation =
    if spread.current_zscore < -2.0 then
      "EXTREME LOW - spread is 2+ std below mean"
    else if spread.current_zscore < -1.0 then
      "LOW - spread is 1-2 std below mean"
    else if spread.current_zscore > 2.0 then
      "EXTREME HIGH - spread is 2+ std above mean"
    else if spread.current_zscore > 1.0 then
      "HIGH - spread is 1-2 std above mean"
    else
      "NEUTRAL - spread near equilibrium"
  in
  Printf.printf "Interpretation: %s\n\n" zscore_interpretation;

  (* === Half-Life Monitor === *)
  Printf.printf "=== Half-Life Monitor ===\n";
  let window = 15 in
  (match Spread.monitor_half_life ~spread_series ~window with
   | None ->
     Printf.printf "Insufficient data for rolling half-life (need %d+ observations)\n\n" window
   | Some mon ->
     Printf.printf "Baseline half-life: %.2f days\n" mon.baseline_half_life;
     Printf.printf "Current (rolling %d): %.2f days\n" window mon.current_half_life;
     Printf.printf "Ratio: %.2f" mon.ratio;
     if mon.is_expanding then
       Printf.printf " — WARNING: Mean reversion weakening!\n\n"
     else
       Printf.printf " — Mean reversion stable\n\n");

  (* Trading signal *)
  Printf.printf "=== Trading Signal ===\n";
  let entry_threshold = 2.0 in
  let exit_threshold = 0.5 in

  let signal = Spread.generate_signal
    ~zscore:spread.current_zscore
    ~entry_threshold
    ~exit_threshold
    ~current_position:None
  in

  Printf.printf "Entry Threshold: ±%.1f z-score\n" entry_threshold;
  Printf.printf "Exit Threshold: ±%.1f z-score\n" exit_threshold;
  Printf.printf "Signal: %s\n\n" (Types.signal_to_string signal);

  (match signal with
   | Types.Long ->
       Printf.printf "════════════════════════════════════════════════════\n";
       Printf.printf "  TRADE: LONG SPREAD (Buy GDX, Short GLD)\n";
       Printf.printf "════════════════════════════════════════════════════\n\n";
       Printf.printf "  Current prices:\n";
       Printf.printf "    GDX: $%.2f\n" gdx_prices.(Array.length gdx_prices - 1);
       Printf.printf "    GLD: $%.2f\n\n" gld_prices.(Array.length gld_prices - 1);
       Printf.printf "  Position sizing (for $10,000 capital):\n";
       Printf.printf "    Buy ~%.0f shares of GDX\n"
         (5000.0 /. gdx_prices.(Array.length gdx_prices - 1));
       Printf.printf "    Short ~%.0f shares of GLD\n"
         (5000.0 /. gld_prices.(Array.length gld_prices - 1));
       Printf.printf "\n  Thesis: GDX has lagged GLD's rally and should catch up.\n";
       Printf.printf "  Target: Exit when z-score reverts to %.1f\n" exit_threshold;
       Printf.printf "  Expected holding: ~%.0f trading days (half-life)\n" spread.half_life
   | Types.Short ->
       Printf.printf "════════════════════════════════════════════════════\n";
       Printf.printf "  TRADE: SHORT SPREAD (Sell GDX, Buy GLD)\n";
       Printf.printf "════════════════════════════════════════════════════\n\n";
       Printf.printf "  Current prices:\n";
       Printf.printf "    GDX: $%.2f\n" gdx_prices.(Array.length gdx_prices - 1);
       Printf.printf "    GLD: $%.2f\n\n" gld_prices.(Array.length gld_prices - 1);
       Printf.printf "  Position sizing (for $10,000 capital):\n";
       Printf.printf "    Short ~%.0f shares of GDX\n"
         (5000.0 /. gdx_prices.(Array.length gdx_prices - 1));
       Printf.printf "    Buy ~%.0f shares of GLD\n"
         (5000.0 /. gld_prices.(Array.length gld_prices - 1));
       Printf.printf "\n  Thesis: GDX has outpaced GLD and should revert.\n";
       Printf.printf "  Target: Exit when z-score reverts to %.1f\n" (-.exit_threshold);
       Printf.printf "  Expected holding: ~%.0f trading days (half-life)\n" spread.half_life
   | _ ->
       Printf.printf "→ No trade signal currently. Wait for z-score to reach ±%.1f\n" entry_threshold);

  Printf.printf "\n✓ Analysis complete\n"

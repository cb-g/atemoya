(* Main entry point for dispersion trading *)

open Dispersion_trading_lib

let () =
  Printf.printf "\n═══ Dispersion Trading ═══\n\n";

  (* Example: Calculate dispersion metrics for SPY vs constituents *)

  (* Hypothetical data *)
  let index_iv = 0.15 in  (* SPY implied vol: 15% *)
  let constituent_vols = [| 0.25; 0.30; 0.20; 0.28; 0.22 |] in  (* AAPL, MSFT, GOOGL, AMZN, NVDA *)
  let weights = [| 0.25; 0.20; 0.15; 0.15; 0.25 |] in  (* Portfolio weights *)
  let tickers = [| "AAPL"; "MSFT"; "GOOGL"; "AMZN"; "NVDA" |] in

  Printf.printf "Index: SPY (IV = %.2f%%)\n" (index_iv *. 100.0);
  Printf.printf "\nConstituents:\n";
  Array.iteri (fun i ticker ->
    Printf.printf "  %s: IV = %.2f%%, Weight = %.1f%%\n"
      ticker
      (constituent_vols.(i) *. 100.0)
      (weights.(i) *. 100.0)
  ) tickers;

  (* Calculate weighted average IV *)
  let weighted_avg_iv = Dispersion.weighted_avg_iv ~constituent_vols ~weights in
  Printf.printf "\nWeighted Avg IV: %.2f%%\n" (weighted_avg_iv *. 100.0);

  (* Calculate dispersion level *)
  let disp_level = Dispersion.dispersion_level ~index_iv ~constituent_vols ~weights in
  Printf.printf "Dispersion Level: %.2f%%\n" (disp_level *. 100.0);

  (* Calculate implied correlation *)
  let implied_corr = Correlation.implied_correlation ~index_vol:index_iv ~constituent_vols ~weights in
  Printf.printf "Implied Correlation: %.2f%%\n\n" (implied_corr *. 100.0);

  (* Trading signal *)
  if disp_level > 0.05 then
    Printf.printf "Signal: LONG DISPERSION (buy stocks, sell index)\n"
  else if disp_level < -0.02 then
    Printf.printf "Signal: SHORT DISPERSION (sell stocks, buy index)\n"
  else
    Printf.printf "Signal: NEUTRAL\n";

  Printf.printf "\n✓ Analysis complete\n";

  (* Example correlation calculation *)
  Printf.printf "\n═══ Correlation Analysis ═══\n\n";

  (* Hypothetical returns data *)
  let aapl_returns = [| 0.01; -0.02; 0.03; -0.01; 0.02 |] in
  let msft_returns = [| 0.02; -0.01; 0.02; 0.00; 0.01 |] in

  let corr = Correlation.correlation aapl_returns msft_returns in
  Printf.printf "AAPL-MSFT Correlation: %.2f%%\n" (corr *. 100.0);

  Printf.printf "\n"

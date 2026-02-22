(** Signal Calculation Module *)

open Types

(** Calculate the four predictive signals from historical data *)
let calculate_signals
    ~(ticker : string)
    ~(current_implied : float)
    ~(historical_events : earnings_event array)
    : signals option =

  let n = Array.length historical_events in

  if n = 0 then None
  else
    (* Get last event *)
    let last_event = historical_events.(n - 1) in
    let last_implied = last_event.implied_move in
    let last_realized = last_event.realized_move in

    (* Calculate averages across all history *)
    let sum_implied = Array.fold_left (fun acc e -> acc +. e.implied_move) 0.0 historical_events in
    let sum_realized = Array.fold_left (fun acc e -> acc +. e.realized_move) 0.0 historical_events in

    let avg_implied = sum_implied /. float_of_int n in
    let avg_realized = sum_realized /. float_of_int n in

    (* Calculate the four signals *)
    let implied_vs_last_implied_ratio =
      if last_implied > 0.0 then
        current_implied /. last_implied
      else 1.0
    in

    let implied_vs_last_realized_gap =
      current_implied -. last_realized
    in

    let implied_vs_avg_implied_ratio =
      if avg_implied > 0.0 then
        current_implied /. avg_implied
      else 1.0
    in

    let implied_vs_avg_realized_gap =
      current_implied -. avg_realized
    in

    Some {
      ticker;
      implied_vs_last_implied_ratio;
      implied_vs_last_realized_gap;
      implied_vs_avg_implied_ratio;
      implied_vs_avg_realized_gap;
      current_implied;
      last_implied;
      last_realized;
      avg_implied;
      avg_realized;
      num_historical_events = n;
    }

(** Print signals *)
let print_signals (s : signals) : unit =
  Printf.printf "\n=== Signals: %s ===\n" s.ticker;
  Printf.printf "Historical events: %d\n" s.num_historical_events;
  Printf.printf "\nCurrent implied move: %.2f%%\n" (s.current_implied *. 100.0);
  Printf.printf "Last implied: %.2f%% | Last realized: %.2f%%\n"
    (s.last_implied *. 100.0) (s.last_realized *. 100.0);
  Printf.printf "Avg implied: %.2f%% | Avg realized: %.2f%%\n"
    (s.avg_implied *. 100.0) (s.avg_realized *. 100.0);

  Printf.printf "\nFour Signals (lower = better):\n";
  Printf.printf "  1. Current/Last Implied Ratio: %.3f\n" s.implied_vs_last_implied_ratio;
  Printf.printf "  2. Current - Last Realized Gap: %.2f%%\n" (s.implied_vs_last_realized_gap *. 100.0);
  Printf.printf "  3. Current/Avg Implied Ratio: %.3f\n" s.implied_vs_avg_implied_ratio;
  Printf.printf "  4. Current - Avg Realized Gap: %.2f%%\n" (s.implied_vs_avg_realized_gap *. 100.0);

  (* Interpretation *)
  if s.implied_vs_avg_implied_ratio < 0.9 then
    Printf.printf "\n✓ Current implied is CHEAP vs historical average\n"
  else if s.implied_vs_avg_implied_ratio > 1.1 then
    Printf.printf "\n✗ Current implied is EXPENSIVE vs historical average\n";

  if s.implied_vs_last_implied_ratio < 0.9 then
    Printf.printf "✓ Current implied is CHEAP vs last earnings\n"
  else if s.implied_vs_last_implied_ratio > 1.1 then
    Printf.printf "✗ Current implied is EXPENSIVE vs last earnings\n"

(* I/O operations for FX hedging *)

open Types

(** CSV Reading **)

(* Read FX rates from CSV *)
let read_fx_rates filename =
  try
    let ic = open_in filename in
    let lines = ref [] in
    begin
      try
        (* Skip header *)
        let _ = input_line ic in
        while true do
          let line = input_line ic in
          lines := line :: !lines
        done
      with End_of_file -> close_in ic
    end;

    let parsed = List.filter_map (fun line ->
      let parts = String.split_on_char ',' line in
      match parts with
      | timestamp_str :: rate_str :: _ ->
          begin try
            let timestamp = float_of_string (String.trim timestamp_str) in
            let rate = float_of_string (String.trim rate_str) in
            Some (timestamp, rate)
          with Failure _ -> None
          end
      | _ -> None
    ) (List.rev !lines) in

    Array.of_list parsed
  with Sys_error msg ->
    Printf.eprintf "Error reading FX rates from %s: %s\n" filename msg;
    [||]

(* Read futures prices from CSV *)
let read_futures_prices filename =
  read_fx_rates filename  (* Same format *)

(* Read portfolio from CSV *)
let read_portfolio filename =
  try
    let ic = open_in filename in
    let lines = ref [] in
    begin
      try
        (* Skip header *)
        let _ = input_line ic in
        while true do
          let line = input_line ic in
          lines := line :: !lines
        done
      with End_of_file -> close_in ic
    end;

    let parsed = List.filter_map (fun line ->
      let parts = String.split_on_char ',' line in
      match parts with
      | ticker :: qty_str :: price_str :: curr_str :: rest ->
          begin try
            let ticker = String.trim ticker in
            let quantity = float_of_string (String.trim qty_str) in
            let price_usd = float_of_string (String.trim price_str) in
            let market_value_usd = quantity *. price_usd in
            let currency = currency_of_string (String.trim curr_str) in
            let pct = match rest with
              | pct_str :: _ -> (try float_of_string (String.trim pct_str) with Failure _ -> 1.0)
              | [] -> 1.0
            in

            Some {
              ticker;
              quantity;
              price_usd;
              market_value_usd;
              currency_exposure = [(currency, pct)];
            }
          with Failure _ | Not_found -> None
          end
      | _ -> None
    ) (List.rev !lines) in

    Array.of_list parsed
  with Sys_error msg ->
    Printf.eprintf "Error reading portfolio from %s: %s\n" filename msg;
    [||]

(** CSV Writing **)

(* Write hedge result to CSV *)
let write_hedge_result ~filename ~(result : hedge_result) =
  try
    let oc = open_out filename in

    Printf.fprintf oc "metric,value\n";
    Printf.fprintf oc "unhedged_pnl,%.6f\n" result.unhedged_pnl;
    Printf.fprintf oc "hedged_pnl,%.6f\n" result.hedged_pnl;
    Printf.fprintf oc "hedge_pnl,%.6f\n" result.hedge_pnl;
    Printf.fprintf oc "transaction_costs,%.6f\n" result.transaction_costs;
    Printf.fprintf oc "num_rebalances,%d\n" result.num_rebalances;
    Printf.fprintf oc "hedge_effectiveness,%.4f\n" result.hedge_effectiveness;
    Printf.fprintf oc "max_drawdown_unhedged,%.4f\n" result.max_drawdown_unhedged;
    Printf.fprintf oc "max_drawdown_hedged,%.4f\n" result.max_drawdown_hedged;

    (match result.sharpe_unhedged with
     | Some sr -> Printf.fprintf oc "sharpe_unhedged,%.4f\n" sr
     | None -> Printf.fprintf oc "sharpe_unhedged,N/A\n");

    (match result.sharpe_hedged with
     | Some sr -> Printf.fprintf oc "sharpe_hedged,%.4f\n" sr
     | None -> Printf.fprintf oc "sharpe_hedged,N/A\n");

    close_out oc;
    Printf.printf "Wrote hedge results to %s\n" filename
  with Sys_error msg ->
    Printf.eprintf "Error writing results to %s: %s\n" filename msg

(* Write exposure analysis to CSV *)
let write_exposure_analysis ~filename ~exposures =
  try
    let oc = open_out filename in

    Printf.fprintf oc "currency,net_exposure_usd,pct_of_portfolio,num_positions\n";

    Array.iter (fun exp ->
      Printf.fprintf oc "%s,%.2f,%.2f,%d\n"
        (currency_to_string exp.currency)
        exp.net_exposure_usd
        exp.pct_of_portfolio
        (List.length exp.positions)
    ) exposures;

    close_out oc;
    Printf.printf "Wrote exposure analysis to %s\n" filename
  with Sys_error msg ->
    Printf.eprintf "Error writing exposure to %s: %s\n" filename msg

(* Write simulation snapshots to CSV *)
let write_simulation_snapshots ~filename ~snapshots =
  try
    let oc = open_out filename in

    Printf.fprintf oc "timestamp,fx_rate,futures_price,unhedged_pnl,hedged_pnl,hedge_pnl,exposure_value,net_value,margin_balance,cumulative_costs,futures_position\n";

    Array.iter (fun (s : simulation_snapshot) ->
      Printf.fprintf oc "%.8f,%.6f,%.6f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f\n"
        s.timestamp
        s.spot_rate
        s.futures_price
        s.unhedged_pnl
        s.hedged_pnl
        s.hedge_value
        s.exposure_value
        s.net_value
        s.margin_balance
        s.cumulative_costs
        s.futures_position
    ) snapshots;

    close_out oc;
    Printf.printf "Wrote simulation snapshots to %s\n" filename
  with Sys_error msg ->
    Printf.eprintf "Error writing snapshots to %s: %s\n" filename msg

(* I/O operations for gamma scalping *)

open Types

(* ========================================================================== *)
(* CSV Reading *)
(* ========================================================================== *)

(* Read intraday price data from CSV

   Format: timestamp,price
   Where timestamp is in days (e.g., 1 minute ≈ 0.000694 days)
*)
let read_intraday_prices filename =
  try
    let ic = open_in filename in
    let lines = ref [] in
    begin
      try
        (* Skip header if present *)
        let header = input_line ic in
        if not (String.contains header ',') then
          lines := [header];  (* No header, include first line *)

        while true do
          let line = input_line ic in
          lines := line :: !lines
        done
      with End_of_file -> close_in ic
    end;

    let parsed = List.filter_map (fun line ->
      let parts = String.split_on_char ',' line in
      match parts with
      | timestamp_str :: price_str :: _ ->
          begin try
            let timestamp = float_of_string (String.trim timestamp_str) in
            let price = float_of_string (String.trim price_str) in
            Some (timestamp, price)
          with Failure _ -> None
          end
      | _ -> None
    ) (List.rev !lines) in

    Array.of_list parsed
  with Sys_error msg ->
    Printf.eprintf "Error reading price data from %s: %s\n" filename msg;
    [||]

(* Read IV timeseries from CSV

   Format: timestamp,iv
*)
let read_iv_timeseries filename =
  try
    let ic = open_in filename in
    let lines = ref [] in
    begin
      try
        (* Skip header if present *)
        let header = input_line ic in
        if not (String.contains header ',') then
          lines := [header];

        while true do
          let line = input_line ic in
          lines := line :: !lines
        done
      with End_of_file -> close_in ic
    end;

    let parsed = List.filter_map (fun line ->
      let parts = String.split_on_char ',' line in
      match parts with
      | timestamp_str :: iv_str :: _ ->
          begin try
            let timestamp = float_of_string (String.trim timestamp_str) in
            let iv = float_of_string (String.trim iv_str) in
            Some (timestamp, iv)
          with Failure _ -> None
          end
      | _ -> None
    ) (List.rev !lines) in

    Array.of_list parsed
  with Sys_error msg ->
    Printf.eprintf "Error reading IV data from %s: %s\n" filename msg;
    [||]

(* ========================================================================== *)
(* CSV Writing *)
(* ========================================================================== *)

(* Write simulation summary to CSV *)
let write_simulation_summary ~filename ~result =
  try
    let oc = open_out filename in

    (* Write header *)
    Printf.fprintf oc "metric,value\n";

    (* Write metrics *)
    Printf.fprintf oc "position,%s\n"
      (match result.position with
       | Straddle { strike } -> Printf.sprintf "Straddle(K=%.2f)" strike
       | Strangle { call_strike; put_strike } ->
           Printf.sprintf "Strangle(C=%.2f,P=%.2f)" call_strike put_strike
       | SingleOption { option_type; strike } ->
           let opt_type = match option_type with Call -> "Call" | Put -> "Put" in
           Printf.sprintf "%s(K=%.2f)" opt_type strike);

    Printf.fprintf oc "entry_premium,%.6f\n" result.entry_premium;
    Printf.fprintf oc "entry_iv,%.4f\n" result.entry_iv;
    Printf.fprintf oc "expiry_years,%.4f\n" result.expiry;
    Printf.fprintf oc "final_pnl,%.6f\n" result.final_pnl;
    Printf.fprintf oc "gamma_pnl_total,%.6f\n" result.gamma_pnl_total;
    Printf.fprintf oc "theta_pnl_total,%.6f\n" result.theta_pnl_total;
    Printf.fprintf oc "vega_pnl_total,%.6f\n" result.vega_pnl_total;
    Printf.fprintf oc "hedge_pnl_total,%.6f\n" result.hedge_pnl_total;
    Printf.fprintf oc "num_hedges,%d\n" result.num_hedges;
    Printf.fprintf oc "total_transaction_costs,%.6f\n" result.total_transaction_costs;
    Printf.fprintf oc "max_drawdown,%.4f\n" result.max_drawdown;
    Printf.fprintf oc "win_rate,%.4f\n" result.win_rate;
    Printf.fprintf oc "avg_hedge_interval_minutes,%.2f\n" result.avg_hedge_interval_minutes;

    (match result.sharpe_ratio with
     | Some sr -> Printf.fprintf oc "sharpe_ratio,%.4f\n" sr
     | None -> Printf.fprintf oc "sharpe_ratio,N/A\n");

    close_out oc;
    Printf.printf "Wrote simulation summary to %s\n" filename
  with Sys_error msg ->
    Printf.eprintf "Error writing summary to %s: %s\n" filename msg

(* Write P&L timeseries to CSV *)
let write_pnl_timeseries ~filename ~pnl_timeseries =
  try
    let oc = open_out filename in

    (* Write header *)
    Printf.fprintf oc "timestamp,spot_price,option_value,option_pnl,gamma_pnl,theta_pnl,vega_pnl,hedge_pnl,transaction_costs,total_pnl,cumulative_pnl\n";

    (* Write rows *)
    Array.iter (fun snapshot ->
      Printf.fprintf oc "%.8f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n"
        snapshot.timestamp
        snapshot.spot_price
        snapshot.option_value
        snapshot.option_pnl
        snapshot.gamma_pnl
        snapshot.theta_pnl
        snapshot.vega_pnl
        snapshot.hedge_pnl
        snapshot.transaction_costs
        snapshot.total_pnl
        snapshot.cumulative_pnl
    ) pnl_timeseries;

    close_out oc;
    Printf.printf "Wrote P&L timeseries to %s\n" filename
  with Sys_error msg ->
    Printf.eprintf "Error writing P&L timeseries to %s: %s\n" filename msg

(* Write hedge log to CSV *)
let write_hedge_log ~filename ~(hedge_log : hedge_event array) =
  try
    let oc = open_out filename in

    (* Write header *)
    Printf.fprintf oc "timestamp,spot_price,delta_before,hedge_quantity,hedge_cost\n";

    (* Write rows *)
    Array.iter (fun (event : hedge_event) ->
      Printf.fprintf oc "%.8f,%.6f,%.6f,%.6f,%.6f\n"
        event.timestamp
        event.spot_price
        event.delta_before
        event.hedge_quantity
        event.hedge_cost
    ) hedge_log;

    close_out oc;
    Printf.printf "Wrote hedge log to %s\n" filename
  with Sys_error msg ->
    Printf.eprintf "Error writing hedge log to %s: %s\n" filename msg

(* ========================================================================== *)
(* Configuration *)
(* ========================================================================== *)

(* Parse command-line arguments (placeholder implementation) *)
let parse_config _argv =
  (* For now, return default config *)
  (* TODO: Implement proper CLI argument parsing *)
  default_config

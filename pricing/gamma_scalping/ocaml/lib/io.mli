(* Interface for I/O operations *)

open Types

(** CSV Reading **)

(* Read intraday price data from CSV

   Expected format:
   timestamp,price
   0.0,100.0
   0.00026,100.5
   ...

   where timestamp is in days (e.g., 1 minute = 1/(24*60) ≈ 0.000694 days)
*)
val read_intraday_prices : string -> (float * float) array

(* Read IV timeseries from CSV

   Expected format:
   timestamp,iv
   0.0,0.20
   0.00026,0.21
   ...
*)
val read_iv_timeseries : string -> (float * float) array

(** CSV Writing **)

(* Write simulation result summary to CSV *)
val write_simulation_summary :
  filename:string ->
  result:simulation_result ->
  unit

(* Write P&L timeseries to CSV *)
val write_pnl_timeseries :
  filename:string ->
  pnl_timeseries:pnl_snapshot array ->
  unit

(* Write hedge log to CSV *)
val write_hedge_log :
  filename:string ->
  hedge_log:hedge_event array ->
  unit

(** Configuration reading **)

(* Parse command-line arguments or config file (placeholder) *)
val parse_config : string array -> simulation_config

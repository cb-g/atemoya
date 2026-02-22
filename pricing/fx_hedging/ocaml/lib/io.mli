(* Interface for I/O operations *)

open Types

(** CSV Reading **)

(* Read FX rate timeseries from CSV

   Expected format:
   date,rate
   2024-01-01,1.1050
   2024-01-02,1.1075
   ...
*)
val read_fx_rates : string -> (float * float) array

(* Read futures prices from CSV *)
val read_futures_prices : string -> (float * float) array

(* Read portfolio positions from CSV *)
val read_portfolio : string -> portfolio_position array

(** CSV Writing **)

(* Write hedge backtest results to CSV *)
val write_hedge_result :
  filename:string ->
  result:hedge_result ->
  unit

(* Write FX exposure analysis to CSV *)
val write_exposure_analysis :
  filename:string ->
  exposures:fx_exposure array ->
  unit

(* Write simulation snapshots to CSV *)
val write_simulation_snapshots :
  filename:string ->
  snapshots:simulation_snapshot array ->
  unit

(* Interface for I/O operations *)

open Types

(** CSV Reading **)

(* Read option chain data: strike, expiry, bid, ask, volume *)
val read_option_chain : string -> (float * float * float * float * int) array

(* Read historical skew observations *)
val read_skew_observations : string -> skew_observation array

(** JSON Reading **)

(* Read volatility surface parameters *)
val read_vol_surface : string -> vol_surface

(* Read underlying asset data *)
val read_underlying_data : string -> underlying_data

(* Read skew trading configuration *)
val read_skew_config : string -> skew_config

(** CSV Writing **)

(* Write skew observations to CSV *)
val write_skew_observations_csv : string -> skew_observation array -> unit

(* Write trading signals to CSV *)
val write_signals_csv : string -> skew_signal array -> unit

(* Write skew positions to CSV *)
val write_positions_csv : string -> skew_position array -> unit

(* Write backtest P&L to CSV *)
val write_pnl_csv : string -> strategy_pnl array -> unit

(** JSON Writing **)

(* Write skew statistics *)
val write_skew_stats_json : string -> (float * float * float * float) -> unit

(* Write calibrated vol surface *)
val write_vol_surface_json : string -> vol_surface -> unit

(** Logging **)

(* Write log message with timestamp *)
val write_log : string -> string -> unit

(** Directory Management **)

(* Ensure output directories exist *)
val ensure_output_dirs : unit -> unit

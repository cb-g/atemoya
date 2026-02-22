(* Interface for I/O operations (CSV and JSON) *)

open Types

(** Read price data from CSV
    Expected columns: date, close
*)
val read_price_data : string -> (float * float) array

(** Read OHLC data from CSV
    Expected columns: date, open, high, low, close
*)
val read_ohlc_data : string -> (float * float * float * float * float) array

(** Read volatility surface parameters from JSON *)
val read_vol_surface : string -> vol_surface

(** Write variance swap details to CSV *)
val write_variance_swap_csv : string -> variance_swap -> unit

(** Write VRP observations to CSV *)
val write_vrp_observations_csv : string -> vrp_observation array -> unit

(** Write trading signals to CSV *)
val write_signals_csv : string -> vrp_trading_signal array -> unit

(** Write replication portfolio to CSV *)
val write_replication_csv : string -> replication_portfolio -> unit

(** Write strategy P&L to CSV *)
val write_pnl_csv : string -> variance_strategy_pnl array -> unit

(** Write VRP statistics summary to JSON *)
val write_vrp_stats_json : string -> (float * float * float) -> unit

(** Read underlying data from JSON *)
val read_underlying_data : string -> underlying_data

(** Write log message to file *)
val write_log : string -> string -> unit

(** Create output directories if they don't exist *)
val ensure_output_dirs : unit -> unit

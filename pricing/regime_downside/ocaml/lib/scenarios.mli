(** Weekly scenario generation from daily returns *)

open Types

(** Convert daily returns to weekly returns by compounding *)
val daily_to_weekly : float array -> float array

(** Create weekly scenario matrix R[t,i] from asset return series *)
val create_weekly_scenarios : return_series list -> float array array

(** Get ordered list of tickers matching scenario matrix columns *)
val get_tickers_ordered : return_series list -> string list

(** Create weekly benchmark scenario vector *)
val create_weekly_benchmark : float array -> float array

(** Create weekly cash scenario vector (typically zeros) *)
val create_weekly_cash : int -> float array

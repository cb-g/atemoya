(** JSON I/O and console output for tail risk forecasting *)

open Types

(** Read intraday data from JSON file (output of fetch_intraday.py) *)
val read_intraday_data : string -> intraday_data option

(** Write analysis result to JSON file *)
val write_result_json : string -> analysis_result -> unit

(** Print tail risk forecast to console *)
val print_forecast : analysis_result -> unit

(** Print HAR model summary *)
val print_har_summary : har_coefficients -> unit

(** Print jump summary *)
val print_jump_summary : jump_indicator array -> unit

(** Format percentage *)
val pct : float -> string

(** Format basis points *)
val bps : float -> string

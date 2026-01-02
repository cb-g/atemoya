(** Data I/O and logging utilities *)

open Types

(** Read returns data from CSV *)
val read_returns_csv : filename:string -> ticker:string -> return_series

(** Read benchmark data from CSV *)
val read_benchmark_csv : filename:string -> benchmark

(** Write log entry to file *)
val write_log_entry : log_file:string -> entry:log_entry -> unit

(** Read optimization parameters from JSON *)
val read_params_json : filename:string -> opt_params

(** Write optimization results to CSV *)
val write_result_csv : filename:string -> results:(string * optimization_result) list -> unit

(** Write dual optimization results to CSV (constrained and frictionless) *)
val write_dual_result_csv : filename:string -> results:(string * dual_optimization_result) list -> unit

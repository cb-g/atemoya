(** JSON parsing and output formatting *)

open Types

(** Read company multiples data from JSON file *)
val read_multiples_data : string -> company_multiples

(** Load sector benchmark from JSON file *)
val load_sector_benchmark : string -> string -> benchmark_stats

(** Create a default benchmark (when no file exists) *)
val default_benchmark : string -> benchmark_stats

(** Print single ticker result to console *)
val print_single_result : single_ticker_result -> unit

(** Print comparative result to console *)
val print_comparative_result : comparative_result -> unit

(** Write single ticker result to JSON file *)
val write_single_result_json : string -> single_ticker_result -> unit

(** Write comparative result to JSON file *)
val write_comparative_result_json : string -> comparative_result -> unit

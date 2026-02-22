(** I/O operations for perpetual futures pricing. *)

open Types

val read_market_data : string -> market_data
val write_pricing_result : string -> pricing_result -> unit
val write_analysis_result : string -> analysis_result -> unit
val write_option_grid : string -> (float * float * float) list -> unit

val print_pricing_dashboard : contract_type -> pricing_result -> unit
val print_option_result : option_type -> option_result -> unit
val print_analysis : analysis_result -> unit

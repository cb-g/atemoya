(** IO for Macro Dashboard *)

(** Load macro data from JSON file *)
val load_macro_data : string -> Types.macro_snapshot

(** Print dashboard to stdout *)
val print_dashboard : Types.macro_snapshot -> Types.macro_environment -> Types.investment_implications -> unit

(** Save environment to JSON file *)
val save_environment : string -> Types.macro_snapshot -> Types.macro_environment -> Types.investment_implications -> unit

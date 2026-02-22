(** Macro Environment Classifier *)

(** Classify full macro environment from snapshot *)
val classify : Types.macro_snapshot -> Types.macro_environment

(** Generate investment implications from environment *)
val investment_implications : Types.macro_environment -> Types.investment_implications

(** I/O functions for REIT valuation *)

open Types

val property_sector_of_string : string -> property_sector
val string_of_property_sector : property_sector -> string
val market_data_of_json : Yojson.Basic.t -> market_data
val financial_data_of_json : Yojson.Basic.t -> financial_data
val load_reit_data : string -> (market_data * financial_data)
val load_config : string -> (float * float)
val valuation_method_to_json : valuation_method -> Yojson.Basic.t
val string_of_signal : investment_signal -> string
val result_to_json : valuation_result -> Yojson.Basic.t
val save_result : string -> valuation_result -> unit
val save_result_with_income : string -> valuation_result -> Income.income_metrics option -> unit
val print_summary : valuation_result -> unit
val print_income_metrics : Income.income_metrics -> unit
val income_metrics_to_json : Income.income_metrics -> Yojson.Basic.t

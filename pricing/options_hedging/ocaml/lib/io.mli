(* I/O Operations - CSV and JSON *)

(* Read option chain CSV from yfinance data *)
val read_option_chain : filename:string -> Types.vol_point array

(* Read underlying data CSV *)
val read_underlying_data : filename:string -> Types.underlying_data

(* Read calibrated volatility surface (JSON) *)
val read_vol_surface : filename:string -> Types.vol_surface

(* Write volatility surface to JSON *)
val write_vol_surface : Types.vol_surface -> filename:string -> unit

(* Write Pareto frontier to CSV *)
val write_pareto_csv : filename:string -> frontier:Types.pareto_point array -> unit

(* Write hedge strategy details to CSV *)
val write_strategy_csv : filename:string -> strategy:Types.hedge_strategy -> unit

(* Write Greeks summary for multiple strategies *)
val write_greeks_csv : filename:string -> strategies:Types.hedge_strategy list -> unit

(* Write optimization result to JSON *)
val write_optimization_result : filename:string -> result:Types.optimization_result -> unit

(* Parse option type from string *)
val parse_option_type : string -> Types.option_type

(* Parse exercise style from string *)
val parse_exercise_style : string -> Types.exercise_style

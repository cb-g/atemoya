(** Dividend Discount Model (DDM) valuations *)

open Types

val gordon_growth_model : float -> float -> float -> float option
val two_stage_ddm : float -> float -> float -> float -> int -> float option
val h_model : float -> float -> float -> float -> float -> float option
val yield_based_value : float -> float -> float option
val calculate_ddm_valuation : dividend_data -> ddm_params -> ddm_valuation
val estimate_required_return : float -> float -> float -> float
val default_params : ?required_return:float -> ?terminal_growth:float -> ?high_growth_years:int -> ?historical_yield:float -> unit -> ddm_params
val sensitivity_discount_rates : dividend_data -> float list -> float -> (float * float option) list
val sensitivity_growth_rates : dividend_data -> float -> float list -> (float * float option) list

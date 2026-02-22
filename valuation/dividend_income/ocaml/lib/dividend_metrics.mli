(** Dividend metrics calculations *)

open Types

val classify_yield : float -> yield_tier
val assess_payout : float -> payout_assessment
val assess_coverage : float -> string
val calculate_metrics : dividend_data -> dividend_metrics
val calculate_growth_metrics : dividend_data -> growth_metrics
val project_dividends : float -> float -> int -> float list
val yield_on_cost : float -> float -> float -> int -> float
val is_yield_trap : dividend_data -> bool * string list

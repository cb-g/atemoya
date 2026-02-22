(** NAV (Net Asset Value) calculation for REIT valuation *)

open Types

val default_cap_rate : property_sector -> float
val property_value_from_noi : noi:float -> cap_rate:float -> float
val implied_cap_rate : noi:float -> property_value:float -> float
val calculate_nav : financial:financial_data -> market:market_data -> cap_rate:float -> nav_components
val calculate_nav_default : financial:financial_data -> market:market_data -> nav_components
val nav_implied_value : nav_per_share:float -> target_premium:float -> float
val quality_adjusted_premium : quality:quality_metrics -> float
val calculate_cap_rate_assumptions : financial:financial_data -> market:market_data -> risk_free_rate:float -> cap_rate_assumptions
val nav_sensitivity : financial:financial_data -> market:market_data -> cap_rates:float list -> (float * float) list

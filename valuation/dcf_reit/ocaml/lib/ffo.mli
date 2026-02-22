(** FFO and AFFO calculations for REIT valuation *)

open Types

val calculate_ffo : financial:financial_data -> float
val calculate_affo : financial:financial_data -> float
val calculate_ffo_metrics : financial:financial_data -> market:market_data -> ffo_metrics
val price_to_ffo : price:float -> ffo_per_share:float -> float
val price_to_affo : price:float -> affo_per_share:float -> float
val implied_value_from_p_ffo : ffo_per_share:float -> sector_p_ffo:float -> float
val implied_value_from_p_affo : affo_per_share:float -> sector_p_affo:float -> float
val dividend_safety_score : ffo_metrics:ffo_metrics -> float
val implied_ffo_growth : price:float -> ffo_per_share:float -> cost_of_equity:float -> float

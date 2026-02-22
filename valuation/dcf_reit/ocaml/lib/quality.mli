(** Quality metrics for REIT assessment *)

open Types

val score_occupancy : occupancy_rate:float -> float
val score_lease_quality : walt:float -> lease_exp_1yr:float -> float
val score_balance_sheet : financial:financial_data -> market:market_data -> float
val score_growth : same_store_noi_growth:float -> float
val calculate_quality : financial:financial_data -> market:market_data -> ffo:ffo_metrics -> quality_metrics

type quality_tier = Premium | Quality | Average | BelowAverage | Poor
val pp_quality_tier : Format.formatter -> quality_tier -> unit
val show_quality_tier : quality_tier -> string

val classify_quality : quality:quality_metrics -> quality_tier
val quality_multiple_adjustment : quality:quality_metrics -> float

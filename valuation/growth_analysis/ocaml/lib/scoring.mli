(** Growth scoring and signal generation *)

open Types

val score_revenue_growth : float -> float
val score_earnings_growth : float -> float
val score_margins : float -> float -> float -> float
val score_efficiency : float -> float -> float
val score_quality : float -> float -> float
val score_to_grade : float -> string
val calculate_growth_score : growth_data -> growth_metrics -> margin_analysis -> growth_score
val determine_signal : growth_metrics -> margin_analysis -> growth_score -> growth_signal
val analyze : growth_data -> growth_result
val compare : growth_result list -> growth_result list

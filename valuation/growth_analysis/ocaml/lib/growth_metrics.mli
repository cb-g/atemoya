(** Growth metrics calculations *)

open Types

val classify_growth : float -> growth_tier
val classify_rule_of_40 : float -> rule_of_40_tier
val determine_margin_trajectory : growth_data -> margin_trajectory
val calculate_operating_leverage : growth_data -> float
val calculate_peg : float -> float -> float option
val calculate_ev_rev_per_growth : float -> float -> float
val calculate_implied_growth : float -> float option
val calculate_analyst_upside : float -> float -> float option
val calculate_growth_metrics : growth_data -> growth_metrics
val calculate_margin_analysis : growth_data -> margin_analysis
val calculate_growth_valuation : growth_data -> growth_valuation

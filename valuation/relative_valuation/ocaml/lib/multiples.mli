(** Valuation multiples calculations and statistics *)

open Types

val calculate_stats : float list -> peer_stats option
val get_multiple : string -> company_data -> float
val get_metric_for_multiple : string -> company_data -> float
val calculate_implied_price : string -> company_data -> float -> float option
val calculate_premium : float -> float -> float
val calculate_percentile : float -> peer_stats -> float
val compare_multiple : string -> company_data -> company_data list -> multiple_comparison option
val all_multiples : string list
val compare_all_multiples : company_data -> company_data list -> multiple_comparison list
val calculate_implied_valuations : company_data -> multiple_comparison list -> implied_valuation list
val average_implied_price : implied_valuation list -> float option

(** Relative valuation scoring and signal generation *)

open Types

val calculate_relative_score : multiple_comparison list -> float
val determine_assessment : float -> relative_assessment
val determine_signal : company_data -> float -> relative_signal
val calculate_fair_premium : company_data -> float -> float -> float
val generate_summary : company_data -> multiple_comparison list -> float option -> string list
val analyze : peer_data -> relative_result

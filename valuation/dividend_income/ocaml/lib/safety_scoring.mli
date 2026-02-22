(** Dividend safety scoring *)

open Types

val score_payout_ratio : float -> float
val score_fcf_coverage : float -> float
val score_dividend_streak : int -> float
val score_balance_sheet : float -> float -> float
val score_stability : float -> float -> float
val score_to_grade : float -> string
val calculate_safety_score : dividend_data -> safety_score
val determine_signal : dividend_data -> safety_score -> ddm_valuation -> income_signal
val generate_recommendation : dividend_data -> safety_score -> income_signal -> string list

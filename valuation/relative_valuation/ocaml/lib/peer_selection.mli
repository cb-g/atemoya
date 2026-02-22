(** Peer selection and similarity scoring *)

open Types

val score_industry : company_data -> company_data -> float
val score_size : company_data -> company_data -> float
val score_growth : company_data -> company_data -> float
val score_profitability : company_data -> company_data -> float
val calculate_similarity : company_data -> company_data -> similarity_score
val score_peers : company_data -> company_data list -> similarity_score list
val filter_by_similarity : float -> similarity_score list -> similarity_score list
val top_peers : int -> similarity_score list -> similarity_score list
val average_similarity : similarity_score list -> float
val classify_peer_quality : float -> string

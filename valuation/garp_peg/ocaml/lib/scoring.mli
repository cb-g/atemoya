(** GARP scoring system *)

(** Calculate PEG score (0-30 points) *)
val score_peg : float -> float

(** Calculate growth score (0-25 points) *)
val score_growth : float -> float

(** Calculate FCF conversion score (0-20 points) *)
val score_fcf_conversion : float -> float

(** Calculate balance sheet score (0-15 points) *)
val score_balance_sheet : float -> float

(** Calculate ROE score (0-10 points) *)
val score_roe : float -> float

(** Convert total score to letter grade *)
val score_to_grade : float -> string

(** Assess earnings quality based on FCF conversion *)
val assess_earnings_quality : float -> string

(** Assess balance sheet strength based on D/E ratio *)
val assess_balance_sheet : float -> string

(** Calculate quality metrics from raw data *)
val calculate_quality_metrics : Types.garp_data -> Types.quality_metrics

(** Calculate complete GARP score *)
val calculate_garp_score : Types.peg_metrics -> Types.garp_data -> Types.garp_score

(** Determine investment signal from score and PEG *)
val determine_signal : Types.garp_score -> Types.peg_metrics -> Types.garp_signal

(** Create complete GARP result from raw data *)
val analyze : Types.garp_data -> Types.garp_result

(** Compare multiple tickers and rank by GARP score *)
val compare : Types.garp_result list -> Types.garp_comparison

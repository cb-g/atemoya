(** Scoring and signal generation for normalized multiples *)

open Types

(** Calculate composite percentile from multiple comparisons *)
val composite_percentile : multiple_vs_benchmark list -> float

(** Apply quality adjustment to raw percentile *)
val quality_adjusted_percentile : float -> quality_adjustment -> float

(** Determine overall signal from percentile *)
val overall_signal : float -> multiple_signal

(** Calculate confidence score based on data quality and agreement *)
val confidence_score : multiple_vs_benchmark list -> float

(** Find the cheapest and most expensive multiples *)
val find_extremes : multiple_vs_benchmark list -> string * string

(** Generate summary insights *)
val generate_summary :
  company_multiples ->
  multiple_vs_benchmark list ->
  quality_adjustment ->
  float option ->
  string list

(** Analyze a single ticker against benchmark *)
val analyze_single :
  company_multiples ->
  benchmark_stats ->
  single_ticker_result

(** Analyze multiple tickers comparatively *)
val analyze_comparative :
  company_multiples list ->
  benchmark_stats ->
  comparative_result

(** Rank tickers by a specific multiple *)
val rank_by_multiple :
  (company_multiples -> normalized_multiple) ->
  company_multiples list ->
  ranking_entry list

(** Sector and industry benchmark operations *)

open Types

(** Calculate percentile rank of a value within a distribution defined by p25/median/p75 *)
val percentile_rank : float -> float -> float -> float -> float

(** Compare a single multiple to benchmark stats *)
val compare_to_benchmark :
  normalized_multiple ->
  benchmark_median:float ->
  benchmark_p25:float ->
  benchmark_p75:float ->
  current_price:float ->
  market_cap:float ->
  enterprise_value:float ->
  multiple_vs_benchmark

(** Calculate quality adjustment based on company metrics vs benchmark *)
val calculate_quality_adjustment :
  company_multiples ->
  benchmark_stats ->
  quality_adjustment

(** Get the benchmark values for a specific multiple name *)
val get_benchmark_for_multiple :
  string ->
  time_window ->
  benchmark_stats ->
  (float * float * float) option  (** median, p25, p75 *)

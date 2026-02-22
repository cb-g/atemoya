(** Mortgage REIT (mREIT) valuation module *)

open Types

val calculate_mreit_metrics :
  financial:financial_data -> market:market_data -> mreit_metrics

type mreit_benchmarks = {
  avg_price_to_book : float;
  avg_price_to_de : float;
  avg_nim : float;
  avg_leverage : float;
}

val default_mreit_benchmarks : mreit_benchmarks

val value_by_price_to_book :
  mreit:mreit_metrics -> quality_adj:float -> valuation_method

val value_by_price_to_de :
  mreit:mreit_metrics -> price:float -> quality_adj:float -> valuation_method

val score_mreit_balance_sheet : mreit:mreit_metrics -> float
val score_mreit_nim : mreit:mreit_metrics -> float
val score_mreit_book_stability : mreit:mreit_metrics -> float
val score_mreit_dividend_safety : mreit:mreit_metrics -> float

val calculate_mreit_quality : mreit:mreit_metrics -> quality_metrics

val blend_mreit_fair_value :
  p_bv_val:valuation_method ->
  p_de_val:valuation_method ->
  ddm_val:valuation_method ->
  float

(** Combined REIT valuation using multiple methodologies *)

open Types

val default_sector_benchmarks : property_sector -> sector_benchmarks
val value_by_p_ffo : ffo:ffo_metrics -> market:market_data -> quality:quality_metrics -> valuation_method
val value_by_p_affo : ffo:ffo_metrics -> market:market_data -> quality:quality_metrics -> valuation_method
val value_by_nav : nav:nav_components -> market:market_data -> quality:quality_metrics -> valuation_method
val value_by_ddm : market:market_data -> cost_of_capital:cost_of_capital -> growth_rate:float -> valuation_method
val implied_value_of : valuation_method -> float
val sector_weights : property_sector -> float * float * float * float
val blend_fair_value : sector:property_sector -> p_ffo_val:valuation_method -> p_affo_val:valuation_method -> nav_val:valuation_method -> ddm_val:valuation_method -> float
val determine_signal : price:float -> fair_value:float -> quality:quality_metrics -> investment_signal
val value_reit : financial:financial_data -> market:market_data -> risk_free_rate:float -> equity_risk_premium:float -> valuation_result

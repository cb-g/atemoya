(** Dividend Discount Model for REIT valuation *)

open Types

val gordon_growth : dividend:float -> cost_of_equity:float -> growth_rate:float -> float
val implied_growth : price:float -> dividend:float -> cost_of_equity:float -> float
val two_stage_ddm : dividend:float -> cost_of_equity:float -> high_growth:float -> terminal_growth:float -> high_growth_years:int -> float
val h_model : dividend:float -> cost_of_equity:float -> short_term_growth:float -> long_term_growth:float -> half_life:float -> float
val calculate_ddm_value : market:market_data -> params:ddm_params -> float
val calculate_cost_of_equity : risk_free_rate:float -> equity_risk_premium:float -> beta:float -> size_premium:float -> float
val sector_beta : property_sector -> float
val calculate_wacc : cost_of_equity:float -> cost_of_debt:float -> tax_rate:float -> debt_ratio:float -> float
val calculate_cost_of_capital : financial:financial_data -> market:market_data -> risk_free_rate:float -> equity_risk_premium:float -> cost_of_capital
val is_yield_sustainable : dividend_yield:float -> affo_yield:float -> bool
val project_dividends : initial_dividend:float -> growth_rate:float -> years:int -> float array

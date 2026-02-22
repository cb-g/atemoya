(** Core types for REIT valuation model *)

type ticker = string
type currency = string

type property_sector =
  | Retail
  | Office
  | Industrial
  | Residential
  | Healthcare
  | DataCenter
  | SelfStorage
  | Hotel
  | Specialty
  | Diversified
  | Mortgage

val pp_property_sector : Format.formatter -> property_sector -> unit
val show_property_sector : property_sector -> string

type reit_type =
  | EquityREIT
  | MortgageREIT
  | HybridREIT

val pp_reit_type : Format.formatter -> reit_type -> unit
val show_reit_type : reit_type -> string

type market_data = {
  ticker : ticker;
  price : float;
  shares_outstanding : float;
  market_cap : float;
  dividend_yield : float;
  dividend_per_share : float;
  currency : currency;
  sector : property_sector;
  reit_type : reit_type;
}

val pp_market_data : Format.formatter -> market_data -> unit
val show_market_data : market_data -> string

type financial_data = {
  revenue : float;
  net_income : float;
  depreciation : float;
  amortization : float;
  gains_on_sales : float;
  impairments : float;
  straight_line_rent_adj : float;
  stock_compensation : float;
  maintenance_capex : float;
  development_capex : float;
  total_debt : float;
  cash : float;
  total_assets : float;
  total_equity : float;
  book_value_per_share : float;
  noi : float;
  occupancy_rate : float;
  same_store_noi_growth : float;
  weighted_avg_lease_term : float;
  lease_expiration_1yr : float;
  interest_income : float;
  interest_expense : float;
  net_interest_income : float;
  earning_assets : float;
  distributable_earnings : float;
}

val pp_financial_data : Format.formatter -> financial_data -> unit
val show_financial_data : financial_data -> string

type cap_rate_assumptions = {
  sector : property_sector;
  implied_cap_rate : float;
  market_cap_rate : float;
  cap_rate_spread : float;
}

val pp_cap_rate_assumptions : Format.formatter -> cap_rate_assumptions -> unit
val show_cap_rate_assumptions : cap_rate_assumptions -> string

type ffo_metrics = {
  ffo : float;
  affo : float;
  ffo_per_share : float;
  affo_per_share : float;
  ffo_payout_ratio : float;
  affo_payout_ratio : float;
}

val pp_ffo_metrics : Format.formatter -> ffo_metrics -> unit
val show_ffo_metrics : ffo_metrics -> string

type mreit_metrics = {
  net_interest_income : float;
  nii_per_share : float;
  net_interest_margin : float;
  book_value_per_share : float;
  price_to_book : float;
  distributable_earnings : float;
  de_per_share : float;
  de_payout_ratio : float;
  leverage_ratio : float;
  interest_coverage : float;
}

val pp_mreit_metrics : Format.formatter -> mreit_metrics -> unit
val show_mreit_metrics : mreit_metrics -> string

type nav_components = {
  property_value : float;
  other_assets : float;
  total_debt : float;
  nav : float;
  nav_per_share : float;
  premium_discount : float;
}

val pp_nav_components : Format.formatter -> nav_components -> unit
val show_nav_components : nav_components -> string

type ddm_params = {
  cost_of_equity : float;
  dividend_growth_rate : float;
  terminal_growth_rate : float;
  projection_years : int;
}

val pp_ddm_params : Format.formatter -> ddm_params -> unit
val show_ddm_params : ddm_params -> string

type cost_of_capital = {
  risk_free_rate : float;
  equity_risk_premium : float;
  reit_beta : float;
  size_premium : float;
  cost_of_equity : float;
  cost_of_debt : float;
  tax_rate : float;
  debt_ratio : float;
  wacc : float;
}

val pp_cost_of_capital : Format.formatter -> cost_of_capital -> unit
val show_cost_of_capital : cost_of_capital -> string

type valuation_method =
  | PriceToFFO of {
      p_ffo : float;
      sector_avg : float;
      implied_value : float;
    }
  | PriceToAFFO of {
      p_affo : float;
      sector_avg : float;
      implied_value : float;
    }
  | NAVMethod of {
      nav_per_share : float;
      premium_discount : float;
      target_premium : float;
      implied_value : float;
    }
  | DividendDiscount of {
      intrinsic_value : float;
      dividend_yield : float;
      implied_growth : float;
    }
  | PriceToBook of {
      p_bv : float;
      sector_avg : float;
      implied_value : float;
    }
  | PriceToDE of {
      p_de : float;
      sector_avg : float;
      implied_value : float;
    }

val pp_valuation_method : Format.formatter -> valuation_method -> unit
val show_valuation_method : valuation_method -> string

type investment_signal =
  | StrongBuy
  | Buy
  | Hold
  | Sell
  | StrongSell
  | Caution

val pp_investment_signal : Format.formatter -> investment_signal -> unit
val show_investment_signal : investment_signal -> string

type quality_metrics = {
  occupancy_score : float;
  lease_quality_score : float;
  balance_sheet_score : float;
  growth_score : float;
  dividend_safety_score : float;
  overall_quality : float;
}

val pp_quality_metrics : Format.formatter -> quality_metrics -> unit
val show_quality_metrics : quality_metrics -> string

type valuation_result = {
  ticker : ticker;
  price : float;
  reit_type : reit_type;
  ffo_metrics : ffo_metrics;
  mreit_metrics : mreit_metrics option;
  nav : nav_components;
  cost_of_capital : cost_of_capital;
  p_ffo_valuation : valuation_method;
  p_affo_valuation : valuation_method;
  nav_valuation : valuation_method;
  ddm_valuation : valuation_method;
  p_bv_valuation : valuation_method option;
  p_de_valuation : valuation_method option;
  fair_value : float;
  upside_potential : float;
  quality : quality_metrics;
  signal : investment_signal;
}

val pp_valuation_result : Format.formatter -> valuation_result -> unit
val show_valuation_result : valuation_result -> string

type sector_benchmarks = {
  sector : property_sector;
  avg_cap_rate : float;
  avg_p_ffo : float;
  avg_p_affo : float;
  avg_nav_premium : float;
}

val pp_sector_benchmarks : Format.formatter -> sector_benchmarks -> unit
val show_sector_benchmarks : sector_benchmarks -> string

type config = {
  risk_free_rate : float;
  equity_risk_premium : float;
  sector_benchmarks : sector_benchmarks list;
  ddm_params : ddm_params;
}

val pp_config : Format.formatter -> config -> unit
val show_config : config -> string

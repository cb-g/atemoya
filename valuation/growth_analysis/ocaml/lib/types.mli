(** Types for growth investor analysis *)

type growth_data = {
  ticker : string;
  company_name : string;
  sector : string;
  industry : string;
  current_price : float;
  market_cap : float;
  enterprise_value : float;
  shares_outstanding : float;
  revenue : float;
  revenue_growth : float;
  revenue_growth_yoy : float;
  revenue_cagr_3y : float;
  revenue_per_share : float;
  trailing_eps : float;
  forward_eps : float;
  earnings_growth : float;
  eps_growth_fwd : float;
  gross_margin : float;
  operating_margin : float;
  ebitda_margin : float;
  profit_margin : float;
  fcf_margin : float;
  ebitda : float;
  free_cashflow : float;
  operating_cashflow : float;
  fcf_per_share : float;
  ev_revenue : float;
  ev_ebitda : float;
  trailing_pe : float;
  forward_pe : float;
  rule_of_40 : float;
  roe : float;
  roa : float;
  roic : float;
  beta : float;
  analyst_target_mean : float;
  analyst_target_high : float;
  analyst_target_low : float;
  analyst_recommendation : string;
  num_analysts : int;
}

type growth_tier =
  | Hypergrowth
  | HighGrowth
  | ModerateGrowth
  | SlowGrowth
  | NoGrowth
  | Declining

type rule_of_40_tier =
  | Excellent
  | Good
  | Moderate
  | Concerning

type margin_trajectory =
  | Expanding
  | Stable
  | Contracting

type growth_metrics = {
  revenue_growth_pct : float;
  revenue_cagr_3y_pct : float;
  earnings_growth_pct : float;
  growth_tier : growth_tier;
  rule_of_40 : float;
  rule_of_40_tier : rule_of_40_tier;
  ev_revenue_per_growth : float;
  peg_ratio : float option;
}

type margin_analysis = {
  gross_margin_pct : float;
  operating_margin_pct : float;
  fcf_margin_pct : float;
  margin_trajectory : margin_trajectory;
  operating_leverage : float;
}

type growth_valuation = {
  ev_revenue : float;
  ev_ebitda : float;
  forward_pe : float;
  implied_growth : float option;
  analyst_upside_pct : float option;
}

type growth_score = {
  total_score : float;
  grade : string;
  revenue_growth_score : float;
  earnings_growth_score : float;
  margin_score : float;
  efficiency_score : float;
  quality_score : float;
}

type growth_signal =
  | StrongGrowth
  | GrowthBuy
  | GrowthHold
  | GrowthCaution
  | NotGrowthStock

type growth_result = {
  ticker : string;
  company_name : string;
  sector : string;
  current_price : float;
  growth_metrics : growth_metrics;
  margin_analysis : margin_analysis;
  valuation : growth_valuation;
  score : growth_score;
  signal : growth_signal;
}

val string_of_growth_tier : growth_tier -> string
val string_of_rule_of_40_tier : rule_of_40_tier -> string
val string_of_margin_trajectory : margin_trajectory -> string
val string_of_growth_signal : growth_signal -> string

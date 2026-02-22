(** ETF Analysis Types *)

type derivatives_type =
  | Standard
  | CoveredCall
  | Buffer
  | Volatility
  | PutWrite
  | Leveraged

type nav_status =
  | Premium of float
  | Discount of float
  | AtNav

type liquidity_tier =
  | HighlyLiquid
  | Liquid
  | ModeratelyLiquid
  | Illiquid

type cost_tier =
  | UltraLowCost
  | LowCost
  | ModerateCost
  | HighCost
  | VeryHighCost

type tracking_quality =
  | Excellent
  | Good
  | Acceptable
  | Poor
  | VeryPoor

type size_tier =
  | Mega
  | Large
  | Medium
  | Small
  | Micro

type returns = {
  ytd : float;
  one_month : float;
  three_month : float;
  one_year : float;
  volatility_1y : float;
}

type tracking_metrics = {
  tracking_error_pct : float;
  tracking_difference_pct : float;
  correlation : float;
  beta : float;
}

type capture_ratios = {
  upside_capture_pct : float;
  downside_capture_pct : float;
}

type distribution_analysis = {
  total_12m : float;
  distribution_yield_pct : float;
  distribution_count_12m : int;
  frequency : string;
  avg_distribution : float;
  min_distribution : float;
  max_distribution : float;
  distribution_variability_pct : float;
}

type holding = {
  symbol : string;
  holding_name : string;
  weight : float;
}

type etf_data = {
  ticker : string;
  name : string;
  category : string;
  benchmark_ticker : string;
  derivatives_type : derivatives_type;
  current_price : float;
  nav : float;
  previous_close : float;
  fifty_two_week_high : float;
  fifty_two_week_low : float;
  expense_ratio : float;
  aum : float;
  avg_volume : float;
  bid_ask_spread : float;
  bid_ask_spread_pct : float;
  premium_discount : float;
  premium_discount_pct : float;
  distribution_yield : float;
  holdings_count : int;
  top_holdings : holding list;
  returns : returns option;
  tracking : tracking_metrics option;
  capture_ratios : capture_ratios option;
  distribution_analysis : distribution_analysis option;
}

type etf_score = {
  total_score : float;
  grade : string;
  cost_score : float;
  tracking_score : float;
  liquidity_score : float;
  size_score : float;
}

type etf_signal =
  | HighQuality
  | GoodQuality
  | Acceptable
  | UseCaution
  | Avoid

type covered_call_analysis = {
  distribution_yield_pct : float;
  upside_capture : float;
  downside_capture : float;
  yield_vs_benchmark : float;
  capture_efficiency : float;
}

type buffer_analysis = {
  buffer_level : float;
  cap_level : float;
  remaining_buffer : float;
  remaining_cap : float;
  days_to_outcome : int;
  buffer_status : string;
}

type volatility_analysis = {
  term_structure : string;
  roll_yield_monthly_pct : float;
  roll_yield_annual_pct : float;
  decay_warning : bool;
}

type derivatives_analysis =
  | CoveredCallAnalysis of covered_call_analysis
  | BufferAnalysis of buffer_analysis
  | VolatilityAnalysis of volatility_analysis
  | NoDerivatives

type etf_result = {
  data : etf_data;
  nav_status : nav_status;
  liquidity_tier : liquidity_tier;
  cost_tier : cost_tier;
  tracking_quality : tracking_quality option;
  size_tier : size_tier;
  score : etf_score;
  signal : etf_signal;
  derivatives_analysis : derivatives_analysis;
  recommendations : string list;
}

type etf_comparison = {
  results : etf_result list;
  best_cost : string;
  best_tracking : string;
  best_liquidity : string;
  best_overall : string;
}

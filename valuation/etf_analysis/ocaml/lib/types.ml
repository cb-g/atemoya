(** ETF Analysis Types *)

(** ETF derivatives strategy type *)
type derivatives_type =
  | Standard
  | CoveredCall
  | Buffer
  | Volatility
  | PutWrite
  | Leveraged

(** Premium/discount status *)
type nav_status =
  | Premium of float  (* positive % *)
  | Discount of float (* negative % *)
  | AtNav            (* within 0.1% *)

(** Liquidity tier *)
type liquidity_tier =
  | HighlyLiquid     (* spread < 0.02%, volume > $1B daily *)
  | Liquid           (* spread < 0.05%, volume > $100M *)
  | ModeratelyLiquid (* spread < 0.10%, volume > $10M *)
  | Illiquid         (* spread >= 0.10% or low volume *)

(** Cost tier *)
type cost_tier =
  | UltraLowCost    (* ER < 0.05% *)
  | LowCost         (* ER < 0.10% *)
  | ModerateCost    (* ER < 0.20% *)
  | HighCost        (* ER < 0.50% *)
  | VeryHighCost    (* ER >= 0.50% *)

(** Tracking quality *)
type tracking_quality =
  | Excellent  (* TE < 0.10% *)
  | Good       (* TE < 0.25% *)
  | Acceptable (* TE < 0.50% *)
  | Poor       (* TE < 1.00% *)
  | VeryPoor   (* TE >= 1.00% *)

(** Size tier based on AUM *)
type size_tier =
  | Mega       (* > $100B *)
  | Large      (* > $10B *)
  | Medium     (* > $1B *)
  | Small      (* > $100M *)
  | Micro      (* <= $100M *)

(** ETF returns data *)
type returns = {
  ytd : float;
  one_month : float;
  three_month : float;
  one_year : float;
  volatility_1y : float;
}

(** Tracking metrics vs benchmark *)
type tracking_metrics = {
  tracking_error_pct : float;
  tracking_difference_pct : float;
  correlation : float;
  beta : float;
}

(** Capture ratios *)
type capture_ratios = {
  upside_capture_pct : float;
  downside_capture_pct : float;
}

(** Distribution analysis for income ETFs *)
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

(** Individual holding in ETF *)
type holding = {
  symbol : string;
  holding_name : string;
  weight : float;
}

(** Core ETF data *)
type etf_data = {
  ticker : string;
  name : string;
  category : string;
  benchmark_ticker : string;
  derivatives_type : derivatives_type;

  (* Price data *)
  current_price : float;
  nav : float;
  previous_close : float;
  fifty_two_week_high : float;
  fifty_two_week_low : float;

  (* Cost metrics *)
  expense_ratio : float;

  (* Size and liquidity *)
  aum : float;
  avg_volume : float;
  bid_ask_spread : float;
  bid_ask_spread_pct : float;

  (* Premium/discount *)
  premium_discount : float;
  premium_discount_pct : float;

  (* Yield *)
  distribution_yield : float;

  (* Holdings *)
  holdings_count : int;
  top_holdings : holding list;

  (* Performance *)
  returns : returns option;
  tracking : tracking_metrics option;
  capture_ratios : capture_ratios option;
  distribution_analysis : distribution_analysis option;
}

(** ETF quality score breakdown *)
type etf_score = {
  total_score : float;
  grade : string;
  cost_score : float;
  tracking_score : float;
  liquidity_score : float;
  size_score : float;
}

(** Signal for ETF quality *)
type etf_signal =
  | HighQuality
  | GoodQuality
  | Acceptable
  | UseCaution
  | Avoid

(** Covered call specific analysis *)
type covered_call_analysis = {
  distribution_yield_pct : float;
  upside_capture : float;
  downside_capture : float;
  yield_vs_benchmark : float;  (* yield / benchmark dividend yield *)
  capture_efficiency : float;  (* upside_capture - downside_capture spread *)
}

(** Buffer ETF specific analysis *)
type buffer_analysis = {
  buffer_level : float;
  cap_level : float;
  remaining_buffer : float;
  remaining_cap : float;
  days_to_outcome : int;
  buffer_status : string;
}

(** Volatility ETF specific analysis *)
type volatility_analysis = {
  term_structure : string;      (* "contango" or "backwardation" *)
  roll_yield_monthly_pct : float;
  roll_yield_annual_pct : float;
  decay_warning : bool;
}

(** Derivatives-specific result *)
type derivatives_analysis =
  | CoveredCallAnalysis of covered_call_analysis
  | BufferAnalysis of buffer_analysis
  | VolatilityAnalysis of volatility_analysis
  | NoDerivatives

(** Complete ETF analysis result *)
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

(** ETF comparison result *)
type etf_comparison = {
  results : etf_result list;
  best_cost : string;
  best_tracking : string;
  best_liquidity : string;
  best_overall : string;
}

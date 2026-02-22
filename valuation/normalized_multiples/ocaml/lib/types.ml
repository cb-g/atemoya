(** Normalized Multiples Types - Implementation *)

type time_window =
  | TTM
  | NTM
  | FY0
  | FY1
  | FY2

let string_of_time_window = function
  | TTM -> "TTM"
  | NTM -> "NTM"
  | FY0 -> "FY0"
  | FY1 -> "FY1"
  | FY2 -> "FY2"

let time_window_of_string = function
  | "TTM" -> Some TTM
  | "NTM" -> Some NTM
  | "FY0" -> Some FY0
  | "FY1" -> Some FY1
  | "FY2" -> Some FY2
  | _ -> None

type normalized_multiple = {
  name : string;
  time_window : time_window;
  value : float;
  is_valid : bool;
  underlying_metric : float;
}

type multiple_category =
  | PriceMultiple
  | EVMultiple

let category_of_multiple name =
  if String.length name >= 2 && String.sub name 0 2 = "EV" then EVMultiple
  else PriceMultiple

type company_multiples = {
  ticker : string;
  company_name : string;
  sector : string;
  industry : string;
  current_price : float;
  market_cap : float;
  enterprise_value : float;
  shares_outstanding : float;

  pe_ttm : normalized_multiple;
  pe_ntm : normalized_multiple;
  ps_ttm : normalized_multiple;
  pb_ttm : normalized_multiple;
  p_fcf_ttm : normalized_multiple;
  peg_ratio : normalized_multiple;

  ev_ebitda_ttm : normalized_multiple;
  ev_ebit_ttm : normalized_multiple;
  ev_sales_ttm : normalized_multiple;
  ev_fcf_ttm : normalized_multiple;

  revenue_growth_ttm : float;
  eps_growth_ttm : float;
  eps_growth_ntm : float;

  gross_margin : float;
  operating_margin : float;
  ebitda_margin : float;

  roe : float;
  roic : float;
}

type benchmark_stats = {
  sector : string;
  industry : string option;
  sample_size : int;

  pe_ttm_median : float;
  pe_ttm_p25 : float;
  pe_ttm_p75 : float;
  pe_ntm_median : float;
  pe_ntm_p25 : float;
  pe_ntm_p75 : float;

  ps_median : float;
  ps_p25 : float;
  ps_p75 : float;
  pb_median : float;
  pb_p25 : float;
  pb_p75 : float;
  p_fcf_median : float;
  p_fcf_p25 : float;
  p_fcf_p75 : float;
  peg_median : float;
  peg_p25 : float;
  peg_p75 : float;

  ev_ebitda_median : float;
  ev_ebitda_p25 : float;
  ev_ebitda_p75 : float;
  ev_ebit_median : float;
  ev_sales_median : float;
  ev_fcf_median : float;

  revenue_growth_median : float;
  ebitda_margin_median : float;
  roe_median : float;
}

type multiple_vs_benchmark = {
  multiple : normalized_multiple;
  benchmark_median : float;
  benchmark_p25 : float;
  benchmark_p75 : float;
  premium_discount_pct : float;
  percentile_rank : float;
  implied_price : float option;
}

type multiple_signal =
  | DeepValue
  | Undervalued
  | FairValue
  | Overvalued
  | Expensive
  | NotMeaningful

let string_of_signal = function
  | DeepValue -> "Deep Value"
  | Undervalued -> "Undervalued"
  | FairValue -> "Fair Value"
  | Overvalued -> "Overvalued"
  | Expensive -> "Expensive"
  | NotMeaningful -> "N/A"

let signal_of_percentile pct is_valid =
  if not is_valid then NotMeaningful
  else if pct < 25.0 then DeepValue
  else if pct < 40.0 then Undervalued
  else if pct < 60.0 then FairValue
  else if pct < 75.0 then Overvalued
  else Expensive

type quality_adjustment = {
  growth_premium_pct : float;
  margin_premium_pct : float;
  return_premium_pct : float;
  total_fair_premium_pct : float;
}

type single_ticker_result = {
  ticker : string;
  company_name : string;
  sector : string;
  industry : string;
  current_price : float;
  analysis_date : string;

  price_multiples : multiple_vs_benchmark list;
  ev_multiples : multiple_vs_benchmark list;

  benchmark : benchmark_stats;
  quality_adj : quality_adjustment;

  composite_percentile : float;
  quality_adjusted_percentile : float;

  implied_prices : (string * float) list;
  average_implied_price : float option;
  median_implied_price : float option;

  overall_signal : multiple_signal;
  confidence : float;

  cheapest_multiple : string;
  most_expensive_multiple : string;
  summary : string list;
}

type ranking_entry = {
  ticker : string;
  value : float;
  signal : multiple_signal;
}

type comparative_result = {
  tickers : string list;
  sector : string;
  analysis_date : string;

  pe_ttm_ranking : ranking_entry list;
  pe_ntm_ranking : ranking_entry list;
  ev_ebitda_ranking : ranking_entry list;
  peg_ranking : ranking_entry list;

  value_score_ranking : (string * float) list;
  quality_adjusted_ranking : (string * float) list;

  best_value : string option;
  best_quality_adjusted : string option;
  best_peg : string option;

  individual_results : single_ticker_result list;
}

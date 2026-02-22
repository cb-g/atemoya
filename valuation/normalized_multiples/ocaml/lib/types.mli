(** Normalized Multiples Types - Explicit Time Windows for All Multiples *)

(** Time window for multiples - eliminates confusion about what period *)
type time_window =
  | TTM   (** Trailing Twelve Months - historical/actual *)
  | NTM   (** Next Twelve Months - forward/consensus estimates *)
  | FY0   (** Current Fiscal Year estimate *)
  | FY1   (** Next Fiscal Year estimate *)
  | FY2   (** Two Fiscal Years forward estimate *)

val string_of_time_window : time_window -> string
val time_window_of_string : string -> time_window option

(** A single valuation multiple with explicit time context *)
type normalized_multiple = {
  name : string;              (** e.g., "P/E", "EV/EBITDA" *)
  time_window : time_window;
  value : float;
  is_valid : bool;            (** False if denominator was negative/zero *)
  underlying_metric : float;  (** The denominator (EPS, EBITDA, etc.) *)
}

(** Multiple category for grouping *)
type multiple_category =
  | PriceMultiple   (** P/E, P/S, P/B, P/FCF, PEG *)
  | EVMultiple      (** EV/EBITDA, EV/EBIT, EV/Sales, EV/FCF *)

val category_of_multiple : string -> multiple_category

(** Company multiples data from Python fetcher *)
type company_multiples = {
  ticker : string;
  company_name : string;
  sector : string;
  industry : string;
  current_price : float;
  market_cap : float;
  enterprise_value : float;
  shares_outstanding : float;

  (* Price multiples *)
  pe_ttm : normalized_multiple;
  pe_ntm : normalized_multiple;
  ps_ttm : normalized_multiple;
  pb_ttm : normalized_multiple;
  p_fcf_ttm : normalized_multiple;
  peg_ratio : normalized_multiple;

  (* EV multiples *)
  ev_ebitda_ttm : normalized_multiple;
  ev_ebit_ttm : normalized_multiple;
  ev_sales_ttm : normalized_multiple;
  ev_fcf_ttm : normalized_multiple;

  (* Growth rates *)
  revenue_growth_ttm : float;
  eps_growth_ttm : float;
  eps_growth_ntm : float;

  (* Margins *)
  gross_margin : float;
  operating_margin : float;
  ebitda_margin : float;

  (* Returns *)
  roe : float;
  roic : float;
}

(** Sector/Industry benchmark statistics *)
type benchmark_stats = {
  sector : string;
  industry : string option;
  sample_size : int;

  (* P/E benchmarks *)
  pe_ttm_median : float;
  pe_ttm_p25 : float;
  pe_ttm_p75 : float;
  pe_ntm_median : float;
  pe_ntm_p25 : float;
  pe_ntm_p75 : float;

  (* Other price multiples *)
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

  (* EV multiples *)
  ev_ebitda_median : float;
  ev_ebitda_p25 : float;
  ev_ebitda_p75 : float;
  ev_ebit_median : float;
  ev_sales_median : float;
  ev_fcf_median : float;

  (* Quality benchmarks *)
  revenue_growth_median : float;
  ebitda_margin_median : float;
  roe_median : float;
}

(** Comparison result for a single multiple vs benchmark *)
type multiple_vs_benchmark = {
  multiple : normalized_multiple;
  benchmark_median : float;
  benchmark_p25 : float;
  benchmark_p75 : float;
  premium_discount_pct : float;  (** Positive = premium, negative = discount *)
  percentile_rank : float;       (** 0-100 *)
  implied_price : float option;
}

(** Valuation signal per multiple *)
type multiple_signal =
  | DeepValue       (** <25th percentile *)
  | Undervalued     (** 25th-40th percentile *)
  | FairValue       (** 40th-60th percentile *)
  | Overvalued      (** 60th-75th percentile *)
  | Expensive       (** >75th percentile *)
  | NotMeaningful   (** Invalid or negative multiple *)

val string_of_signal : multiple_signal -> string
val signal_of_percentile : float -> bool -> multiple_signal

(** Quality-adjusted fair value assessment *)
type quality_adjustment = {
  growth_premium_pct : float;
  margin_premium_pct : float;
  return_premium_pct : float;
  total_fair_premium_pct : float;
}

(** Single ticker analysis result *)
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

(** Ranking entry for comparative analysis *)
type ranking_entry = {
  ticker : string;
  value : float;
  signal : multiple_signal;
}

(** Comparative analysis result *)
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

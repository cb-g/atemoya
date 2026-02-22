(** Types for relative valuation / comparable company analysis *)

type company_data = {
  ticker : string;
  company_name : string;
  sector : string;
  industry : string;
  current_price : float;
  market_cap : float;
  enterprise_value : float;
  shares_outstanding : float;
  trailing_eps : float;
  forward_eps : float;
  trailing_pe : float;
  forward_pe : float;
  book_value : float;
  pb_ratio : float;
  revenue : float;
  revenue_per_share : float;
  ps_ratio : float;
  free_cashflow : float;
  fcf_per_share : float;
  p_fcf : float;
  ebitda : float;
  operating_income : float;
  ev_ebitda : float;
  ev_ebit : float;
  ev_revenue : float;
  revenue_growth : float;
  earnings_growth : float;
  gross_margin : float;
  operating_margin : float;
  ebitda_margin : float;
  profit_margin : float;
  roe : float;
  roa : float;
  roic : float;
  beta : float;
  dividend_yield : float;
}

type peer_data = {
  target : company_data;
  peers : company_data list;
  peer_count : int;
}

type multiples = {
  pe_trailing : float;
  pe_forward : float;
  pb : float;
  ps : float;
  p_fcf : float;
  ev_ebitda : float;
  ev_ebit : float;
  ev_revenue : float;
}

type peer_stats = {
  median : float;
  mean : float;
  min : float;
  max : float;
  std_dev : float;
}

type multiple_comparison = {
  multiple_name : string;
  target_value : float;
  peer_stats : peer_stats;
  premium_pct : float;
  percentile : float;
  implied_value : float option;
}

type similarity_score = {
  ticker : string;
  total_score : float;
  industry_score : float;
  size_score : float;
  growth_score : float;
  profitability_score : float;
}

type implied_valuation = {
  method_name : string;
  peer_multiple : float;
  target_metric : float;
  implied_price : float;
  upside_downside_pct : float;
}

type relative_assessment =
  | VeryUndervalued
  | Undervalued
  | FairlyValued
  | Overvalued
  | VeryOvervalued

type relative_signal =
  | StrongBuy
  | Buy
  | Hold
  | Caution
  | Sell

type relative_result = {
  ticker : string;
  company_name : string;
  sector : string;
  current_price : float;
  peer_count : int;
  peer_similarities : similarity_score list;
  multiple_comparisons : multiple_comparison list;
  implied_valuations : implied_valuation list;
  average_implied_price : float option;
  relative_score : float;
  assessment : relative_assessment;
  signal : relative_signal;
}

val string_of_relative_assessment : relative_assessment -> string
val string_of_relative_signal : relative_signal -> string

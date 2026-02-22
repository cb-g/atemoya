(** Core types for GARP/PEG valuation model *)

type ticker = string

(** Raw data fetched from yfinance *)
type garp_data = {
  ticker : ticker;
  price : float;
  market_cap : float;
  shares_outstanding : float;
  eps_trailing : float;
  eps_forward : float;
  pe_trailing : float;
  pe_forward : float;
  earnings_growth : float;
  earnings_quarterly_growth : float;
  revenue_growth : float;
  eps_growth_1y : float;
  growth_estimate_5y : float;
  peg_ratio_yf : float;
  free_cash_flow : float;
  operating_cash_flow : float;
  net_income : float;
  total_revenue : float;
  total_debt : float;
  total_equity : float;
  total_cash : float;
  debt_to_equity : float;
  roe : float;
  roa : float;
  fcf_conversion : float;
  fcf_per_share : float;
  book_value_per_share : float;
  net_cash_per_share : float;
  dividend_yield : float;
  dividend_rate : float;
  sector : string;
  industry : string;
}

val pp_garp_data : Format.formatter -> garp_data -> unit
val show_garp_data : garp_data -> string

(** PEG ratio variants *)
type peg_type =
  | PEG_Trailing
  | PEG_Forward
  | PEGY

val pp_peg_type : Format.formatter -> peg_type -> unit
val show_peg_type : peg_type -> string

(** Calculated PEG metrics *)
type peg_metrics = {
  pe_trailing : float;
  pe_forward : float;
  growth_rate_used : float;
  growth_source : string;
  peg_trailing : float;
  peg_forward : float;
  pegy : float;
  peg_assessment : string;
}

val pp_peg_metrics : Format.formatter -> peg_metrics -> unit
val show_peg_metrics : peg_metrics -> string

(** Quality metrics for GARP scoring *)
type quality_metrics = {
  fcf_conversion : float;
  debt_to_equity : float;
  roe : float;
  roa : float;
  earnings_quality : string;
  balance_sheet_strength : string;
}

val pp_quality_metrics : Format.formatter -> quality_metrics -> unit
val show_quality_metrics : quality_metrics -> string

(** GARP score breakdown *)
type garp_score = {
  total_score : float;
  grade : string;
  peg_score : float;
  growth_score : float;
  quality_score : float;
  balance_sheet_score : float;
  roe_score : float;
}

val pp_garp_score : Format.formatter -> garp_score -> unit
val show_garp_score : garp_score -> string

(** Investment signal for GARP *)
type garp_signal =
  | StrongBuy
  | Buy
  | Hold
  | Caution
  | Avoid
  | NotApplicable

val pp_garp_signal : Format.formatter -> garp_signal -> unit
val show_garp_signal : garp_signal -> string

(** Complete GARP analysis result *)
type garp_result = {
  ticker : ticker;
  price : float;
  peg_metrics : peg_metrics;
  quality_metrics : quality_metrics;
  garp_score : garp_score;
  signal : garp_signal;
  implied_fair_pe : float option;
  implied_fair_price : float option;
  upside_downside : float option;
  raw_data : garp_data;
}

val pp_garp_result : Format.formatter -> garp_result -> unit
val show_garp_result : garp_result -> string

(** Multi-ticker comparison result *)
type garp_comparison = {
  results : garp_result list;
  best_peg : ticker option;
  best_score : ticker option;
  ranking : (ticker * float) list;
}

val pp_garp_comparison : Format.formatter -> garp_comparison -> unit
val show_garp_comparison : garp_comparison -> string

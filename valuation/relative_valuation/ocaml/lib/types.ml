(** Types for relative valuation / comparable company analysis *)

(** Company data from Python fetcher *)
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

(** Peer data bundle *)
type peer_data = {
  target : company_data;
  peers : company_data list;
  peer_count : int;
}

(** Key valuation multiples *)
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

(** Peer statistics (median, mean, range) *)
type peer_stats = {
  median : float;
  mean : float;
  min : float;
  max : float;
  std_dev : float;
}

(** Multiple comparison result *)
type multiple_comparison = {
  multiple_name : string;
  target_value : float;
  peer_stats : peer_stats;
  premium_pct : float;         (** Premium/discount vs peer median *)
  percentile : float;          (** Where target falls in peer range *)
  implied_value : float option; (** Implied price at peer median *)
}

(** Peer similarity score breakdown *)
type similarity_score = {
  ticker : string;
  total_score : float;           (** 0-100 *)
  industry_score : float;        (** 0-30 *)
  size_score : float;            (** 0-25 *)
  growth_score : float;          (** 0-25 *)
  profitability_score : float;   (** 0-20 *)
}

(** Implied valuation from a multiple *)
type implied_valuation = {
  method_name : string;
  peer_multiple : float;
  target_metric : float;
  implied_price : float;
  upside_downside_pct : float;
}

(** Relative valuation assessment *)
type relative_assessment =
  | VeryUndervalued    (** Trading at significant discount *)
  | Undervalued        (** Below peer median *)
  | FairlyValued       (** Near peer median *)
  | Overvalued         (** Above peer median *)
  | VeryOvervalued     (** Significant premium *)

(** Relative valuation signal *)
type relative_signal =
  | StrongBuy    (** Undervalued vs peers with good fundamentals *)
  | Buy          (** Modest undervaluation *)
  | Hold         (** Fairly valued *)
  | Caution      (** Premium vs peers, needs justification *)
  | Sell         (** Significant overvaluation *)

(** Complete relative valuation result *)
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
  relative_score : float;      (** 0-100, higher = more undervalued *)
  assessment : relative_assessment;
  signal : relative_signal;
}

(** String conversion functions *)
let string_of_relative_assessment = function
  | VeryUndervalued -> "Very Undervalued"
  | Undervalued -> "Undervalued"
  | FairlyValued -> "Fairly Valued"
  | Overvalued -> "Overvalued"
  | VeryOvervalued -> "Very Overvalued"

let string_of_relative_signal = function
  | StrongBuy -> "Strong Buy"
  | Buy -> "Buy"
  | Hold -> "Hold"
  | Caution -> "Caution"
  | Sell -> "Sell"

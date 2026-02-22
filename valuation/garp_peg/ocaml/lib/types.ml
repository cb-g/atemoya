(** Core types for GARP/PEG valuation model *)

type ticker = string [@@deriving show]

(** Raw data fetched from yfinance *)
type garp_data = {
  ticker : ticker;
  price : float;
  market_cap : float;
  shares_outstanding : float;

  (* EPS data *)
  eps_trailing : float;
  eps_forward : float;

  (* P/E ratios *)
  pe_trailing : float;
  pe_forward : float;

  (* Growth rates - as decimals (0.15 = 15%) *)
  earnings_growth : float;
  earnings_quarterly_growth : float;
  revenue_growth : float;
  eps_growth_1y : float;
  growth_estimate_5y : float;

  (* PEG from yfinance for comparison *)
  peg_ratio_yf : float;

  (* Quality metrics *)
  free_cash_flow : float;
  operating_cash_flow : float;
  net_income : float;
  total_revenue : float;

  (* Balance sheet *)
  total_debt : float;
  total_equity : float;
  total_cash : float;
  debt_to_equity : float;

  (* Returns - as decimals *)
  roe : float;
  roa : float;

  (* Derived metrics *)
  fcf_conversion : float;
  fcf_per_share : float;
  book_value_per_share : float;
  net_cash_per_share : float;

  (* Dividend for PEGY *)
  dividend_yield : float;
  dividend_rate : float;

  (* Classification *)
  sector : string;
  industry : string;
}
[@@deriving show]

(** PEG ratio variants *)
type peg_type =
  | PEG_Trailing    (** P/E trailing / earnings growth *)
  | PEG_Forward     (** P/E forward / earnings growth *)
  | PEGY            (** P/E / (growth + dividend yield) *)
[@@deriving show]

(** Calculated PEG metrics *)
type peg_metrics = {
  pe_trailing : float;
  pe_forward : float;
  growth_rate_used : float;      (** Growth rate used for PEG calculation *)
  growth_source : string;        (** Which growth estimate was used *)

  peg_trailing : float;          (** Trailing P/E / Growth *)
  peg_forward : float;           (** Forward P/E / Growth *)
  pegy : float;                  (** P/E / (Growth + Dividend Yield) *)

  (* Interpretation thresholds *)
  peg_assessment : string;       (** "Undervalued", "Fair", "Expensive" etc *)
}
[@@deriving show]

(** Quality metrics for GARP scoring *)
type quality_metrics = {
  fcf_conversion : float;        (** FCF / Net Income *)
  debt_to_equity : float;
  roe : float;
  roa : float;
  earnings_quality : string;     (** "High", "Medium", "Low" *)
  balance_sheet_strength : string;
}
[@@deriving show]

(** GARP score breakdown *)
type garp_score = {
  total_score : float;           (** 0-100 *)
  grade : string;                (** A, B, C, D, F *)

  (* Component scores *)
  peg_score : float;             (** 0-30 based on PEG ratio *)
  growth_score : float;          (** 0-25 based on growth rate *)
  quality_score : float;         (** 0-20 based on FCF conversion *)
  balance_sheet_score : float;   (** 0-15 based on D/E ratio *)
  roe_score : float;             (** 0-10 based on ROE *)
}
[@@deriving show]

(** Investment signal for GARP *)
type garp_signal =
  | StrongBuy      (** PEG < 0.5, high quality *)
  | Buy            (** PEG 0.5-1.0, good quality *)
  | Hold           (** PEG 1.0-1.5 or mixed signals *)
  | Caution        (** PEG 1.5-2.0 or quality concerns *)
  | Avoid          (** PEG > 2.0 or poor quality *)
  | NotApplicable  (** Negative earnings, can't calculate PEG *)
[@@deriving show]

(** Complete GARP analysis result *)
type garp_result = {
  ticker : ticker;
  price : float;

  (* PEG analysis *)
  peg_metrics : peg_metrics;

  (* Quality analysis *)
  quality_metrics : quality_metrics;

  (* Overall scoring *)
  garp_score : garp_score;
  signal : garp_signal;

  (* Valuation context *)
  implied_fair_pe : float option;    (** Fair P/E based on growth *)
  implied_fair_price : float option; (** Price at fair P/E *)
  upside_downside : float option;    (** % upside/downside to fair price *)

  (* Raw data for reference *)
  raw_data : garp_data;
}
[@@deriving show]

(** Multi-ticker comparison result *)
type garp_comparison = {
  results : garp_result list;
  best_peg : ticker option;
  best_score : ticker option;
  ranking : (ticker * float) list;   (** Sorted by GARP score *)
}
[@@deriving show]

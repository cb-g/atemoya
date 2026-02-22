(** Types for growth investor analysis *)

(** Raw growth data from Python fetcher *)
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

(** Revenue growth tier *)
type growth_tier =
  | Hypergrowth     (** > 40% YoY *)
  | HighGrowth      (** 20-40% YoY *)
  | ModerateGrowth  (** 10-20% YoY *)
  | SlowGrowth      (** 5-10% YoY *)
  | NoGrowth        (** < 5% YoY *)
  | Declining       (** Negative growth *)

(** Rule of 40 assessment *)
type rule_of_40_tier =
  | Excellent   (** > 40 *)
  | Good        (** 30-40 *)
  | Moderate    (** 20-30 *)
  | Concerning  (** < 20 *)

(** Margin trajectory *)
type margin_trajectory =
  | Expanding   (** Margins improving *)
  | Stable      (** Margins flat *)
  | Contracting (** Margins declining *)

(** Calculated growth metrics *)
type growth_metrics = {
  revenue_growth_pct : float;
  revenue_cagr_3y_pct : float;
  earnings_growth_pct : float;
  growth_tier : growth_tier;
  rule_of_40 : float;
  rule_of_40_tier : rule_of_40_tier;
  ev_revenue_per_growth : float;   (** EV/Rev divided by growth rate *)
  peg_ratio : float option;        (** P/E / EPS growth *)
}

(** Margin analysis *)
type margin_analysis = {
  gross_margin_pct : float;
  operating_margin_pct : float;
  fcf_margin_pct : float;
  margin_trajectory : margin_trajectory;
  operating_leverage : float;  (** Operating income growth / Revenue growth *)
}

(** Valuation metrics for growth stocks *)
type growth_valuation = {
  ev_revenue : float;
  ev_ebitda : float;
  forward_pe : float;
  implied_growth : float option;  (** What growth is implied by current valuation *)
  analyst_upside_pct : float option;
}

(** Growth score breakdown *)
type growth_score = {
  total_score : float;          (** 0-100 *)
  grade : string;               (** A, B, C, D, F *)
  revenue_growth_score : float; (** 0-25 *)
  earnings_growth_score : float; (** 0-20 *)
  margin_score : float;         (** 0-20 *)
  efficiency_score : float;     (** 0-20 - Rule of 40, operating leverage *)
  quality_score : float;        (** 0-15 - ROE, ROIC *)
}

(** Growth signal *)
type growth_signal =
  | StrongGrowth      (** High growth + improving margins *)
  | GrowthBuy         (** Good growth characteristics *)
  | GrowthHold        (** Moderate growth *)
  | GrowthCaution     (** Slowing growth or poor efficiency *)
  | NotGrowthStock    (** Slow/no growth *)

(** Complete growth analysis result *)
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

(** String conversion functions *)
let string_of_growth_tier = function
  | Hypergrowth -> "Hypergrowth (>40%)"
  | HighGrowth -> "High Growth (20-40%)"
  | ModerateGrowth -> "Moderate Growth (10-20%)"
  | SlowGrowth -> "Slow Growth (5-10%)"
  | NoGrowth -> "No Growth (<5%)"
  | Declining -> "Declining"

let string_of_rule_of_40_tier = function
  | Excellent -> "Excellent"
  | Good -> "Good"
  | Moderate -> "Moderate"
  | Concerning -> "Concerning"

let string_of_margin_trajectory = function
  | Expanding -> "Expanding"
  | Stable -> "Stable"
  | Contracting -> "Contracting"

let string_of_growth_signal = function
  | StrongGrowth -> "Strong Growth"
  | GrowthBuy -> "Growth Buy"
  | GrowthHold -> "Growth Hold"
  | GrowthCaution -> "Growth Caution"
  | NotGrowthStock -> "Not a Growth Stock"

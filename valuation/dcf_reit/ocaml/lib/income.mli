(** Income investor metrics for REITs

    Provides metrics and scoring from an income investor's perspective,
    complementing the value-based analysis.

    Income investors care about:
    1. Current yield relative to risk-free rate and alternatives
    2. Dividend sustainability (coverage ratio, occupancy, lease structure)
    3. Dividend growth track record and potential
    4. Quality of underlying cash flows
    5. Rate environment (declining rates = REITs more attractive)
*)

open Types

(** Quality factors for income assessment *)
type income_quality_factors = {
  occupancy_premium : float;        (** Bonus for high occupancy (0-10) *)
  lease_structure_premium : float;  (** Bonus for triple-net leases (0-10) *)
  dividend_track_record : float;    (** Bonus for long dividend history (0-15) *)
  rate_environment_bonus : float;   (** Bonus when yield spread is attractive (0-10) *)
  monthly_dividend_bonus : float;   (** Bonus for monthly payers (0-5) *)
}

val pp_income_quality_factors : Format.formatter -> income_quality_factors -> unit
val show_income_quality_factors : income_quality_factors -> string

(** Income investor metrics *)
type income_metrics = {
  dividend_yield : float;           (** Annual dividend / Price *)
  dividend_per_share : float;       (** Annual dividend amount *)
  coverage_ratio : float;           (** Earnings / Dividend - >1.0 is safe *)
  coverage_status : string;         (** "Well Covered", "Covered", "At Risk", "Uncovered" *)
  earnings_per_share : float;       (** FFO for equity, DE for mREIT *)
  payout_ratio : float;             (** Dividend / Earnings *)
  payout_status : string;           (** "Conservative", "Normal", "Aggressive", "Unsustainable" *)
  yield_vs_sector : float;          (** Yield premium/discount vs sector average *)
  yield_vs_10yr : float;            (** Spread to 10-year Treasury *)
  yield_percentile : float;         (** Where current yield ranks historically 0-100 *)
  quality_factors : income_quality_factors option;  (** Quality bonuses for equity REITs *)
  income_score : float;             (** 0-100 composite score *)
  income_grade : string;            (** A, B, C, D, F *)
  income_recommendation : string;   (** "Strong Income Buy", "Income Buy", etc. *)
}

val pp_income_metrics : Format.formatter -> income_metrics -> unit
val show_income_metrics : income_metrics -> string

(** Get sector average dividend yield *)
val get_sector_avg_yield : property_sector -> float

(** Calculate income metrics for equity REITs *)
val calculate_equity_reit :
  market:market_data ->
  ffo_metrics:ffo_metrics ->
  quality:quality_metrics ->
  risk_free_rate:float ->
  income_metrics

(** Calculate income metrics for mortgage REITs *)
val calculate_mreit :
  market:market_data ->
  mreit_metrics:mreit_metrics ->
  risk_free_rate:float ->
  income_metrics

(** Format income metrics for display *)
val format_income_metrics : income_metrics -> string

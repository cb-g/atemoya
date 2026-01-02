(** Scenario analysis: bull, base, and bear valuations *)

(** Scenario type *)
type scenario_type =
  | Bull    (** Optimistic: higher growth, lower discount rate *)
  | Base    (** Current parameters *)
  | Bear    (** Pessimistic: lower growth, higher discount rate *)
[@@deriving show]

(** Scenario parameters adjustment *)
type scenario_adjustment = {
  growth_delta : float;           (** Adjustment to growth rates *)
  discount_rate_delta : float;    (** Adjustment to discount rates (CE, WACC) *)
}
[@@deriving show]

(** Scenario result *)
type scenario_result = {
  scenario : scenario_type;
  ivps_fcfe : float;
  ivps_fcff : float;
  margin_of_safety_fcfe : float;
  margin_of_safety_fcff : float;
  cost_of_equity : float;
  wacc : float;
  growth_rate_fcfe : float;
  growth_rate_fcff : float;
}
[@@deriving show]

(** Scenario comparison *)
type scenario_comparison = {
  ticker : Types.ticker;
  price : float;
  bull : scenario_result;
  base : scenario_result;
  bear : scenario_result;
}
[@@deriving show]

(** Default scenario adjustments:
    - Bull: +5% growth, -50bps discount rates
    - Base: no adjustment
    - Bear: -5% growth, +50bps discount rates *)
val default_adjustments : scenario_type -> scenario_adjustment

(** Run scenario analysis for a ticker
    Returns comparison of bull/base/bear valuations *)
val run_scenario_analysis :
  market_data:Types.market_data ->
  financial_data:Types.financial_data ->
  config:Types.config ->
  scenario_comparison option

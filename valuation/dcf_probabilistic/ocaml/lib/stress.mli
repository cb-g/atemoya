(** Stress testing module for scenario analysis *)

open Types

(** Generate all predefined stress scenarios for a given asset *)
val generate_stress_scenarios :
  market_data:market_data ->
  time_series:time_series ->
  cost_of_capital:cost_of_capital ->
  config:simulation_config ->
  roe_prior:beta_prior ->
  retention_prior:beta_prior ->
  roic_prior:beta_prior ->
  tax_rate:float ->
  stress_scenario list
(** Generates a list of stress scenarios representing historical crises:
    - 2008 Financial Crisis
    - Volcker High Rates (1980)
    - 2020 COVID Crash
    - Tech Bubble Burst (2000)
    Each scenario runs deterministic valuations under stress conditions. *)

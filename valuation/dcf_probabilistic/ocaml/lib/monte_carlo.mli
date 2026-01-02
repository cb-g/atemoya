(** Monte Carlo simulation engine for probabilistic DCF *)

(** Run one simulation iteration for FCFE valuation *)
val simulate_fcfe_once :
  market_data:Types.market_data ->
  time_series:Types.time_series ->
  cost_of_capital:Types.cost_of_capital ->
  config:Types.simulation_config ->
  roe_prior:Types.beta_prior ->
  retention_prior:Types.beta_prior ->
  Types.simulation_sample

(** Run one simulation iteration for FCFF valuation *)
val simulate_fcff_once :
  market_data:Types.market_data ->
  time_series:Types.time_series ->
  cost_of_capital:Types.cost_of_capital ->
  config:Types.simulation_config ->
  roic_prior:Types.beta_prior ->
  tax_rate:float ->
  Types.simulation_sample

(** Run Monte Carlo simulation for FCFE method
    Returns array of intrinsic values per share *)
val run_fcfe_simulations :
  market_data:Types.market_data ->
  time_series:Types.time_series ->
  cost_of_capital:Types.cost_of_capital ->
  config:Types.simulation_config ->
  roe_prior:Types.beta_prior ->
  retention_prior:Types.beta_prior ->
  float array

(** Run Monte Carlo simulation for FCFF method
    Returns array of intrinsic values per share *)
val run_fcff_simulations :
  market_data:Types.market_data ->
  time_series:Types.time_series ->
  cost_of_capital:Types.cost_of_capital ->
  config:Types.simulation_config ->
  roic_prior:Types.beta_prior ->
  tax_rate:float ->
  float array

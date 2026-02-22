(** Probabilistic O&G valuation using NAV Model
    Runs Monte Carlo simulations sampling oil price, gas price, lifting cost, and discount rate *)

(** Run N Monte Carlo simulations of O&G fair value per share.
    Returns array of IVPS samples. *)
val run_oil_gas_simulations :
  oil_gas_data:Types.oil_gas_data ->
  market_data:Types.market_data ->
  cost_of_capital:Types.cost_of_capital ->
  config:Types.simulation_config ->
  tax_rate:float ->
  oil_price:float ->
  gas_price:float ->
  float array

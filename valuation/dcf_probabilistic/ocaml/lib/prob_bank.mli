(** Probabilistic bank valuation using Excess Return Model
    Runs Monte Carlo simulations sampling ROE, cost of equity, and BV growth *)

(** Run N Monte Carlo simulations of bank fair value per share.
    Returns array of IVPS samples. *)
val run_bank_simulations :
  bank_data:Types.bank_data ->
  market_data:Types.market_data ->
  cost_of_capital:Types.cost_of_capital ->
  config:Types.simulation_config ->
  float array

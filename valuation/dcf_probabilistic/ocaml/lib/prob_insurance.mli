(** Probabilistic insurance valuation using Float-Based Model
    Runs Monte Carlo simulations sampling combined ratio, investment yield, and CoE *)

(** Run N Monte Carlo simulations of insurance fair value per share.
    Returns array of IVPS samples. *)
val run_insurance_simulations :
  insurance_data:Types.insurance_data ->
  market_data:Types.market_data ->
  cost_of_capital:Types.cost_of_capital ->
  config:Types.simulation_config ->
  float array

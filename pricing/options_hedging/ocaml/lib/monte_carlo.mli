(* Monte Carlo Option Pricing - Longstaff-Schwartz for American Options *)

(* Generate price paths via Geometric Brownian Motion
   Returns: paths[i][t] = price at time t for path i
*)
val simulate_price_paths :
  spot:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  expiry:float ->
  num_steps:int ->
  num_paths:int ->
  float array array

(* Longstaff-Schwartz algorithm for American option pricing *)
val price_american_option :
  Types.option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  num_paths:int ->
  num_steps:int ->
  float

(* Monte Carlo Greeks via finite differences *)
val monte_carlo_delta :
  Types.option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  num_paths:int ->
  num_steps:int ->
  float

val monte_carlo_gamma :
  Types.option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  num_paths:int ->
  num_steps:int ->
  float

val monte_carlo_vega :
  Types.option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  num_paths:int ->
  num_steps:int ->
  float

(* Laguerre polynomial basis functions for regression *)
val laguerre_basis :
  x:float ->
  degree:int ->
  float array

(* Compute immediate exercise value *)
val exercise_value :
  Types.option_type ->
  spot:float ->
  strike:float ->
  float

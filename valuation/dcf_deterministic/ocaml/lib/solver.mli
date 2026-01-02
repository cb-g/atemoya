(** Implied growth rate solver using Newton-Raphson + bisection *)

(** Solve for implied FCFE growth rate given market price.
    Uses Newton-Raphson method with bisection fallback.
    Returns None if no valid solution exists. *)
val solve_implied_fcfe_growth :
  fcfe_0:float ->
  shares_outstanding:float ->
  market_price:float ->
  cost_of_equity:float ->
  terminal_growth_rate:float ->
  projection_years:int ->
  max_iterations:int ->
  tolerance:float ->
  float option

(** Solve for implied FCFF growth rate given market price.
    Uses Newton-Raphson method with bisection fallback.
    Returns None if no valid solution exists. *)
val solve_implied_fcff_growth :
  fcff_0:float ->
  shares_outstanding:float ->
  market_price:float ->
  debt:float ->
  wacc:float ->
  terminal_growth_rate:float ->
  projection_years:int ->
  max_iterations:int ->
  tolerance:float ->
  float option

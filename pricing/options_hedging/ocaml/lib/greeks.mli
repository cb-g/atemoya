(* Portfolio-Level Greeks Analysis *)

(* Portfolio Greeks: sum of individual option Greeks weighted by contracts *)
val portfolio_greeks : Types.hedge_strategy list -> Types.greeks

(* Greeks for a single hedge strategy
   Computes Greeks for all options in the strategy
*)
val strategy_greeks :
  Types.strategy_type ->
  underlying_data:Types.underlying_data ->
  vol_surface:Types.vol_surface ->
  rate:float ->
  contracts:int ->
  Types.greeks

(* Check if portfolio is delta-neutral within tolerance *)
val is_delta_neutral : Types.greeks -> tolerance:float -> bool

(* Check if portfolio is gamma-neutral within tolerance *)
val is_gamma_neutral : Types.greeks -> tolerance:float -> bool

(* Greeks sensitivity analysis via finite differences
   Returns: (spot_bump, vol_bump, rate_bump, time_bump)
   Each is a tuple of (greek_name, bumped_value)
*)
val greeks_bumps :
  Types.option_spec ->
  underlying_data:Types.underlying_data ->
  vol_surface:Types.vol_surface ->
  rate:float ->
  bump_size:float ->
  (string * Types.greeks) list

(* Compute Greeks for a single option position *)
val option_greeks :
  Types.option_spec ->
  underlying_data:Types.underlying_data ->
  volatility:float ->
  rate:float ->
  Types.greeks

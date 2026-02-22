(* Hedge Strategy Construction and Pricing *)

(* Create a protective put strategy *)
val protective_put :
  underlying_position:float ->
  put_strike:float ->
  expiry:float ->
  underlying_data:Types.underlying_data ->
  vol_surface:Types.vol_surface ->
  rate:float ->
  Types.hedge_strategy

(* Create a collar strategy (long put + short call) *)
val collar :
  underlying_position:float ->
  put_strike:float ->
  call_strike:float ->
  expiry:float ->
  underlying_data:Types.underlying_data ->
  vol_surface:Types.vol_surface ->
  rate:float ->
  Types.hedge_strategy

(* Create a vertical put spread *)
val vertical_put_spread :
  underlying_position:float ->
  long_put_strike:float ->
  short_put_strike:float ->
  expiry:float ->
  underlying_data:Types.underlying_data ->
  vol_surface:Types.vol_surface ->
  rate:float ->
  Types.hedge_strategy

(* Create a covered call strategy *)
val covered_call :
  underlying_position:float ->
  call_strike:float ->
  expiry:float ->
  underlying_data:Types.underlying_data ->
  vol_surface:Types.vol_surface ->
  rate:float ->
  Types.hedge_strategy

(* Compute strategy payoff at expiry *)
val strategy_payoff :
  Types.strategy_type ->
  underlying_position:float ->
  spot_at_expiry:float ->
  float

(* Simulate strategy payoff distribution (Monte Carlo) *)
val strategy_payoff_distribution :
  Types.hedge_strategy ->
  underlying_data:Types.underlying_data ->
  vol_surface:Types.vol_surface ->
  rate:float ->
  num_paths:int ->
  float array

(* Compute protection level (minimum portfolio value) from payoff distribution *)
val compute_protection_level :
  payoff_distribution:float array ->
  confidence:float ->  (* e.g., 0.95 for 95th percentile *)
  float

(* Price options for a strategy (helper) *)
val price_strategy_options :
  Types.strategy_type ->
  expiry:float ->
  underlying_data:Types.underlying_data ->
  vol_surface:Types.vol_surface ->
  rate:float ->
  contracts:int ->
  float  (* Total cost *)

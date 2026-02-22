(* Interface for gamma scalping simulation *)

open Types

(** Main simulation function **)

(* Run a gamma scalping simulation

   Inputs:
   - position_type: Type of position (straddle/strangle/single option)
   - intraday_prices: Array of (timestamp_days, spot_price) tuples
   - entry_iv: Implied volatility at entry (annualized)
   - iv_timeseries: Optional array of (timestamp_days, IV) for changing IV
   - hedging_strategy: Which hedging strategy to use
   - config: Simulation configuration (rates, costs, etc.)
   - expiry: Time to expiration in years

   Output:
   - simulation_result: Complete simulation results with P&L breakdown and hedge log

   Algorithm:
   1. Initialize position at t=0 with entry IV
   2. For each timestep:
      a. Update spot price and Greeks
      b. Check if hedging is required (based on strategy)
      c. Execute hedge if needed
      d. Update P&L attribution (gamma, theta, vega)
      e. Record snapshot
   3. Calculate summary metrics (Sharpe, max DD, etc.)
*)
val run_simulation :
  position_type:position_type ->
  intraday_prices:(float * float) array ->
  entry_iv:float ->
  iv_timeseries:(float * float) array option ->
  hedging_strategy:hedging_strategy ->
  config:simulation_config ->
  expiry:float ->
  simulation_result

(** Helper functions **)

(* Calculate time to expiry at a given timestamp *)
val time_to_expiry :
  current_time:float ->
  entry_time:float ->
  initial_expiry:float ->
  float

(* Extract recent returns for vol-adaptive hedging *)
val get_recent_returns :
  prices:(float * float) array ->
  current_index:int ->
  lookback:int ->
  float array

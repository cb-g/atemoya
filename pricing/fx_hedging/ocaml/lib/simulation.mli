(* Interface for hedge backtesting simulation *)

open Types

(** Main simulation **)

(* Run hedge backtest

   Inputs:
   - exposure_usd: Dollar value of FX exposure
   - fx_rates: Historical FX rate timeseries (timestamp, rate)
   - futures_prices: Historical futures prices (timestamp, price)
   - hedge_strategy: Hedging strategy to use
   - futures: Futures contract specification
   - initial_margin_balance: Starting cash in margin account

   Output:
   - hedge_result: Complete backtest results
*)
val run_hedge_backtest :
  exposure_usd:float ->
  fx_rates:(float * float) array ->
  futures_prices:(float * float) array ->
  hedge_strategy:hedge_strategy ->
  futures:futures_contract ->
  initial_margin_balance:float ->
  transaction_cost_bps:float ->
  hedge_result * simulation_snapshot array

(* Run backtest with options hedge *)
val run_options_backtest :
  exposure_usd:float ->
  fx_rates:(float * float) array ->
  futures_prices:(float * float) array ->
  hedge_strategy:hedge_strategy ->
  option:futures_option ->
  initial_margin_balance:float ->
  transaction_cost_bps:float ->
  hedge_result * simulation_snapshot array

(** Simulation helpers **)

(* Calculate returns from price series *)
val calculate_returns :
  prices:float array ->
  float array

(* Calculate Sharpe ratio *)
val sharpe_ratio :
  returns:float array ->
  risk_free_rate:float ->
  float option

(* Calculate maximum drawdown *)
val max_drawdown :
  cumulative_pnl:float array ->
  float

(* Calculate win rate *)
val win_rate :
  daily_pnl:float array ->
  float

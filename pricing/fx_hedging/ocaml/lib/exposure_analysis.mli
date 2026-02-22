(* Interface for FX exposure analysis *)

open Types

(** Portfolio exposure calculation **)

(* Calculate total FX exposure from portfolio positions

   Aggregates currency exposure across all positions
   Returns array of exposures by currency
*)
val calculate_portfolio_exposure :
  positions:portfolio_position array ->
  fx_exposure array

(* Calculate net exposure for a single currency *)
val net_currency_exposure :
  positions:portfolio_position array ->
  currency:currency ->
  float

(* Calculate total portfolio value in USD *)
val total_portfolio_value :
  positions:portfolio_position array ->
  float

(* Calculate exposure percentage for each currency *)
val exposure_percentages :
  positions:portfolio_position array ->
  (currency * float) list  (* [(EUR, 25.5); (JPY, 15.2)] *)

(** Hedge sizing **)

(* Calculate notional amount to hedge for a currency *)
val hedge_notional :
  exposure_usd:float ->
  hedge_ratio:float ->
  float

(* Calculate number of futures contracts needed *)
val futures_contracts_needed :
  exposure_usd:float ->
  hedge_ratio:float ->
  futures_price:float ->
  contract_size:float ->
  int

(* Calculate number of options contracts needed (delta-adjusted) *)
val options_contracts_needed :
  exposure_usd:float ->
  hedge_ratio:float ->
  option_delta:float ->
  futures_price:float ->
  contract_size:float ->
  int

(** Direct vs Indirect exposure **)

(* Separate direct and indirect currency exposures *)
val split_direct_indirect :
  position:portfolio_position ->
  (float * float)  (* (direct_exposure, indirect_exposure) in USD *)

(* Calculate effective FX sensitivity (beta to FX rate) *)
val fx_beta :
  position:portfolio_position ->
  currency:currency ->
  float  (* Beta coefficient *)

(** Risk metrics **)

(* Value at Risk from FX exposure

   VaR = Exposure × σ_FX × z_score

   where:
     σ_FX = FX rate volatility
     z_score = standard normal quantile (e.g., 1.65 for 95% confidence)
*)
val fx_var :
  exposure_usd:float ->
  fx_volatility:float ->
  confidence_level:float ->
  horizon_days:int ->
  float

(* Expected Shortfall (CVaR) from FX exposure *)
val fx_cvar :
  exposure_usd:float ->
  fx_volatility:float ->
  confidence_level:float ->
  horizon_days:int ->
  float

(** Scenario analysis **)

(* Calculate P&L impact from FX rate change *)
val fx_scenario_pnl :
  exposure_usd:float ->
  fx_rate_initial:float ->
  fx_rate_scenario:float ->
  float

(* Calculate portfolio P&L from FX shocks *)
val portfolio_fx_scenario :
  positions:portfolio_position array ->
  fx_shocks:(currency * float) list ->  (* [(EUR, 0.10); (JPY, -0.05)] = % changes *)
  float  (* Total P&L impact *)

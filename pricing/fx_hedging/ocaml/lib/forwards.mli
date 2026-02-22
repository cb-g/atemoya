(* Interface for FX forward pricing *)

open Types

(** Forward pricing using covered interest rate parity **)

(* Calculate forward rate from spot and interest rates

   Formula: F = S × e^((r_d - r_f) × T)

   where:
     S = spot rate
     r_d = domestic (quote currency) interest rate
     r_f = foreign (base currency) interest rate
     T = time to maturity in years
*)
val forward_rate :
  spot:float ->
  domestic_rate:float ->
  foreign_rate:float ->
  maturity:float ->
  float

(* Calculate forward points (difference between forward and spot)

   Forward Points = F - S
*)
val forward_points :
  spot:float ->
  domestic_rate:float ->
  foreign_rate:float ->
  maturity:float ->
  float

(* Build a forward contract *)
val build_forward :
  pair:fx_pair ->
  domestic_rate:float ->
  foreign_rate:float ->
  maturity:float ->
  notional:float ->
  forward_contract

(* Calculate implied foreign rate from forward rate

   Useful for extracting market's implied foreign interest rate
   from observed forward prices
*)
val implied_foreign_rate :
  spot:float ->
  forward:float ->
  domestic_rate:float ->
  maturity:float ->
  float

(* Calculate implied domestic rate from forward rate *)
val implied_domestic_rate :
  spot:float ->
  forward:float ->
  foreign_rate:float ->
  maturity:float ->
  float

(* Check if covered interest parity holds

   Returns true if arbitrage-free, false if arbitrage opportunity exists
*)
val check_covered_interest_parity :
  spot:float ->
  forward:float ->
  domestic_rate:float ->
  foreign_rate:float ->
  maturity:float ->
  tolerance:float ->
  bool

(* Calculate forward contract value (mark-to-market)

   Value of existing forward at current market rates
*)
val forward_value :
  contract:forward_contract ->
  current_spot:float ->
  current_domestic_rate:float ->
  current_foreign_rate:float ->
  time_remaining:float ->
  float

(* P&L from forward position *)
val forward_pnl :
  entry_forward:float ->
  exit_forward:float ->
  notional:float ->
  float

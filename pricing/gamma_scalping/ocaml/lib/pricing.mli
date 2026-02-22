(* Interface for option pricing and Greeks *)

open Types

(** Black-Scholes option pricing **)

(* Price European option *)
val price_option :
  option_type:option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  float

(** Greeks calculation **)

(* Compute all Greeks at once *)
val compute_greeks :
  option_type:option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  greeks

(* Individual Greeks *)
val delta :
  option_type:option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  float

val gamma :
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  float

val theta :
  option_type:option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  float

val vega :
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  float

val rho :
  option_type:option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  float

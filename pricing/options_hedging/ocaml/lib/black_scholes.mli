(* Black-Scholes-Merton Pricing and Greeks *)

(* Standard normal cumulative distribution function *)
val normal_cdf : float -> float

(* Standard normal probability density function *)
val normal_pdf : float -> float

(* Black-Scholes formula for European options *)
val price_european_option :
  option_type:Types.option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  float

(* Individual Greeks *)
val delta :
  Types.option_type ->
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

val vega :
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  float

val theta :
  Types.option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  float

val rho :
  Types.option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  float

(* Calculate all Greeks at once *)
val calculate_greeks :
  Types.option_type ->
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  Types.greeks

(* Helper: compute d1 and d2 from BSM formula *)
val compute_d1_d2 :
  spot:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  dividend:float ->
  volatility:float ->
  float * float

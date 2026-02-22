(* Interface for futures options pricing (Black-76 model) *)

open Types

(** Black-76 Model for Options on Futures **)

(* Price European option on futures using Black's model

   Call: C = e^(-rT) [F·N(d₁) - K·N(d₂)]
   Put:  P = e^(-rT) [K·N(-d₂) - F·N(-d₁)]

   where:
     F = futures price (NOT spot!)
     K = strike price
     T = time to expiry
     r = risk-free rate
     σ = volatility of futures price
*)
val black_price :
  option_type:option_type ->
  futures_price:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  volatility:float ->
  float

(* Compute all Greeks at once for futures options *)
val black_greeks :
  option_type:option_type ->
  futures_price:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  volatility:float ->
  greeks

(* Individual Greeks *)

(* Delta: ∂V/∂F (sensitivity to futures price, NOT spot!)

   Δ_call = e^(-rT) · N(d₁)
   Δ_put = -e^(-rT) · N(-d₁)
*)
val delta :
  option_type:option_type ->
  futures_price:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  volatility:float ->
  float

(* Gamma: ∂²V/∂F²

   Γ = e^(-rT) · n(d₁) / (F · σ · √T)

   Same for calls and puts
*)
val gamma :
  futures_price:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  volatility:float ->
  float

(* Theta: -∂V/∂t (per day)

   Different formula from Black-Scholes!
*)
val theta :
  option_type:option_type ->
  futures_price:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  volatility:float ->
  float

(* Vega: ∂V/∂σ (per 1% vol change)

   ν = F · e^(-rT) · n(d₁) · √T / 100

   Same for calls and puts
*)
val vega :
  futures_price:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  volatility:float ->
  float

(* Rho: ∂V/∂r (per 1% rate change)

   Different from Black-Scholes! Only affects discounting.

   ρ_call = T · C
   ρ_put = -T · P
*)
val rho :
  option_type:option_type ->
  premium:float ->
  expiry:float ->
  float

(** Helper functions **)

(* Build futures option from specification *)
val build_futures_option :
  futures:futures_contract ->
  option_type:option_type ->
  strike:float ->
  expiry:float ->
  rate:float ->
  volatility:float ->
  futures_option

(* Calculate intrinsic value *)
val intrinsic_value :
  option_type:option_type ->
  futures_price:float ->
  strike:float ->
  float

(* Calculate time value *)
val time_value :
  option_type:option_type ->
  futures_price:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  volatility:float ->
  float

(* Check if option is ITM/ATM/OTM *)
val moneyness :
  option_type:option_type ->
  futures_price:float ->
  strike:float ->
  string  (* "ITM", "ATM", or "OTM" *)

(* Calculate implied volatility from option price

   Uses Newton-Raphson iteration
*)
val implied_volatility :
  option_type:option_type ->
  futures_price:float ->
  strike:float ->
  expiry:float ->
  rate:float ->
  market_price:float ->
  float option  (* None if cannot solve *)

(** Everlasting options pricing. *)

open Types

(** Solve quadratic for option exponents. Returns (Pi, Theta). *)
val quadratic_roots :
  r_a:float -> r_b:float -> sigma:float -> kappa:float -> float * float

(** Perpetual futures price for put-call parity. *)
val perpetual_futures :
  kappa:float -> r_a:float -> r_b:float -> spot:float -> float

(** Everlasting call option price. *)
val price_everlasting_call :
  kappa:float -> r_a:float -> r_b:float -> sigma:float ->
  strike:float -> spot:float -> float

(** Everlasting put option price. *)
val price_everlasting_put :
  kappa:float -> r_a:float -> r_b:float -> sigma:float ->
  strike:float -> spot:float -> float

(** Everlasting call delta. *)
val delta_everlasting_call :
  kappa:float -> r_a:float -> r_b:float -> sigma:float ->
  strike:float -> spot:float -> float

(** Everlasting put delta. *)
val delta_everlasting_put :
  kappa:float -> r_a:float -> r_b:float -> sigma:float ->
  strike:float -> spot:float -> float

(** Price option with full result. *)
val price_option : everlasting_option -> spot:float -> option_result

(** Generate price grid for plotting. Returns (spot, call, put) list. *)
val option_price_grid :
  kappa:float -> r_a:float -> r_b:float -> sigma:float ->
  strike:float -> spots:float list -> (float * float * float) list

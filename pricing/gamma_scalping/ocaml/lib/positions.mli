(* Interface for building gamma scalping positions *)

open Types

(** Position constructors **)

(* Build a straddle: long ATM call + long ATM put at the same strike *)
val build_straddle :
  spot:float ->
  strike:float ->
  expiry:float ->
  volatility:float ->
  rate:float ->
  dividend:float ->
  contracts:int ->
  (float * greeks)  (* (total_premium, combined_greeks) *)

(* Build a strangle: long OTM call + long OTM put at different strikes *)
val build_strangle :
  spot:float ->
  call_strike:float ->
  put_strike:float ->
  expiry:float ->
  volatility:float ->
  rate:float ->
  dividend:float ->
  contracts:int ->
  (float * greeks)  (* (total_premium, combined_greeks) *)

(* Build a single option position *)
val build_single_option :
  spot:float ->
  option_type:option_type ->
  strike:float ->
  expiry:float ->
  volatility:float ->
  rate:float ->
  dividend:float ->
  contracts:int ->
  (float * greeks)  (* (total_premium, greeks) *)

(** Position Greeks calculation **)

(* Calculate Greeks for a given position type *)
val position_greeks :
  position_type:position_type ->
  spot:float ->
  expiry:float ->
  volatility:float ->
  rate:float ->
  dividend:float ->
  contracts:int ->
  (float * greeks)  (* (total_premium, greeks) *)

(** Helper functions **)

(* Combine Greeks from multiple options *)
val add_greeks : greeks -> greeks -> greeks

(* Scale Greeks by a factor (e.g., number of contracts) *)
val scale_greeks : greeks -> float -> greeks

(* Zero Greeks (neutral position) *)
val zero_greeks : greeks

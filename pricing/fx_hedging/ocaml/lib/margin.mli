(* Interface for margin calculations *)

open Types

(** Initial and maintenance margin **)

(* Get initial margin requirement for futures contract *)
val initial_margin :
  futures:futures_contract ->
  quantity:int ->
  float

(* Get maintenance margin requirement *)
val maintenance_margin :
  futures:futures_contract ->
  quantity:int ->
  float

(* Get initial margin for futures option *)
val option_initial_margin :
  option:futures_option ->
  quantity:int ->
  float

(** Margin account management **)

(* Create margin account *)
val create_margin_account :
  cash_balance:float ->
  initial_margin_required:float ->
  maintenance_margin_required:float ->
  margin_account

(* Update margin account after daily settlement *)
val update_margin_account :
  account:margin_account ->
  variation_margin:float ->
  margin_account

(* Check if margin call is triggered *)
val is_margin_call :
  account:margin_account ->
  bool

(* Calculate required deposit to restore margin *)
val margin_call_amount :
  account:margin_account ->
  float

(* Calculate excess margin (available to withdraw) *)
val excess_margin :
  account:margin_account ->
  float

(** SPAN margin (simplified) **)

(* Simplified SPAN margin calculation

   SPAN (Standard Portfolio Analysis of Risk) calculates
   worst-case loss across multiple scenarios

   This is a simplified version - real SPAN is much more complex
*)
val span_margin_estimate :
  futures:futures_contract ->
  quantity:int ->
  float

(* SPAN margin for option position *)
val span_option_margin :
  option:futures_option ->
  quantity:int ->
  float

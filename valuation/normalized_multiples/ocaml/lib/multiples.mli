(** Multiple calculations and extraction *)

open Types

(** Create a normalized multiple with validation *)
val make_multiple :
  name:string ->
  time_window:time_window ->
  value:float ->
  underlying_metric:float ->
  normalized_multiple

(** Extract all multiples from company data as a flat list *)
val extract_all_multiples : company_multiples -> normalized_multiple list

(** Get just the price multiples *)
val get_price_multiples : company_multiples -> normalized_multiple list

(** Get just the EV multiples *)
val get_ev_multiples : company_multiples -> normalized_multiple list

(** List of all supported multiple names *)
val all_price_multiple_names : string list
val all_ev_multiple_names : string list

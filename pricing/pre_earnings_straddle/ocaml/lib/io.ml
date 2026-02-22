(** IO Module for Loading Data *)

open Types

(** Load historical earnings events from CSV *)
let load_earnings_history ~(file_path : string) ~(ticker : string) : earnings_event array =
  try
    let ic = open_in file_path in
    let rec read_lines acc =
      try
        let line = input_line ic in
        read_lines (line :: acc)
      with End_of_file ->
        close_in ic;
        List.rev acc
    in
    let lines = read_lines [] in

    (* Skip header *)
    let data_lines = match lines with
      | [] -> []
      | _ :: rest -> rest
    in

    let parse_line line =
      let parts = String.split_on_char ',' line in
      match parts with
      | t :: date :: implied :: realized :: _ when t = ticker ->
          Some {
            ticker = t;
            date;
            implied_move = float_of_string implied;
            realized_move = float_of_string realized;
          }
      | _ -> None
    in

    let events = List.filter_map parse_line data_lines in
    Array.of_list events
  with
  | Sys_error _ ->
      Printf.printf "Warning: Could not load earnings history file: %s\n" file_path;
      [||]

(** Load straddle opportunity from CSV *)
let load_opportunity ~(file_path : string) : straddle_opportunity option =
  try
    let ic = open_in file_path in
    let _ = input_line ic in  (* Skip header *)
    let line = input_line ic in
    close_in ic;

    let parts = String.split_on_char ',' line in
    match parts with
    | ticker :: earnings_date :: days_to_earnings :: spot :: atm_strike ::
      call_price :: put_price :: cost :: implied_move :: exp :: dte :: _ ->
        Some {
          ticker;
          earnings_date;
          days_to_earnings = int_of_string days_to_earnings;
          spot_price = float_of_string spot;
          atm_strike = float_of_string atm_strike;
          atm_call_price = float_of_string call_price;
          atm_put_price = float_of_string put_price;
          straddle_cost = float_of_string cost;
          current_implied_move = float_of_string implied_move;
          expiration = exp;
          days_to_expiry = int_of_string dte;
        }
    | _ -> None
  with Sys_error _ | End_of_file | Failure _ -> None

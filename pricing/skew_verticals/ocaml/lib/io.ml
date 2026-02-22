(** CSV Input/Output *)

open Types

(** Load option data from CSV *)
let load_options_csv ~(file_path : string) : option_data array =
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

  (* CSV columns: strike,option_type,implied_vol,bid,ask,open_interest,volume,mid_price,delta *)
  let parse_line line =
    let parts = String.split_on_char ',' line in
    match parts with
    | strike :: opt_type :: iv :: bid :: ask :: _oi :: _vol :: mid :: delta :: _ ->
        (try
          Some {
            strike = float_of_string strike;
            option_type = opt_type;
            implied_vol = float_of_string iv;
            delta = float_of_string delta;
            bid = float_of_string bid;
            ask = float_of_string ask;
            mid_price = float_of_string mid;
          }
        with Failure _ ->
          Printf.eprintf "Warning: Failed to parse line: %s\n" line;
          None)
    | _ -> None
  in

  let options = List.filter_map parse_line data_lines in
  Array.of_list options

(** Load metadata from CSV *)
let load_metadata_csv ~(file_path : string) : (string * float * string * int * float) =
  let ic = open_in file_path in
  let _ = input_line ic in  (* Skip header *)
  let line = input_line ic in
  close_in ic;

  let parts = String.split_on_char ',' line in
  match parts with
  | ticker :: spot :: expiration :: days :: atm :: _ ->
      (ticker,
       float_of_string spot,
       expiration,
       int_of_string days,
       float_of_string atm)
  | _ -> failwith "Invalid metadata CSV format"

(** Load price data from CSV *)
let load_prices_csv ~(file_path : string) : (string * float) array =
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
    | date :: price :: _ ->
        (try
          Some (date, float_of_string price)
        with Failure _ ->
          Printf.eprintf "Warning: Failed to parse price line: %s\n" line;
          None)
    | _ -> None
  in

  let prices = List.filter_map parse_line data_lines in
  Array.of_list prices

(** Print options chain summary *)
let print_chain_summary (chain : options_chain) : unit =
  Printf.printf "\n=== Options Chain: %s ===\n" chain.ticker;
  Printf.printf "Spot: $%.2f\n" chain.spot_price;
  Printf.printf "ATM Strike: $%.2f\n" chain.atm_strike;
  Printf.printf "Expiration: %s (%d days)\n" chain.expiration chain.days_to_expiry;
  Printf.printf "Calls: %d | Puts: %d\n"
    (Array.length chain.calls) (Array.length chain.puts)

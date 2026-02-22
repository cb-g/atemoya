(** Macro Dashboard CLI *)

open Macro_dashboard

let usage = {|
Macro Economic Dashboard

Usage:
  macro_dashboard <macro_data.json> [options]

Options:
  --output <file>     Save classified environment to JSON
  --quiet             Suppress detailed output

Example:
  macro_dashboard data/macro_data.json --output output/environment.json
|}

let () =
  let args = Array.to_list Sys.argv |> List.tl in

  if List.length args = 0 || List.mem "--help" args || List.mem "-h" args then begin
    print_string usage;
    exit 0
  end;

  (* Parse arguments *)
  let input_file = ref "" in
  let output_file = ref "" in
  let quiet = ref false in

  let rec parse = function
    | [] -> ()
    | "--output" :: file :: rest ->
        output_file := file;
        parse rest
    | "--quiet" :: rest ->
        quiet := true;
        parse rest
    | file :: rest when !input_file = "" ->
        input_file := file;
        parse rest
    | unknown :: _ ->
        Printf.eprintf "Unknown argument: %s\n" unknown;
        exit 1
  in
  parse args;

  if !input_file = "" then begin
    Printf.eprintf "Error: No input file specified\n";
    print_string usage;
    exit 1
  end;

  (* Load macro data *)
  let snapshot =
    try Io.load_macro_data !input_file
    with e ->
      Printf.eprintf "Error loading macro data: %s\n" (Printexc.to_string e);
      exit 1
  in

  (* Classify environment *)
  let env = Classifier.classify snapshot in

  (* Generate investment implications *)
  let impl = Classifier.investment_implications env in

  (* Print dashboard *)
  if not !quiet then
    Io.print_dashboard snapshot env impl;

  (* Save output *)
  if !output_file <> "" then begin
    Io.save_environment !output_file snapshot env impl;
    Printf.printf "\nSaved environment to %s\n" !output_file
  end

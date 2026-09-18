(* Reads boundary financials JSON files and writes one valuation record per line.
   Parameters come from reference/ (or --reference DIR); ages are measured at
   today's UTC date unless --today YYYY-MM-DD is given. *)

let usage =
  "usage: atemoya [--reference DIR] [--today YYYY-MM-DD] <financials.json>...\n"

let today_utc () =
  let tm = Unix.gmtime (Unix.time ()) in
  Printf.sprintf "%04d-%02d-%02d" (tm.tm_year + 1900) (tm.tm_mon + 1) tm.tm_mday

let rec parse_args reference today paths = function
  | [] -> (reference, today, List.rev paths)
  | "--reference" :: dir :: rest -> parse_args dir today paths rest
  | "--today" :: date :: rest -> parse_args reference date paths rest
  | [ ("--reference" | "--today") ] ->
      prerr_string usage;
      exit 2
  | path :: rest -> parse_args reference today (path :: paths) rest

let value params ~today path =
  match
    Atdgen_runtime.Util.Json.from_file Atemoya.Boundary_j.read_financials path
  with
  | fin ->
      print_endline
        (Atemoya.Boundary_j.string_of_valuation
           (Atemoya.Valuation.run params ~today fin));
      true
  | exception
      ( Yojson.Json_error msg
      | Atdgen_runtime.Oj_run.Error msg
      | Sys_error msg
      | Failure msg ) ->
      Printf.eprintf "%s: cannot read financials: %s\n%!" path msg;
      false

let () =
  let reference, today, paths =
    parse_args "reference" (today_utc ()) [] (List.tl (Array.to_list Sys.argv))
  in
  if paths = [] then (
    prerr_string usage;
    exit 2);
  (match Atemoya.Params.days_between ~from:today ~until:today with
  | Ok _ -> ()
  | Error msg ->
      Printf.eprintf "--today: %s\n%!" msg;
      exit 2);
  match Atemoya.Params.load ~dir:reference with
  | Error msg ->
      Printf.eprintf "cannot load parameters from %s: %s\n%!" reference msg;
      exit 2
  | Ok params ->
      let ok =
        List.fold_left (fun ok path -> value params ~today path && ok) true paths
      in
      exit (if ok then 0 else 1)

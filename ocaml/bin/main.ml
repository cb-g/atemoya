(* Values boundary financials JSON files. Parameters come from reference/ (or --reference
   DIR); ages are measured at today's UTC date unless --today YYYY-MM-DD is given.
   Inputs may be files or directories (every *.json inside, sorted). Without --out, one
   valuation record per line goes to stdout. With --out DIR, DIR/valuations.jsonl and
   DIR/summary.txt are written and the summary is printed; the summary checks each ticker
   against --universe FILE, defaulting to <reference>/universe.json when it exists.
   Valuation never fetches. *)

open Atemoya

let usage =
  "usage: atemoya [--reference DIR] [--today YYYY-MM-DD] [--out DIR] [--universe FILE] \
   <financials.json | directory>...\n"

type options = {
  reference : string;
  today : string;
  out : string option;
  universe : string option;
}

let usage_exit () =
  prerr_string usage;
  exit 2

let today_utc () =
  let tm = Unix.gmtime (Unix.time ()) in
  Printf.sprintf "%04d-%02d-%02d" (tm.tm_year + 1900) (tm.tm_mon + 1) tm.tm_mday

let rec parse o paths = function
  | [] -> (o, List.rev paths)
  | "--reference" :: v :: rest -> parse { o with reference = v } paths rest
  | "--today" :: v :: rest -> parse { o with today = v } paths rest
  | "--out" :: v :: rest -> parse { o with out = Some v } paths rest
  | "--universe" :: v :: rest -> parse { o with universe = Some v } paths rest
  | [ ("--reference" | "--today" | "--out" | "--universe") ] -> usage_exit ()
  | p :: rest -> parse o (p :: paths) rest

let expand path =
  match Sys.is_directory path with
  | true ->
      Sys.readdir path |> Array.to_list
      |> List.filter (fun f -> Filename.check_suffix f ".json")
      |> List.sort compare
      |> List.map (Filename.concat path)
  | false -> [ path ]
  | exception Sys_error _ -> [ path ]

let read what reader path =
  match Atdgen_runtime.Util.Json.from_file reader path with
  | v -> Some v
  | exception
      ( Yojson.Json_error msg
      | Atdgen_runtime.Oj_run.Error msg
      | Sys_error msg
      | Failure msg ) ->
      Printf.eprintf "%s: cannot read %s: %s\n%!" path what msg;
      None

let rec mkdir_p dir =
  if dir <> "" && dir <> "." && dir <> "/" && not (Sys.file_exists dir) then (
    mkdir_p (Filename.dirname dir);
    Sys.mkdir dir 0o755)

let write_file path contents =
  let oc = open_out_bin path in
  output_string oc contents;
  close_out oc

let () =
  let o, paths =
    parse
      { reference = "reference"; today = today_utc (); out = None; universe = None }
      []
      (List.tl (Array.to_list Sys.argv))
  in
  if paths = [] then usage_exit ();
  (match Params.days_between ~from:o.today ~until:o.today with
  | Ok _ -> ()
  | Error msg ->
      Printf.eprintf "--today: %s\n%!" msg;
      exit 2);
  let params =
    match Params.load ~dir:o.reference with
    | Ok p -> p
    | Error msg ->
        Printf.eprintf "cannot load parameters from %s: %s\n%!" o.reference msg;
        exit 2
  in
  let universe =
    let path =
      match o.universe with
      | Some p -> Some p
      | None ->
          let p = Filename.concat o.reference "universe.json" in
          if Sys.file_exists p then Some p else None
    in
    match path with
    | None -> None
    | Some p -> (
        match read "universe" Reference_j.read_universe p with
        | Some u -> Some u
        | None -> exit 2)
  in
  let files = List.concat_map expand paths in
  let results =
    List.filter_map
      (fun path ->
        Option.map
          (fun fin -> Valuation.run params ~today:o.today fin)
          (read "financials" Boundary_j.read_financials path))
      files
  in
  let unreadable = List.length files - List.length results in
  let jsonl =
    String.concat ""
      (List.map (fun v -> Boundary_j.string_of_valuation v ^ "\n") results)
  in
  (match o.out with
  | None -> print_string jsonl
  | Some dir ->
      mkdir_p dir;
      write_file (Filename.concat dir "valuations.jsonl") jsonl;
      let summary = Batch.summary ?universe results in
      write_file (Filename.concat dir "summary.txt") summary;
      print_string summary);
  exit (if unreadable > 0 then 1 else 0)

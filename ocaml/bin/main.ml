(* Values boundary financials JSON files. Parameters come from reference/ (or --reference
   DIR); ages are measured at today's UTC date unless --today YYYY-MM-DD is given.
   Inputs may be files or directories (every *.json inside, sorted). The entity class of
   each ticker comes from the universe file (--universe FILE, default
   <reference>/universe.json); a ticker not in it takes --entity-class CLASS if given,
   otherwise it fails as undeclared. Without --out, one valuation record per line goes to
   stdout. With --out DIR, DIR/valuations.jsonl and DIR/summary.txt are written and the
   summary is printed; the universe file is loaded strictly (exactly ticker, entity_class,
   why and scope_limits per entry). With --baseline FILE (a previous run's valuations.jsonl),
   provider_diff.txt opens with this run against that one, every record, every moved fair
   value with the inputs that moved. With --baseline-snapshot DIR as well (the financials
   the baseline run was valued from), DIR/stability_<old>_<new>.txt classifies every moved
   input of every record and the summary gains the counts per class. Every record carries
   model_version (git short hash, -dirty on an uncommitted tree, unversioned outside a
   checkout), and every --out run is also written, never overwritten, to
   DIR/runs/<valued_on>/ (-2, -3 on the same date); the belief map's grid per Ok name with a
   growth-then-terminal path goes to DIR/maps/<ticker>.json (23). Valuation never fetches. *)

open Atemoya

let usage =
  "usage: atemoya [--reference DIR] [--today YYYY-MM-DD] [--out DIR] [--universe FILE] \
   [--entity-class CLASS] [--baseline valuations.jsonl] [--baseline-snapshot DIR] \
   <financials.json | directory>...\n"

type options = {
  reference : string;
  today : string;
  out : string option;
  universe : string option;
  entity_class : string option;
  baseline : string option;
  baseline_snapshot : string option;
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
  | "--entity-class" :: v :: rest -> parse { o with entity_class = Some v } paths rest
  | "--baseline" :: v :: rest -> parse { o with baseline = Some v } paths rest
  | "--baseline-snapshot" :: v :: rest -> parse { o with baseline_snapshot = Some v } paths rest
  | [ ("--reference" | "--today" | "--out" | "--universe" | "--entity-class" | "--baseline" | "--baseline-snapshot") ] ->
      usage_exit ()
  | p :: rest -> parse o (p :: paths) rest

let is_shadow f =
  let marker = ".shadow-" in
  let rec go i = i + String.length marker <= String.length f && (String.sub f i (String.length marker) = marker || go (i + 1)) in
  go 0

let expand path =
  match Sys.is_directory path with
  | true ->
      Sys.readdir path |> Array.to_list
      |> List.filter (fun f -> Filename.check_suffix f ".json" && not (is_shadow f))
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

(* The code that produced this run (21): stdout of a command, None when it did not exit 0
   (git outside a checkout exits 128; stderr is discarded). *)
let command_output cmd =
  match Unix.open_process_in cmd with
  | ic -> (
      let out = In_channel.input_all ic in
      match Unix.close_process_in ic with Unix.WEXITED 0 -> Some out | _ -> None)
  | exception Unix.Unix_error _ -> None

let model_version () =
  Model_version.stamp
    ~head:(command_output "git rev-parse --short HEAD 2>/dev/null")
    ~porcelain:(Option.value ~default:"" (command_output "git status --porcelain 2>/dev/null"))

let class_or_exit s =
  match Admissibility.class_of_string s with
  | Some c -> c
  | None ->
      Printf.eprintf "%S is not an entity class; one of: %s\n%!" s
        (String.concat ", " (List.map Admissibility.class_name Admissibility.all_classes));
      exit 2

(* The declaration for a ticker: its universe entry, else the command-line class. Every
   universe entry's class is validated up front so a typo fails the run, not one record. *)
let declarations (universe : Reference_t.universe option) cli_class =
  let entries =
    match universe with
    | None -> []
    | Some u ->
        List.map
          (fun (e : Reference_t.universe_entry) ->
            ( e.ticker,
              {
                Valuation.entity_class = class_or_exit e.entity_class;
                scope_limits = e.scope_limits;
              } ))
          u.tickers
  in
  let fallback =
    Option.map
      (fun s -> { Valuation.entity_class = class_or_exit s; scope_limits = [] })
      cli_class
  in
  fun ticker ->
    match List.assoc_opt ticker entries with Some d -> Some d | None -> fallback

let () =
  let o, paths =
    parse
      {
        reference = "reference";
        today = today_utc ();
        out = None;
        universe = None;
        entity_class = None;
        baseline = None;
        baseline_snapshot = None;
      }
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
        match Universe.load p with
        | Ok u -> Some u
        | Error msg ->
            Printf.eprintf "%s\n%!" msg;
            exit 2)
  in
  let declaration = declarations universe o.entity_class in
  let model_version = model_version () in
  let files = List.concat_map expand paths in
  (* Each record, and the valuation of its vendor-statement shadow when the fetch wrote one
     (an XBRL-primary name): same declaration, same parameters, for the provider diff. *)
  let paired =
    List.filter_map
      (fun path ->
        Option.map
          (fun (fin : Boundary_t.financials) ->
            let value = Valuation.run params ~today:o.today ~model_version ~declaration:(declaration fin.ticker) in
            let shadow_path =
              Filename.concat (Filename.dirname path) (fin.ticker ^ ".shadow-yfinance.json")
            in
            let shadow =
              if Sys.file_exists shadow_path then
                Option.map value (read "shadow financials" Boundary_j.read_financials shadow_path)
              else None
            in
            (value fin, shadow))
          (read "financials" Boundary_j.read_financials path))
      files
  in
  let results = List.map fst paired in
  (* A previous run's valuations.jsonl, one record per line; an unreadable line is
     reported and skipped, an unreadable file exits. *)
  let baseline =
    Option.map
      (fun path ->
        let lines =
          match In_channel.with_open_bin path In_channel.input_all with
          | text -> String.split_on_char '\n' text |> List.filter (fun l -> String.trim l <> "")
          | exception Sys_error msg ->
              Printf.eprintf "--baseline: cannot read %s: %s\n%!" path msg;
              exit 2
        in
        List.filter_map
          (fun line ->
            match (Boundary_j.valuation_of_string line, Yojson.Safe.from_string line) with
            | v, raw -> Some (v, (v.ticker, raw))
            | exception (Yojson.Json_error msg | Atdgen_runtime.Oj_run.Error msg) ->
                Printf.eprintf "%s: skipping a baseline line: %s\n%!" path msg;
                None)
          lines)
      o.baseline
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
      (* Stability (16): the baseline run's records paired with the financials they were
         valued from, against this run's records and financials. *)
      let stability =
        match (baseline, o.baseline_snapshot) with
        | Some b, Some snapshot ->
            let financials_of dir (v : Boundary_t.valuation) =
              let path = Filename.concat dir (v.ticker ^ ".json") in
              if Sys.file_exists path then read "financials" Boundary_j.read_financials path else None
            in
            let old = List.map (fun (v, _) -> (v, financials_of snapshot v)) b in
            let now =
              List.map2
                (fun path (v, _) -> (v, read "financials" Boundary_j.read_financials path))
                (List.filter (fun p -> Option.is_some (read "financials" Boundary_j.read_financials p)) files)
                paired
            in
            let name d = Filename.basename (if Filename.check_suffix d "/" then Filename.chop_suffix d "/" else d) in
            let snapshot_new =
              match paths with [ p ] when Sys.is_directory p -> name p | _ -> "this run"
            in
            let text, line = Batch.stability ~snapshot_old:(name snapshot) ~snapshot_new ~old ~now in
            Some (Printf.sprintf "stability_%s_%s.txt" (name snapshot) snapshot_new, text, line)
        | _ -> None
      in
      let stability_line = Option.map (fun (_, _, l) -> l) stability in
      (* Dated runs (21): the same three files again under DIR/runs/<valued_on>/, never
         overwritten, so what the model said that day survives the next run. *)
      let run_dir = Batch.dated_run_dir ~exists:Sys.file_exists ~root:(Filename.concat dir "runs") o.today in
      let summary =
        Batch.summary ?universe ~definitions:params.field_definitions ?stability_line ~run_dir results
      in
      let diff =
        (match baseline with
         | Some b -> Batch.run_diff ~baseline_raw:(List.map snd b) ~baseline:(List.map fst b) results ^ "\n"
         | None -> "")
        ^ Batch.provider_diff paired
      in
      Option.iter (fun (file, text, _) -> write_file (Filename.concat dir file) text) stability;
      (* The belief map's grid per name (23): DIR/maps/<ticker>.json, never on the record. *)
      List.iter
        (fun (v : Boundary_t.valuation) ->
          match (v.belief_map, v.price) with
          | Some b, Some price ->
              mkdir_p (Filename.concat dir "maps");
              write_file
                (Filename.concat (Filename.concat dir "maps") (v.ticker ^ ".json"))
                (Boundary_j.string_of_belief_grid (Belief_map.grid b ~ticker:v.ticker ~price) ^ "\n")
          | _ -> ())
        results;
      mkdir_p run_dir;
      List.iter
        (fun d ->
          write_file (Filename.concat d "valuations.jsonl") jsonl;
          write_file (Filename.concat d "summary.txt") summary;
          write_file (Filename.concat d "provider_diff.txt") diff)
        [ dir; run_dir ];
      print_string summary);
  exit (if unreadable > 0 then 1 else 0)

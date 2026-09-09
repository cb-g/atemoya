(* Reads boundary financials JSON files and writes one valuation record per line. *)

let usage = "usage: atemoya <financials.json>...\n"

let value path =
  match Atdgen_runtime.Util.Json.from_file Atemoya.Boundary_j.read_financials path with
  | fin ->
      print_endline (Atemoya.Boundary_j.string_of_valuation (Atemoya.Valuation.run fin));
      true
  | exception
      ( Yojson.Json_error msg
      | Atdgen_runtime.Oj_run.Error msg
      | Sys_error msg
      | Failure msg ) ->
      Printf.eprintf "%s: cannot read financials: %s\n%!" path msg;
      false

let () =
  match List.tl (Array.to_list Sys.argv) with
  | [] ->
      prerr_string usage;
      exit 2
  | paths ->
      let ok = List.fold_left (fun ok path -> value path && ok) true paths in
      exit (if ok then 0 else 1)

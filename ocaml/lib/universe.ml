let allowed_fields = [ "ticker"; "entity_class"; "why"; "scope_limits"; "cik" ]
let required_fields = [ "ticker"; "entity_class"; "why" ]

let check_entry index (entry : Yojson.Safe.t) =
  match entry with
  | `Assoc fields ->
      let name =
        match List.assoc_opt "ticker" fields with Some (`String t) -> t | _ -> Printf.sprintf "entry %d" index
      in
      let unknown = List.filter (fun (k, _) -> not (List.mem k allowed_fields)) fields in
      if unknown <> [] then
        Error
          (Printf.sprintf "universe entry %s carries unknown field(s) %s; a universe entry is exactly %s" name
             (String.concat ", " (List.map fst unknown)) (String.concat ", " allowed_fields))
      else
        let missing =
          List.filter
            (fun k -> match List.assoc_opt k fields with Some (`String s) -> String.trim s = "" | _ -> true)
            required_fields
        in
        if missing <> [] then
          Error (Printf.sprintf "universe entry %s lacks %s" name (String.concat ", " missing))
        else
          let class_name = match List.assoc_opt "entity_class" fields with Some (`String c) -> c | _ -> "" in
          if Option.is_none (Admissibility.class_of_string class_name) then
            Error
              (Printf.sprintf "universe entry %s declares unknown class %S; one of: %s" name class_name
                 (String.concat ", " (List.map Admissibility.class_name Admissibility.all_classes)))
          else (
            match (List.assoc_opt "scope_limits" fields, List.assoc_opt "cik" fields) with
            | (None | Some (`List [])), (None | Some (`String _)) -> Ok ()
            | Some (`List items), (None | Some (`String _)) when List.for_all (function `String _ -> true | _ -> false) items -> Ok ()
            | _, Some _ -> Error (Printf.sprintf "universe entry %s: cik must be a string" name)
            | _ -> Error (Printf.sprintf "universe entry %s: scope_limits must be a list of strings" name))
  | _ -> Error (Printf.sprintf "universe entry %d is not an object" index)

let load_string text =
  match Yojson.Safe.from_string text with
  | exception Yojson.Json_error msg -> Error ("universe: " ^ msg)
  | `Assoc top -> (
      match List.assoc_opt "tickers" top with
      | Some (`List entries) -> (
          let rec go i = function
            | [] -> Ok ()
            | e :: rest -> ( match check_entry i e with Ok () -> go (i + 1) rest | Error _ as err -> err)
          in
          match go 1 entries with
          | Error msg -> Error msg
          | Ok () -> (
              match Reference_j.universe_of_string text with
              | u -> Ok u
              | exception Atdgen_runtime.Oj_run.Error msg -> Error ("universe: " ^ msg)))
      | _ -> Error "universe: no tickers list")
  | _ -> Error "universe: not an object"

let load path =
  match In_channel.with_open_bin path In_channel.input_all with
  | text -> Result.map_error (fun m -> path ^ ": " ^ m) (load_string text)
  | exception Sys_error msg -> Error msg

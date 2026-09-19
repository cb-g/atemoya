let fields = [ "premium_over_rf"; "why"; "as_of" ]

let check_entry name (json : Yojson.Safe.t) =
  match json with
  | `Assoc kv -> (
      let unknown = List.filter (fun (k, _) -> not (List.mem k fields)) kv in
      let missing = List.filter (fun k -> not (List.mem_assoc k kv)) fields in
      if unknown <> [] then
        Error
          (Printf.sprintf "required return %s carries unknown field(s) %s; an entry is exactly %s" name
             (String.concat ", " (List.map fst unknown)) (String.concat ", " fields))
      else if missing <> [] then Error (Printf.sprintf "required return %s lacks %s" name (String.concat ", " missing))
      else
        let number = match List.assoc "premium_over_rf" kv with `Float x -> Some x | `Int n -> Some (float_of_int n) | _ -> None in
        let text k = match List.assoc k kv with `String s -> Some s | _ -> None in
        match (number, text "why", text "as_of") with
        | Some _, Some why, Some as_of -> (
            if String.trim why = "" then Error (Printf.sprintf "required return %s: why is empty" name)
            else
              match Date.days_between ~from:as_of ~until:as_of with
              | Ok _ -> Ok ()
              | Error e -> Error (Printf.sprintf "required return %s: as_of: %s" name e))
        | _ -> Error (Printf.sprintf "required return %s: premium_over_rf must be a number, why and as_of strings" name))
  | _ -> Error (Printf.sprintf "required return %s is not an object" name)

let check_table ~key ~required text =
  match Yojson.Safe.from_string text with
  | exception Yojson.Json_error msg -> Error ("required returns: " ^ msg)
  | `Assoc top -> (
      match List.assoc_opt key top with
      | Some (`Assoc entries) ->
          List.fold_left (fun acc (name, json) -> match acc with Error _ -> acc | Ok () -> check_entry name json) (Ok ()) entries
      | None when not required -> Ok ()
      | _ -> Error (Printf.sprintf "required returns: no %s object" key))
  | _ -> Error "required returns: not an object"

let parse reader text =
  match reader text with v -> Ok v | exception Atdgen_runtime.Oj_run.Error msg -> Error ("required returns: " ^ msg)

let load_classes_string text =
  Result.bind (check_table ~key:"classes" ~required:true text) (fun () ->
      Result.bind (check_table ~key:"names" ~required:false text) (fun () ->
          parse Reference_j.required_returns_of_string text))

let load_names_string text =
  Result.bind (check_table ~key:"tickers" ~required:true text) (fun () -> parse Reference_j.name_required_returns_of_string text)

let read path loader =
  match In_channel.with_open_bin path In_channel.input_all with
  | text -> Result.map_error (fun m -> path ^ ": " ^ m) (loader text)
  | exception Sys_error msg -> Error msg

let load_classes path = read path load_classes_string
let load_names path = read path load_names_string

let version (r : Reference_t.required_return) ~source_kind =
  let key = Printf.sprintf "%.17g|%s|%s" r.premium_over_rf r.why r.as_of in
  Printf.sprintf "%s-%s-%s" r.as_of (String.sub (Digest.to_hex (Digest.string key)) 0 7) source_kind

let declared (r : Reference_t.required_return) ~source ~source_kind : Dcf.declared_return =
  { premium_over_rf = Float.round (r.premium_over_rf /. 100. *. 1e10) /. 1e10; source; version = version r ~source_kind }

let resolve (table : Reference_t.required_returns) ?(names : Reference_t.name_required_returns option) ~ticker ~entity_class () =
  let extra = Option.bind names (fun (n : Reference_t.name_required_returns) -> List.assoc_opt ticker n.tickers) in
  match (extra, List.assoc_opt ticker table.names, List.assoc_opt entity_class table.classes) with
  | Some r, _, _ -> Some (declared r ~source:"declared: name (--required-returns file)" ~source_kind:"name")
  | None, Some r, _ -> Some (declared r ~source:"declared: name" ~source_kind:"name")
  | None, None, Some r -> Some (declared r ~source:("declared: class " ^ entity_class) ~source_kind:"class")
  | None, None, None -> None

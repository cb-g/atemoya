let is_date d = match Date.days_between ~from:d ~until:d with Ok _ -> true | Error _ -> false

let dates_at_or_before ~dir ~today =
  (match Sys.readdir dir with d -> Array.to_list d | exception Sys_error _ -> [])
  |> List.filter (fun d -> Sys.is_directory (Filename.concat dir d) && is_date d && d <= today)
  |> List.sort (fun a b -> compare b a)

let within ~today ~max_age_days d =
  match Date.days_between ~from:d ~until:today with Ok n -> n <= max_age_days | Error _ -> false

let snapshot_dates ~dir ~today ?max_age_days () =
  let all = dates_at_or_before ~dir ~today in
  match max_age_days with None -> all | Some n -> List.filter (within ~today ~max_age_days:n) all

let path dir d ticker = Filename.concat (Filename.concat dir d) (ticker ^ ".json")

let all_dates ~dir =
  (match Sys.readdir dir with d -> Array.to_list d | exception Sys_error _ -> [])
  |> List.filter (fun d -> Sys.is_directory (Filename.concat dir d) && is_date d)

let lookup ~dir ~today ?max_age_days ticker =
  let all = dates_at_or_before ~dir ~today in
  (* Under a window, a name the store holds on any date at all (before or after today) but
     not within the window carries the window's reason: on the panel, the dates before the
     archive begins say so rather than "no options data", which is kept for a name the
     store never holds. *)
  let present =
    match max_age_days with
    | Some _ -> List.filter (fun d -> Sys.file_exists (path dir d ticker)) (all_dates ~dir)
    | None -> List.filter (fun d -> Sys.file_exists (path dir d ticker)) all
  in
  let usable =
    match max_age_days with
    | None -> present
    | Some n -> List.filter (fun d -> d <= today && within ~today ~max_age_days:n d) present
  in
  match (usable, present, max_age_days) with
  | d :: _, _, _ -> (
      let file = path dir d ticker in
      match Atdgen_runtime.Util.Json.from_file Boundary_j.read_option_chain file with
      | chain -> Ok chain
      | exception (Yojson.Json_error msg | Atdgen_runtime.Oj_run.Error msg | Sys_error msg | Failure msg) ->
          Error (Printf.sprintf "unreadable option chain %s: %s" file msg))
  | [], _ :: _, Some n -> Error (Printf.sprintf "no options snapshot within %d days before %s" n today)
  | [], _, _ -> Error "no options data"

open Boundary_t

let status_name = function `Ok -> "Ok" | `Failed -> "Failed"
let signal_name = function `Buy -> "Buy" | `Hold -> "Hold" | `Sell -> "Sell"

let model_label = function
  | Some m -> Classify.model_name m
  | None -> "unresolved"

let starts_with ~prefix s =
  String.length s >= String.length prefix
  && String.sub s 0 (String.length prefix) = prefix

let reason_key reason =
  let rec find i =
    if i + 1 >= String.length reason then None
    else if reason.[i] = ' ' && reason.[i + 1] = '(' then Some i
    else find (i + 1)
  in
  match find 0 with Some i -> String.sub reason 0 i | None -> reason

let meets_expectation (e : Reference_t.universe_entry) (v : valuation) =
  status_name v.status = e.expected_status
  &&
  match (e.expected_reason, v.failed_reason) with
  | None, _ -> true
  | Some prefix, Some reason -> starts_with ~prefix reason
  | Some _, None -> false

(* Counts by key, most frequent first, ties by key. *)
let count_by key items =
  let tally =
    List.fold_left
      (fun acc x ->
        let k = key x in
        match List.assoc_opt k acc with
        | Some c -> (k, c + 1) :: List.remove_assoc k acc
        | None -> (k, 1) :: acc)
      [] items
  in
  List.stable_sort
    (fun (ka, a) (kb, b) -> if a <> b then compare b a else compare ka kb)
    tally

let summary ?universe (vs : valuation list) =
  let b = Buffer.create 4096 in
  let n = List.length vs in
  let ok = List.length (List.filter (fun v -> v.status = `Ok) vs) in
  let valued_on = match vs with v :: _ -> v.valued_on | [] -> "-" in
  Printf.bprintf b "valued_on %s: %d records, %d Ok, %d Failed\n\n" valued_on n
    ok (n - ok);
  Printf.bprintf b "by model: %s\n\n"
    (String.concat ", "
       (List.map
          (fun (k, c) -> Printf.sprintf "%s %d" k c)
          (count_by (fun v -> model_label v.model) vs)));
  let reasons =
    List.filter_map
      (fun v ->
        match (v.status, v.failed_reason) with
        | `Failed, Some r -> Some (reason_key r)
        | _ -> None)
      vs
  in
  Printf.bprintf b "Failed by reason:\n";
  List.iter
    (fun (k, c) -> Printf.bprintf b "  %3d  %s\n" c k)
    (count_by Fun.id reasons);
  Printf.bprintf b "\nper ticker%s:\n"
    (if Option.is_some universe then " (expected from the universe file)"
     else "");
  List.iter
    (fun v ->
      let detail =
        match (v.status, v.fair_value, v.price, v.margin_of_safety, v.signal) with
        | `Ok, Some fv, Some p, Some mos, Some s ->
            Printf.sprintf "fair_value %.2f  price %.2f  mos %+.2f  %s" fv p mos
              (signal_name s)
        | _ -> Option.value v.failed_reason ~default:""
      in
      let verdict =
        match universe with
        | None -> ""
        | Some (u : Reference_t.universe) -> (
            match
              List.find_opt
                (fun (e : Reference_t.universe_entry) -> e.ticker = v.ticker)
                u.tickers
            with
            | None -> "  [not in universe]"
            | Some e ->
                if meets_expectation e v then "  as expected"
                else
                  Printf.sprintf "  EXPECTED %s%s" e.expected_status
                    (match e.expected_reason with
                    | Some r -> " " ^ r
                    | None -> ""))
      in
      Printf.bprintf b "  %-10s %-7s %-10s %s%s\n" v.ticker
        (status_name v.status) (model_label v.model) detail verdict)
    vs;
  (match universe with
  | Some (u : Reference_t.universe) ->
      let missing =
        List.filter
          (fun (e : Reference_t.universe_entry) ->
            not (List.exists (fun (v : valuation) -> v.ticker = e.ticker) vs))
          u.tickers
      in
      if missing <> [] then
        Printf.bprintf b "\nin the universe but not run: %s\n"
          (String.concat ", "
             (List.map (fun (e : Reference_t.universe_entry) -> e.ticker) missing))
  | None -> ());
  Buffer.contents b

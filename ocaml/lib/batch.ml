open Boundary_t

let status_name = function `Ok -> "Ok" | `Failed -> "Failed"
let signal_name = function `Buy -> "Buy" | `Hold -> "Hold" | `Sell -> "Sell"

let class_label = function
  | Some c -> Admissibility.class_name c
  | None -> "undeclared"

let starts_with ~prefix s =
  String.length s >= String.length prefix
  && String.sub s 0 (String.length prefix) = prefix

let cut_at reason marker =
  let n = String.length marker in
  let rec find i =
    if i + n > String.length reason then None
    else if String.sub reason i n = marker then Some i
    else find (i + 1)
  in
  match find 0 with Some i -> String.sub reason 0 i | None -> reason

let reason_key reason = cut_at (cut_at reason " (") "; lens:"

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
  Printf.bprintf b "by class: %s\n\n"
    (String.concat ", "
       (List.map
          (fun (k, c) -> Printf.sprintf "%s %d" k c)
          (count_by (fun v -> class_label v.entity_class) vs)));
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
  let checked = List.filter (fun (v : valuation) -> Option.is_some v.cross_check) vs in
  let disagreeing =
    List.filter
      (fun (v : valuation) ->
        match v.cross_check with Some c -> c.disagreements > 0 | None -> false)
      checked
  in
  if checked <> [] then begin
    let fields =
      List.concat_map
        (fun (v : valuation) ->
          match v.cross_check with
          | Some c ->
              List.filter_map
                (fun (f : field_check) -> if f.agree = Some false then Some f.field else None)
                c.fields
          | None -> [])
        disagreeing
    in
    Printf.bprintf b "\ncross-check: %d of %d filed-statement records disagree with the vendor beyond threshold on some field%s\n"
      (List.length disagreeing) (List.length checked)
      (match count_by Fun.id fields with
      | [] -> ""
      | tally ->
          "; most often: "
          ^ String.concat ", " (List.map (fun (k, c) -> Printf.sprintf "%s (%d)" k c) tally))
  end;
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
      Printf.bprintf b "  %-10s %-7s %-18s %s%s\n" v.ticker
        (status_name v.status) (class_label v.entity_class) detail verdict)
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

let fair_value_text = function Some fv -> Printf.sprintf "%.2f" fv | None -> "none"

let provider_diff pairs =
  let b = Buffer.create 4096 in
  Printf.bprintf b "provider diff: filed statements (primary) against the vendor's (shadow), same model and parameters\n\n";
  List.iter
    (fun ((v : valuation), shadow) ->
      match shadow with
      | None ->
          Printf.bprintf b "%-10s unchanged (statements from %s%s)\n" v.ticker v.statements_provider
            (if v.provider_reason = "" then "" else ": " ^ v.provider_reason)
      | Some (s : valuation) ->
          let delta =
            match (v.fair_value, s.fair_value) with
            | Some n, Some o -> Printf.sprintf "%+.2f (%+.1f%%)" (n -. o) ((n -. o) /. o *. 100.)
            | _ -> "n/a"
          in
          Printf.bprintf b "%-10s %s -> %s: old %s (%s) new %s (%s), delta %s\n" v.ticker
            s.statements_provider v.statements_provider (fair_value_text s.fair_value)
            (status_name s.status) (fair_value_text v.fair_value) (status_name v.status) delta;
          (match (v.status, v.failed_reason) with
          | `Failed, Some r -> Printf.bprintf b "           new: %s\n" r
          | _ -> ());
          (match (s.status, s.failed_reason) with
          | `Failed, Some r -> Printf.bprintf b "           old: %s\n" r
          | _ -> ());
          (match v.cross_check with
          | None -> Printf.bprintf b "           no cross-check on the record\n"
          | Some c ->
              let ranked =
                List.filter (fun (f : field_check) -> Option.is_some f.relative_difference) c.fields
                |> List.sort (fun (a : field_check) (b : field_check) ->
                       compare b.relative_difference a.relative_difference)
              in
              let top = List.filteri (fun i _ -> i < 3) ranked in
              let missing =
                List.filter (fun (f : field_check) -> f.primary = None && f.secondary <> None) c.fields
              in
              List.iter
                (fun (f : field_check) ->
                  Printf.bprintf b "           %-26s filed %s  vendor %s  differ %s\n" f.field
                    (fair_value_text f.primary) (fair_value_text f.secondary)
                    (match f.relative_difference with Some d -> Printf.sprintf "%.1f%%" (d *. 100.) | None -> "-"))
                top;
              if missing <> [] then
                Printf.bprintf b "           absent from the filing, present at the vendor: %s\n"
                  (String.concat ", " (List.map (fun (f : field_check) -> f.field) missing))))
    pairs;
  Buffer.contents b

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

let money x =
  if Float.abs x >= 1e6 then Printf.sprintf "%.1fm" (x /. 1e6) else Printf.sprintf "%.4g" x

let composition_text = function
  | None -> ""
  | Some (c : composition) ->
      Printf.sprintf " [%s: %s]" c.definition
        (String.concat " + "
           (List.map
              (fun (k : component) -> Printf.sprintf "%s %s (%s)" k.name (money k.value) k.row)
              c.components))

(* The cross-checked fields the routed model reads; a flag elsewhere moves no number. *)
let model_reads (m : model option) =
  match m with
  | Some `Dcf ->
      [ "total_revenue"; "ebit"; "pretax_income"; "tax_provision"; "depreciation_amortization"; "capex";
        "delta_nwc"; "cash"; "total_debt"; "book_equity" ]
  | Some `Residual_income | Some `Residual_income_insurer -> [ "book_equity"; "net_income"; "dividends_paid" ]
  | None -> []

let flagged_fields (v : valuation) =
  match v.cross_check with
  | Some c -> List.filter_map (fun (f : field_check) -> if f.agree = Some false then Some f.field else None) c.fields
  | None -> []

let entry_of universe ticker =
  Option.bind universe (fun (u : Reference_t.universe) ->
      List.find_opt (fun (e : Reference_t.universe_entry) -> e.ticker = ticker) u.tickers)

let summary ?universe ?definitions (vs : valuation list) =
  let b = Buffer.create 4096 in
  let n = List.length vs in
  let ok = List.length (List.filter (fun v -> v.status = `Ok) vs) in
  let valued_on = match vs with v :: _ -> v.valued_on | [] -> "-" in
  Printf.bprintf b "valued_on %s: %d records, %d Ok, %d Failed\n\n" valued_on n
    ok (n - ok);
  (match definitions with
  | Some (d : Reference_t.field_definitions) ->
      Printf.bprintf b
        "field definitions (reference/field_definitions.json, as_of %s): cash = %s; total_debt = %s; delta_nwc = %s; ebit = %s\n\n"
        d.as_of
        (d.cash : Reference_t.cash_definition).name
        (d.total_debt : Reference_t.debt_definition).name
        (d.delta_nwc : Reference_t.nwc_definition).name
        (d.ebit : Reference_t.ebit_definition).name
  | None -> ());
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
          ^ String.concat ", " (List.map (fun (k, c) -> Printf.sprintf "%s (%d)" k c) tally));
    let material =
      List.filter
        (fun (v : valuation) -> List.exists (fun f -> List.mem f (model_reads v.model)) (flagged_fields v))
        disagreeing
    in
    Printf.bprintf b "  on a field the routed model reads: %d of %d%s\n" (List.length material) (List.length checked)
      (match material with
      | [] -> ""
      | vs -> " (" ^ String.concat ", " (List.map (fun (v : valuation) -> v.ticker) vs) ^ ")");
    List.iter
      (fun (v : valuation) ->
        match v.cross_check with
        | None -> ()
        | Some c ->
            let flagged = List.filter (fun (f : field_check) -> f.agree = Some false) c.fields in
            Printf.bprintf b "  %-10s %s\n" v.ticker
              (String.concat "; "
                 (List.map
                    (fun (f : field_check) ->
                      Printf.sprintf "%s filed %s vendor %s (%.1f%%)" f.field
                        (match f.primary with Some x -> money x | None -> "none")
                        (match f.secondary with Some x -> money x | None -> "none")
                        (match f.relative_difference with Some d -> d *. 100. | None -> 0.))
                    flagged));
            let read = List.filter (fun f -> List.mem f (model_reads v.model)) (flagged_fields v) in
            Printf.bprintf b "             %s\n"
              (match read with
              | [] -> "none of these is an input of the routed model"
              | fs -> "read by the model: " ^ String.concat ", " fs);
            let note =
              match entry_of universe v.ticker with
              | Some (e : Reference_t.universe_entry) when e.cross_check_note <> "" -> e.cross_check_note
              | _ -> "uncharacterised"
            in
            Printf.bprintf b "             %s\n" note)
      disagreeing
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
        | Some _ -> (
            match entry_of universe v.ticker with
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

let parameter_drivers (ps : (string * parameter) list) =
  List.map (fun (name, (p : parameter)) -> (name, p.value, "")) ps

let residual_income_drivers (i : residual_income_inputs) =
  [
    ("price", i.price, "");
    ("market_cap", i.market_cap, "");
    ("shares", i.shares, "");
    ("book_equity", i.book_equity, "");
    ("net_income", i.net_income, "");
    ("roe_0", i.roe_0, "");
    ("payout_ratio", i.payout_ratio, "");
  ]
  @ (match i.dividends_paid with
    | Some d -> [ ("dividends_paid", d, match i.dividends_paid_row with Some r -> " (" ^ r ^ ")" | None -> "") ]
    | None -> [])
  @ parameter_drivers
      ([
         ("risk_free_rate", i.risk_free_rate);
         ("equity_risk_premium", i.equity_risk_premium);
         ("beta", i.beta);
         ("mean_reversion_lambda", i.mean_reversion_lambda);
         ("terminal_growth_rate", i.terminal_growth_rate);
         ("terminal_roe_spread", i.terminal_roe_spread);
       ]
      @ match i.country_risk_premium with Some c -> [ ("country_risk_premium", c) ] | None -> [])
  @ [ ("projection_years", float_of_int i.projection_years.value, "") ]

let drivers (inputs : model_inputs) =
  match inputs with
  | `Dcf (i : inputs) ->
      [
        ("price", i.price, "");
        ("market_cap", i.market_cap, "");
        ("shares", i.shares, "");
        ( "ebit",
          i.ebit,
          (match i.ebit_recipe with Some r -> " recipe " ^ r | None -> "")
          ^ composition_text i.ebit_composition );
        ("tax_rate", i.tax_rate, "");
        ( "depreciation_amortization",
          i.depreciation_amortization,
          match i.depreciation_amortization_row with Some r -> " (" ^ r ^ ")" | None -> "" );
        ("capex", i.capex, "");
        ( "delta_nwc",
          i.delta_nwc,
          Printf.sprintf " mean over %s" (String.concat ", " i.delta_nwc_periods)
          ^ String.concat "" (List.map composition_text i.delta_nwc_compositions) );
        ("cash", i.cash, composition_text i.cash_composition);
        ( "total_debt",
          i.total_debt,
          (match i.total_debt_source with Some r -> " (" ^ r ^ ")" | None -> "")
          ^ composition_text i.total_debt_composition );
        ("book_equity", i.book_equity, "");
      ]
      @ parameter_drivers
          ([
             ("statutory_tax_rate", i.statutory_tax_rate);
             ("risk_free_rate", i.risk_free_rate);
             ("equity_risk_premium", i.equity_risk_premium);
             ("beta", i.beta);
             ("debt_spread", i.debt_spread);
             ("growth_clamp_lower", i.growth_clamp_lower);
             ("growth_clamp_upper", i.growth_clamp_upper);
             ("mean_reversion_lambda", i.mean_reversion_lambda);
             ("terminal_growth_rate", i.terminal_growth_rate);
           ]
          @ match i.country_risk_premium with Some c -> [ ("country_risk_premium", c) ] | None -> [])
      @ [ ("projection_years", float_of_int i.projection_years.value, "") ]
  | `Residual_income i -> residual_income_drivers i
  | `Residual_income_insurer (i : insurer_inputs) ->
      residual_income_drivers i.core
      @ [ ("reported_book_equity", i.reported_book_equity, ""); ("aoci", i.aoci, "") ]

let differs a b =
  let scale = Float.max (Float.abs a) (Float.abs b) in
  scale > 0. && Float.abs (a -. b) /. scale > 1e-9

let status_value (v : valuation) =
  Printf.sprintf "%s %s" (status_name v.status) (fair_value_text v.fair_value)

let run_diff ~baseline (vs : valuation list) =
  let b = Buffer.create 8192 in
  let base_on = match baseline with v :: _ -> v.valued_on | [] -> "-" in
  let this_on = match vs with v :: _ -> v.valued_on | [] -> "-" in
  Printf.bprintf b
    "run diff: this run (valued_on %s) against the baseline run (valued_on %s): every record, and for every moved fair value the inputs that moved\n\n"
    this_on base_on;
  let moved = ref 0 and unexplained = ref 0 and status_changed = ref 0 in
  List.iter
    (fun (v : valuation) ->
      match List.find_opt (fun (o : valuation) -> o.ticker = v.ticker) baseline with
      | None -> Printf.bprintf b "%-10s new: %s; not in the baseline\n" v.ticker (status_value v)
      | Some o ->
          let delta =
            match (v.fair_value, o.fair_value) with
            | Some n, Some p when differs n p ->
                Printf.sprintf " delta %+.2f (%+.1f%%)" (n -. p) ((n -. p) /. p *. 100.)
            | Some _, Some _ -> " unchanged"
            | _ -> ""
          in
          let fv_moved =
            match (v.fair_value, o.fair_value) with
            | Some n, Some p -> differs n p
            | None, None -> false
            | _ -> true
          in
          if v.status <> o.status then incr status_changed;
          if fv_moved then incr moved;
          Printf.bprintf b "%-10s %s -> %s%s; statements %s -> %s\n" v.ticker (status_value o)
            (status_value v) delta o.statements_provider v.statements_provider;
          (match (o.status, o.failed_reason) with
          | `Failed, Some r -> Printf.bprintf b "           was: %s\n" r
          | _ -> ());
          (match (v.status, v.failed_reason) with
          | `Failed, Some r -> Printf.bprintf b "           now: %s\n" r
          | _ -> ());
          let inputs_of (x : valuation) = Option.map drivers x.inputs in
          (match (inputs_of o, inputs_of v) with
          | Some od, Some nd ->
              let changed =
                List.filter_map
                  (fun (name, nv, ntext) ->
                    match List.find_opt (fun (n, _, _) -> n = name) od with
                    | Some (_, ov, otext) when differs ov nv -> Some (name, Some (ov, otext), (nv, ntext))
                    | Some _ -> None
                    | None -> Some (name, None, (nv, ntext)))
                  nd
              in
              List.iter
                (fun (name, old, (nv, ntext)) ->
                  Printf.bprintf b "           %-26s %s -> %s%s\n" name
                    (match old with Some (ov, otext) -> money ov ^ otext | None -> "absent")
                    (money nv) ntext)
                changed;
              if fv_moved && changed = [] then begin
                incr unexplained;
                Printf.bprintf b
                  "           NO DRIVER: no input or parameter differs; the model arithmetic itself changed, or this is a bug\n"
              end
          | None, Some nd ->
              Printf.bprintf b "           inputs now present (%s):\n"
                (match v.inputs with
                | Some (`Dcf _) -> "dcf"
                | Some (`Residual_income _) -> "residual_income"
                | Some (`Residual_income_insurer _) -> "residual_income_insurer"
                | None -> "-");
              List.iter
                (fun (name, nv, ntext) ->
                  if List.mem name [ "ebit"; "delta_nwc"; "cash"; "total_debt"; "dividends_paid"; "book_equity"; "net_income" ] then
                    Printf.bprintf b "           %-26s %s%s\n" name (money nv) ntext)
                nd
          | Some _, None -> Printf.bprintf b "           inputs no longer computed\n"
          | None, None -> ()))
    vs;
  List.iter
    (fun (o : valuation) ->
      if not (List.exists (fun (v : valuation) -> v.ticker = o.ticker) vs) then
        Printf.bprintf b "%-10s in the baseline (%s), not in this run\n" o.ticker (status_value o))
    baseline;
  Printf.bprintf b "\n%d of %d fair values moved, %d status changes, %d moved without a driver\n"
    !moved (List.length vs) !status_changed !unexplained;
  Buffer.contents b

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

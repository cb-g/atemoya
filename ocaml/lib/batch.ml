open Boundary_t

let status_name = function `Ok -> "Ok" | `Failed -> "Failed"
let signal_name = function `Buy -> "Buy" | `Hold -> "Hold" | `Sell -> "Sell"

let class_label = function
  | Some c -> Admissibility.class_name c
  | None -> "undeclared"

let contains haystack needle =
  let n = String.length needle and h = String.length haystack in
  let rec go i = i + n <= h && (String.sub haystack i n = needle || go (i + 1)) in
  n = 0 || go 0

let cut_at reason marker =
  let n = String.length marker in
  let rec find i =
    if i + n > String.length reason then None
    else if String.sub reason i n = marker then Some i
    else find (i + 1)
  in
  match find 0 with Some i -> String.sub reason 0 i | None -> reason

let reason_key reason = cut_at (cut_at reason " (") "; lens:"

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
  | Some `Dcf_midcycle -> [ "net_income"; "depreciation_amortization"; "capex"; "delta_nwc"; "cash"; "total_debt"; "book_equity" ]
  | Some `Residual_income | Some `Residual_income_insurer -> [ "book_equity"; "net_income"; "dividends_paid" ]
  | Some `Reit_ffo_dividend -> [ "net_income"; "depreciation_amortization"; "dividends_paid" ]
  | None -> []

let flagged_fields (v : valuation) =
  match v.cross_check with
  | Some c -> List.filter_map (fun (f : field_check) -> if f.agree = Some false then Some f.field else None) c.fields
  | None -> []

let version_of (vs : valuation list) =
  match vs with { model_version = ""; _ } :: _ | [] -> "unrecorded" | v :: _ -> v.model_version

let summary ?universe ?definitions ?stability_line ?run_dir (vs : valuation list) =
  let b = Buffer.create 4096 in
  let n = List.length vs in
  let ok = List.length (List.filter (fun v -> v.status = `Ok) vs) in
  let valued_on = match vs with v :: _ -> v.valued_on | [] -> "-" in
  Printf.bprintf b "valued_on %s, model_version %s: %d records, %d Ok, %d Failed\n\n" valued_on (version_of vs) n
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
            (* A finding: field, filed value, vendor value, relative difference, and nothing
               else. Never resolved by the run and never explained by a note. *)
            let flagged = List.filter (fun (f : field_check) -> f.agree = Some false) c.fields in
            Printf.bprintf b "  %-10s %s\n" v.ticker
              (String.concat "; "
                 (List.map
                    (fun (f : field_check) ->
                      Printf.sprintf "%s filed %s vendor %s (%.1f%%)" f.field
                        (match f.primary with Some x -> money x | None -> "none")
                        (match f.secondary with Some x -> money x | None -> "none")
                        (match f.relative_difference with Some d -> d *. 100. | None -> 0.))
                    flagged)))
      disagreeing
  end;
  (* What the market needs to be true, across the Ok names. *)
  let implied = List.filter_map (fun (v : valuation) -> v.implied) vs in
  if implied <> [] then begin
    let half_lives =
      List.filter_map (fun (i : implied) -> i.half_life_years.value) implied |> List.sort compare
    in
    let n = List.length half_lives in
    let median =
      if n = 0 then None
      else if n mod 2 = 1 then Some (List.nth half_lives (n / 2))
      else Some (0.5 *. (List.nth half_lives ((n / 2) - 1) +. List.nth half_lives (n / 2)))
    in
    let count_reason needle =
      List.length
        (List.filter
           (fun (i : implied) ->
             match i.half_life_years.reason with Some r -> contains r needle | None -> false)
           implied)
    in
    let never_decay = count_reason "would have to never decay" in
    let below_no_growth = count_reason "price is below the no-" in
    let horizons =
      List.filter_map (fun (i : implied) -> Option.bind i.horizon_years (fun (r : readout) -> r.value)) implied
      |> List.sort compare
    in
    let hn = List.length horizons in
    let hmedian =
      if hn = 0 then None
      else if hn mod 2 = 1 then Some (List.nth horizons (hn / 2))
      else Some (0.5 *. (List.nth horizons ((hn / 2) - 1) +. List.nth horizons (hn / 2)))
    in
    let under_guard = List.length (List.filter (fun (i : implied) -> Option.is_some i.fair_value_at_40) implied) in
    let beyond_40 =
      List.length
        (List.filter
           (fun (i : implied) ->
             match Option.bind i.horizon_years (fun (r : readout) -> r.reason) with
             | Some r -> contains r "even indefinite persistence"
             | None -> false)
           implied)
    in
    let level_guard = List.length (List.filter (fun (i : implied) -> i.meaningful_readout = "level" && Option.is_none i.fair_value_at_40) implied) in
    let level_beyond = List.length (List.filter (fun (i : implied) -> i.meaningful_readout = "level" && Option.is_some i.fair_value_at_40) implied) in
    Printf.bprintf b "\nimplied horizon, across %d Ok names under the guard (start above its target): %s; %d beyond 40 years (even indefinite persistence of the decaying path does not reach the price); level is the meaningful readout for %d (%d guard failed, %d beyond 40)\n"
      under_guard
      (match hmedian with
      | Some m -> Printf.sprintf "median %.0f years (range %.0f to %.0f, %d solved)" m (List.hd horizons) (List.nth horizons (hn - 1)) hn
      | None -> "none solved")
      beyond_40 (level_guard + level_beyond) level_guard level_beyond;
    let binding =
      count_by (fun x -> x)
        (List.filter_map
           (fun (v : valuation) -> Option.bind v.sensitivity (fun (s : sensitivity) -> s.binding_input))
           vs)
    in
    Printf.bprintf b "sensitivity (23), the binding input across %d Ok names for the declared steps: %s\n"
      (List.length (List.filter (fun (v : valuation) -> Option.is_some v.sensitivity) vs))
      (match binding with
      | [] -> "none"
      | xs -> String.concat ", " (List.map (fun (name, n) -> Printf.sprintf "%s %d" name n) xs));
    let probabilities =
      List.filter_map (fun (v : valuation) -> Option.map (fun (r : belief_readout) -> r.probability_overpaid) v.belief) vs
      |> List.sort compare
    in
    let np = List.length probabilities in
    let no_belief = List.filter (fun (v : valuation) -> v.status = `Ok && Option.is_none v.belief) vs in
    let readouts = List.filter_map (fun (v : valuation) -> v.belief) vs in
    let at_one = List.filter (fun (r : belief_readout) -> r.probability_overpaid >= 1.) readouts in
    let past_rate = List.filter (fun (r : belief_readout) -> Option.is_some r.probability_reason) at_one in
    Printf.bprintf b
      "probability_overpaid (24), across %d Ok names with a declared belief: %s; at 1.0: %d (%d where the price needs long-run growth at or above the discount rate, %d where the implied long-run growth is at or above the belief's ceiling); no belief on %d Ok names (%s)\n"
      np
      (if np = 0 then "none"
       else
         Printf.sprintf "median %.2f, range %.2f to %.2f" (List.nth probabilities (np / 2)) (List.hd probabilities)
           (List.nth probabilities (np - 1)))
      (List.length at_one) (List.length past_rate) (List.length at_one - List.length past_rate)
      (List.length no_belief)
      (String.concat "; "
         (List.map (fun (r, n) -> Printf.sprintf "%d %s" n r)
            (count_by (fun x -> x) (List.filter_map (fun (v : valuation) -> v.belief_reason) no_belief))));
    Printf.bprintf b "implied half-life, across %d Ok names: %s; beyond range: %d would need growth or roe that never decays, %d priced below the no-growth value; level is the meaningful readout for %d (start at or below its target)\n"
      (List.length implied)
      (match (median, half_lives) with
      | Some m, _ :: _ ->
          Printf.sprintf "median %.1f years (range %.1f to %.1f, %d solved)" m (List.hd half_lives)
            (List.nth half_lives (n - 1)) n
      | _ -> "none solved")
      never_decay below_no_growth level_guard
  end;
  (match stability_line with Some l -> Printf.bprintf b "\n%s\n" l | None -> ());
  Printf.bprintf b "\nper ticker:\n";
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
        | Some (u : Reference_t.universe)
          when not (List.exists (fun (e : Reference_t.universe_entry) -> e.ticker = v.ticker) u.tickers) ->
            "  [not in universe]"
        | _ -> ""
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
  Option.iter (fun d -> Printf.bprintf b "\nrun written to %s\n" d) run_dir;
  Buffer.contents b

let dated_run_dir ~exists ~root valued_on =
  let first = Filename.concat root valued_on in
  if not (exists first) then first
  else
    let rec go n =
      let candidate = Filename.concat root (Printf.sprintf "%s-%d" valued_on n) in
      if exists candidate then go (n + 1) else candidate
    in
    go 2

let fair_value_text = function Some fv -> Printf.sprintf "%.2f" fv | None -> "none"

(* The cross-currency rate is an input too. *)
let conversion_driver = function
  | Some (c : conversion) -> [ ("fx_rate", c.fx_rate, Printf.sprintf " (%s, as_of %s)" c.fx_source c.fx_as_of) ]
  | None -> []

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
       ]
      @ match i.country_risk_premium with Some c -> [ ("country_risk_premium", c) ] | None -> [])
  @ [ ("projection_years", float_of_int i.projection_years.value, "") ]

let rec drivers (inputs : model_inputs) =
  match inputs with
  | `Dcf_midcycle (m : midcycle_inputs) ->
      (* The through-cycle aggregates are what the fair value moves with; the window's
         period fields sit behind them on the record. *)
      [
        ( "roic_mid",
          m.roic_mid,
          Printf.sprintf " mean over %d observations, window %s to %s" (List.length m.observations)
            (List.nth m.window (List.length m.window - 1)) (List.hd m.window) );
        ("reinvestment_rate_mid", m.reinvestment_rate_mid, Printf.sprintf " (%.4g / %.4g over %d periods)" m.reinvestment_sum m.nopat_sum (List.length m.reinvestment_periods));
        ("invested_capital_latest", m.invested_capital_latest, "");
        ( "fcff_mid",
          m.fcff_mid,
          match (m.spot_fcff, m.spot_to_midcycle) with
          | Some s, Some r -> Printf.sprintf " (spot fcff %.4g, %.2fx)" s r
          | _ -> " (no spot fcff: " ^ Option.value m.spot_reason ~default:"" ^ ")" );
      ]
      @ List.filter (fun (n, _, _) -> not (List.mem n [ "ebit"; "tax_rate"; "depreciation_amortization"; "capex"; "delta_nwc" ])) (drivers (`Dcf m.dcf))
      @ [ ("midcycle_window_years", float_of_int m.midcycle_window_years.value, "") ]
  | `Dcf (i : inputs) ->
      let flow name value text = match value with Some v -> [ (name, v, text) ] | None -> [] in
      [ ("price", i.price, ""); ("market_cap", i.market_cap, ""); ("shares", i.shares, "") ]
      @ flow "ebit" i.ebit
          ((match i.ebit_recipe with Some r -> " recipe " ^ r | None -> "") ^ composition_text i.ebit_composition)
      @ [ ("tax_rate", i.tax_rate, "") ]
      @ flow "depreciation_amortization" i.depreciation_amortization
          (match i.depreciation_amortization_row with Some r -> " (" ^ r ^ ")" | None -> "")
      @ flow "capex" i.capex ""
      @ flow "delta_nwc" i.delta_nwc
          (Printf.sprintf " mean over %s" (String.concat ", " i.delta_nwc_periods)
          ^ String.concat "" (List.map composition_text i.delta_nwc_compositions))
      @ [
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
      @ conversion_driver i.conversion
  | `Residual_income i -> residual_income_drivers i @ conversion_driver i.conversion
  | `Residual_income_insurer (i : insurer_inputs) ->
      residual_income_drivers i.core
      @ [ ("reported_book_equity", i.reported_book_equity, ""); ("aoci", i.aoci, "") ]
      @ conversion_driver i.core.conversion
  | `Reit_ffo_dividend (i : reit_inputs) ->
      [
        ("price", i.price, "");
        ("market_cap", i.market_cap, "");
        ("shares", i.shares, "");
        ("ffo", i.ffo, composition_text i.ffo_composition);
        ("dividends_paid", i.dividends_paid, match i.dividends_paid_row with Some r -> " (" ^ r ^ ")" | None -> "");
        ("covered_dividend", i.covered_dividend, Printf.sprintf " (coverage %.3f)" i.coverage);
        ("g_historical", i.g_historical, Printf.sprintf " (ffo per weighted-average share over %s)" (String.concat ", " i.ffo_periods));
      ]
      @ parameter_drivers
          ([
             ("risk_free_rate", i.risk_free_rate);
             ("equity_risk_premium", i.equity_risk_premium);
             ("beta", i.beta);
             ("growth_clamp_lower", i.growth_clamp_lower);
             ("growth_clamp_upper", i.growth_clamp_upper);
             ("mean_reversion_lambda", i.mean_reversion_lambda);
             ("terminal_growth_rate", i.terminal_growth_rate);
           ]
          @ match i.country_risk_premium with Some c -> [ ("country_risk_premium", c) ] | None -> [])
      @ [ ("projection_years", float_of_int i.projection_years.value, "") ]
      @ conversion_driver i.conversion

let differs a b =
  let scale = Float.max (Float.abs a) (Float.abs b) in
  scale > 0. && Float.abs (a -. b) /. scale > 1e-9

let status_value (v : valuation) =
  Printf.sprintf "%s %s%s" (status_name v.status) (fair_value_text v.fair_value)
    (match v.signal with Some s -> " " ^ signal_name s | None -> "")

(* The input fields a baseline record carried that the current record type no longer has:
   a model that lost a term names it here, with the value it had. *)
let removed_inputs ~(baseline_raw : (string * Yojson.Safe.t) list) (v : valuation) =
  match (List.assoc_opt v.ticker baseline_raw, v.inputs) with
  | Some (`Assoc old), Some inputs -> (
      match (List.assoc_opt "inputs" old, Yojson.Safe.from_string (Boundary_j.string_of_model_inputs inputs)) with
      | Some (`List [ _; `Assoc old_fields ]), `List [ _; `Assoc new_fields ] ->
          List.filter_map
            (fun (k, value) ->
              if List.mem_assoc k new_fields then None
              else
                match value with
                | `Float f -> Some (k, money f)
                | `Int n -> Some (k, string_of_int n)
                | `Assoc fields -> (
                    (* a parameter: its value and source *)
                    match (List.assoc_opt "value" fields, List.assoc_opt "source" fields) with
                    | Some (`Float f), Some (`String src) -> Some (k, Printf.sprintf "%s (%s)" (money f) src)
                    | _ -> Some (k, Yojson.Safe.to_string value))
                | other -> Some (k, Yojson.Safe.to_string other))
            old_fields
      | _ -> [])
  | _ -> []

let run_diff ?(baseline_raw = []) ~baseline (vs : valuation list) =
  let b = Buffer.create 8192 in
  let base_on = match baseline with v :: _ -> v.valued_on | [] -> "-" in
  let this_on = match vs with v :: _ -> v.valued_on | [] -> "-" in
  let this_version = version_of vs and base_version = version_of baseline in
  Printf.bprintf b
    "run diff: this run (valued_on %s, model_version %s) against the baseline run (valued_on %s, model_version %s): every record, and for every moved fair value the inputs that moved\n\n"
    this_on this_version base_on base_version;
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
          (* Two runs under different beliefs are different runs (24). *)
          if o.belief_version <> v.belief_version then
            Printf.bprintf b "           belief_version %s -> %s\n"
              (Option.value o.belief_version ~default:"null") (Option.value v.belief_version ~default:"null");
          (match (v.status, v.failed_reason) with
          | `Failed, Some r -> Printf.bprintf b "           now: %s\n" r
          | _ -> ());
          (match v.inputs with
          | Some (`Dcf_midcycle m) ->
              Printf.bprintf b
                "           mid-cycle (22): spot fcff %s vs fcff_mid %s; roic_mid %.4f (median %.4f) over %d observations; window %s to %s (%d periods, %d excluded from a sum); fair value %s -> %s\n"
                (match (m.spot_fcff, m.spot_to_midcycle) with
                | Some sp, Some r -> Printf.sprintf "%s (%.2fx)" (money sp) r
                | _ -> "none (" ^ Option.value m.spot_reason ~default:"" ^ ")")
                (money m.fcff_mid) m.roic_mid m.roic_median
                (List.length m.observations) (List.nth m.window (List.length m.window - 1)) (List.hd m.window)
                (List.length m.window) (List.length m.exclusions) (fair_value_text o.fair_value) (fair_value_text v.fair_value)
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
              let removed = removed_inputs ~baseline_raw v in
              List.iter
                (fun (k, value) -> Printf.bprintf b "           %-26s %s -> removed from the model\n" k value)
                removed;
              if fv_moved && changed = [] && removed = [] then begin
                incr unexplained;
                Printf.bprintf b
                  "           NO DRIVER: moved under %s against %s with unchanged inputs; the model arithmetic itself changed, or this is a bug\n"
                  this_version base_version
              end
          | None, Some nd ->
              Printf.bprintf b "           inputs now present (%s):\n"
                (match v.inputs with
                | Some (`Dcf _) -> "dcf"
                | Some (`Residual_income _) -> "residual_income"
                | Some (`Residual_income_insurer _) -> "residual_income_insurer"
                | Some (`Reit_ffo_dividend _) -> "reit_ffo_dividend"
                | Some (`Dcf_midcycle _) -> "dcf_midcycle"
                | None -> "-");
              List.iter
                (fun (name, nv, ntext) ->
                  if List.mem name [ "ebit"; "delta_nwc"; "cash"; "total_debt"; "dividends_paid"; "book_equity"; "net_income"; "ffo"; "covered_dividend"; "g_historical" ] then
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


(* --- stability: the same name on two snapshots (16) --- *)

(* Why an input moved between two fetches with nothing having happened. A report, never a
   gate. *)
type stability_class = Price | New_filing | Restated | Vendor_row | Rate_or_fx | Unexplained

let class_name = function
  | Price -> "price"
  | New_filing -> "new_filing"
  | Restated -> "restated"
  | Vendor_row -> "vendor_row"
  | Rate_or_fx -> "rate_or_fx"
  | Unexplained -> "unexplained"

let all_classes = [ Price; New_filing; Restated; Vendor_row; Rate_or_fx; Unexplained ]

let market_inputs = [ "price"; "market_cap"; "shares" ]

let parameter_inputs =
  [ "statutory_tax_rate"; "risk_free_rate"; "equity_risk_premium"; "beta"; "debt_spread"; "growth_clamp_lower";
    "growth_clamp_upper"; "mean_reversion_lambda"; "terminal_growth_rate"; "country_risk_premium";
    "projection_years"; "midcycle_window_years"; "fx_rate" ]

(* What identifies the statements an input came from: the provider, the fiscal period and,
   on filed statements, the accession of that period. *)
type statements_identity = { provider : string; period_end : string option; accession : string option }

let identity (v : valuation) (fin : financials option) =
  let period_end =
    match v.inputs with
    | Some (`Dcf i) -> Some i.fiscal_period_end
    | Some (`Residual_income i) -> Some i.fiscal_period_end
    | Some (`Residual_income_insurer i) -> Some i.core.fiscal_period_end
    | Some (`Reit_ffo_dividend i) -> Some i.fiscal_period_end
    | Some (`Dcf_midcycle m) -> Some m.dcf.fiscal_period_end
    | None -> None
  in
  let accession =
    Option.bind fin (fun (f : financials) ->
        Option.bind period_end (fun e ->
            Option.bind
              (List.find_opt (fun (p : fiscal_period) -> p.period_end = e) f.periods)
              (fun (p : fiscal_period) -> p.accession)))
  in
  { provider = v.statements_provider; period_end; accession }

let classify_input ~(old : statements_identity) ~(now : statements_identity) name =
  if List.mem name market_inputs then Price
  else if List.mem name parameter_inputs then Rate_or_fx
  else if old.provider <> now.provider then Unexplained
  else if now.provider = "yfinance" then Vendor_row
  else
    match (old.accession, now.accession) with
    | Some a, Some b when a <> b -> New_filing
    | Some a, Some b when a = b && old.period_end = now.period_end -> Restated
    | _ -> Unexplained

type moved_input = { name : string; old_value : float; new_value : float; klass : stability_class }

(* Every input that moved between the two records, classified; a record whose model, status
   or provider differs is one Unexplained item naming the difference. *)
let moved_inputs ~(old : valuation * financials option) ~(now : valuation * financials option) =
  let ov, ofin = old and nv, nfin = now in
  let oi = identity ov ofin and ni = identity nv nfin in
  match (ov.inputs, nv.inputs) with
  | Some oinputs, Some ninputs ->
      let od = drivers oinputs and nd = drivers ninputs in
      let moved =
        List.filter_map
          (fun (name, value, _) ->
            match List.find_opt (fun (n, _, _) -> n = name) od with
            | Some (_, before, _) when differs before value ->
                Some { name; old_value = before; new_value = value; klass = classify_input ~old:oi ~now:ni name }
            | Some _ -> None
            | None -> Some { name; old_value = nan; new_value = value; klass = Unexplained })
          nd
      in
      let gone =
        List.filter_map
          (fun (name, before, _) ->
            if List.exists (fun (n, _, _) -> n = name) nd then None
            else Some { name; old_value = before; new_value = nan; klass = Unexplained })
          od
      in
      let structural =
        if oi.provider <> ni.provider then
          [ { name = "statements_provider " ^ oi.provider ^ " -> " ^ ni.provider; old_value = nan; new_value = nan; klass = Unexplained } ]
        else if oi.period_end <> ni.period_end && ni.provider <> "yfinance" && oi.accession = ni.accession then
          [ { name = "fiscal period " ^ Option.value oi.period_end ~default:"-" ^ " -> " ^ Option.value ni.period_end ~default:"-"; old_value = nan; new_value = nan; klass = Unexplained } ]
        else []
      in
      moved @ gone @ structural
  | None, None ->
      if ov.failed_reason = nv.failed_reason && ov.statements_provider = nv.statements_provider then []
      else [ { name = Printf.sprintf "failed: %s -> %s" (Option.value ov.failed_reason ~default:"-") (Option.value nv.failed_reason ~default:"-"); old_value = nan; new_value = nan; klass = Unexplained } ]
  | _ ->
      [ { name = Printf.sprintf "status %s -> %s" (status_name ov.status) (status_name nv.status); old_value = nan; new_value = nan; klass = Unexplained } ]

let value_text x = if Float.is_nan x then "-" else money x

(* The report over two runs on two snapshots, and the counts per class. Rates refreshed
   between the runs show as a differing parameter as_of on any record. *)
let stability ~snapshot_old ~snapshot_new ~(old : (valuation * financials option) list)
    ~(now : (valuation * financials option) list) =
  let b = Buffer.create 8192 in
  let counts = Hashtbl.create 8 in
  List.iter (fun c -> Hashtbl.replace counts c 0) all_classes;
  let bump c = Hashtbl.replace counts c (Hashtbl.find counts c + 1) in
  let rf_as_of (v : valuation) =
    match v.inputs with
    | Some (`Dcf i) -> Some i.risk_free_rate.as_of
    | Some (`Residual_income i) -> Some i.risk_free_rate.as_of
    | Some (`Residual_income_insurer i) -> Some i.core.risk_free_rate.as_of
    | Some (`Reit_ffo_dividend i) -> Some i.risk_free_rate.as_of
    | Some (`Dcf_midcycle m) -> Some m.dcf.risk_free_rate.as_of
    | None -> None
  in
  let as_of_pair =
    List.find_map
      (fun ((nv : valuation), _) ->
        match List.find_opt (fun ((ov : valuation), _) -> ov.ticker = nv.ticker) old with
        | Some (ov, _) -> ( match (rf_as_of ov, rf_as_of nv) with Some a, Some c -> Some (a, c) | _ -> None)
        | None -> None)
      now
  in
  Printf.bprintf b "stability: snapshot %s against snapshot %s, every input of every record classified; a report, never a gate\n" snapshot_new snapshot_old;
  (match as_of_pair with
  | Some (a, c) when a <> c -> Printf.bprintf b "rates or fx refreshed between the runs: yes (risk-free as_of %s -> %s)\n\n" a c
  | Some (a, _) -> Printf.bprintf b "rates or fx refreshed between the runs: no (risk-free as_of %s on both)\n\n" a
  | None -> Printf.bprintf b "rates or fx refreshed between the runs: not determinable (no valued record on both sides)\n\n");
  List.iter
    (fun ((nv : valuation), nfin) ->
      match List.find_opt (fun ((ov : valuation), _) -> ov.ticker = nv.ticker) old with
      | None -> Printf.bprintf b "%-10s not in snapshot %s\n" nv.ticker snapshot_old
      | Some (ov, ofin) ->
          let items = moved_inputs ~old:(ov, ofin) ~now:(nv, nfin) in
          List.iter (fun (m : moved_input) -> bump m.klass) items;
          let fv =
            match (ov.fair_value, nv.fair_value) with
            | Some p, Some n when differs p n -> Printf.sprintf "; fair value %.2f -> %.2f" p n
            | _ -> ""
          in
          if items = [] then Printf.bprintf b "%-10s unchanged%s\n" nv.ticker fv
          else begin
            Printf.bprintf b "%-10s %d moved input(s)%s\n" nv.ticker (List.length items) fv;
            List.iter
              (fun (m : moved_input) ->
                Printf.bprintf b "           %-12s %-26s %s -> %s\n" (class_name m.klass) m.name (value_text m.old_value) (value_text m.new_value))
              items
          end)
    now;
  List.iter
    (fun ((ov : valuation), _) ->
      if not (List.exists (fun ((nv : valuation), _) -> nv.ticker = ov.ticker) now) then
        Printf.bprintf b "%-10s not in snapshot %s\n" ov.ticker snapshot_new)
    old;
  let line =
    "stability against snapshot " ^ snapshot_old ^ ": "
    ^ String.concat ", " (List.map (fun c -> Printf.sprintf "%s %d" (class_name c) (Hashtbl.find counts c)) all_classes)
  in
  Printf.bprintf b "\n%s\n" line;
  (Buffer.contents b, line)

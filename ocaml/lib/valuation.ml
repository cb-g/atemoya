open Boundary_t

type thresholds = { buy_above : float; sell_below : float; sanity_bound : float }

let default_thresholds = { buy_above = 0.25; sell_below = -0.25; sanity_bound = 5.0 }

let signal t margin_of_safety : signal =
  if margin_of_safety >= t.buy_above then `Buy
  else if margin_of_safety <= t.sell_below then `Sell
  else `Hold

type declaration = {
  entity_class : entity_class;
  scope_limits : string list;
}

let floor_of_rule (r : Reference_t.class_rule) : floor =
  { present = r.floor_present_default; basis = r.floor_basis_default }

let floor_undeclared : floor =
  { present = None; basis = "not assessable: no entity_class declared" }

(* What a completed model verified as the floor. *)
let floor_verified ~currency (inputs : model_inputs) ~fair_value : floor =
  let basis =
    match inputs with
    | `Dcf (i : inputs) ->
        Printf.sprintf
          "dcf: fcff %.4g %s for the fiscal period ending %s, fair value %.2f %s per share \
           against price %.2f"
          i.fcff currency i.fiscal_period_end fair_value currency i.price
    | `Residual_income (i : residual_income_inputs) ->
        Printf.sprintf
          "residual income: book value %.2f %s per share for the fiscal period ending %s, \
           fair value %.2f %s per share against price %.2f, justified price/book %.2f"
          i.book_value_per_share currency i.fiscal_period_end fair_value currency i.price
          i.justified_price_to_book
    | `Residual_income_insurer (i : insurer_inputs) ->
        Printf.sprintf
          "residual income on AOCI-adjusted book: adjusted book value %.2f %s per share \
           (reported %.4g, AOCI %.4g removed) for the fiscal period ending %s, fair value \
           %.2f %s per share against price %.2f, justified price/book %.2f; reserve adequacy \
           not assessed"
          i.core.book_value_per_share currency i.reported_book_equity i.aoci
          i.core.fiscal_period_end fair_value currency i.core.price
          i.core.justified_price_to_book
    | `Dcf_midcycle (m : midcycle_inputs) ->
        Printf.sprintf
          "mid-cycle dcf: fcff_mid %.4g %s from a mean roic of %.4f over %d observations (%s to %s) on invested \
           capital %.4g, reinvestment rate %.4f%s, spot fcff %s for the fiscal period ending %s, \
           fair value %.2f %s per share against price %.2f"
          m.fcff_mid currency m.roic_mid (List.length m.observations)
          (List.nth m.window (List.length m.window - 1)) (List.hd m.window) m.invested_capital_latest
          m.reinvestment_rate_mid
          (match m.reinvestment_rate_measured with Some r -> Printf.sprintf " (measured %.4f, floored at zero)" r | None -> "")
          (match (m.spot_fcff, m.spot_to_midcycle) with
          | Some s, Some r -> Printf.sprintf "%.4g (%.2fx mid-cycle)" s r
          | _ -> "none (" ^ Option.value m.spot_reason ~default:"" ^ ")")
          m.dcf.fiscal_period_end fair_value currency m.dcf.price
    | `Reit_ffo_dividend (i : reit_inputs) ->
        Printf.sprintf
          "reit ffo dividend: ffo %.2f %s per share (price/ffo %.1f) covering a dividend of %.2f per share \
           (coverage %.2f) for the fiscal period ending %s, fair value %.2f %s per share against price \
           %.2f; %s"
          i.ffo_per_share currency i.price_to_ffo i.dividend_per_share i.coverage i.fiscal_period_end
          fair_value currency i.price i.caveat
  in
  { present = Some true; basis }

let with_conversion conversion (inputs : model_inputs) : model_inputs =
  match inputs with
  | `Dcf i -> `Dcf { i with conversion = Some conversion }
  | `Residual_income i -> `Residual_income { i with conversion = Some conversion }
  | `Residual_income_insurer i ->
      `Residual_income_insurer { i with core = { i.core with conversion = Some conversion } }
  | `Reit_ffo_dividend i -> `Reit_ffo_dividend { i with conversion = Some conversion }
  | `Dcf_midcycle m -> `Dcf_midcycle { m with dcf = { m.dcf with conversion = Some conversion } }

(* A record's compositions must follow the reference's definitions on every period: a
   data file fetched under another definition is refused, never valued as if it were the
   current one. A record that names no definition (fetched before them) passes. *)
let definitions_check (defs : Reference_t.field_definitions) (fin : financials) =
  let mismatch field recorded expected =
    Error
      (Printf.sprintf
         "field definition mismatch: %s follows %S, reference/field_definitions.json defines \
          %S; refetch the statements"
         field recorded expected)
  in
  let check field (recorded : composition option) expected =
    match recorded with
    | Some c when c.definition <> expected -> mismatch field c.definition expected
    | _ -> Ok ()
  in
  let ( let* ) = Result.bind in
  let cash_name = (defs.cash : Reference_t.cash_definition).name in
  let debt_name = (defs.total_debt : Reference_t.debt_definition).name in
  let nwc_name = (defs.delta_nwc : Reference_t.nwc_definition).name in
  let ebit = (defs.ebit : Reference_t.ebit_definition) in
  List.fold_left
    (fun acc (p : fiscal_period) ->
      let* () = acc in
      let* () = check "cash" p.cash_composition cash_name in
      let* () = check "total_debt" p.total_debt_composition debt_name in
      let* () = check "delta_nwc" p.delta_nwc_composition nwc_name in
      let* () = check "ebit" p.ebit_composition ebit.name in
      let* () =
        match defs.aoci with
        | Some (a : Reference_t.aoci_definition) -> check "aoci" p.aoci_composition a.name
        | None -> Ok ()
      in
      match p.ebit_recipe with
      | Some r when not (List.mem r ebit.recipes) ->
          mismatch "ebit recipe" r (String.concat " | " ebit.recipes)
      | _ -> Ok ())
    (Ok ()) fin.periods

(* Filed statements carry their own currency (the facts' unit); the vendor names the
   statement currency independently. They must agree, or the record is refused before any
   money moves: this is where a silent unit error between the two providers would live. *)
let currency_agreement (fin : financials) =
  match (fin.vendor_financial_currency, fin.financial_currency) with
  | Some vendor, Some filing when vendor <> filing ->
      Error (Printf.sprintf "financial currency disagreement: filing %s, vendor %s" filing vendor)
  | _ -> Ok ()

(* Every named parameter a model's inputs carry, for the anachronism declaration. *)
let rec parameters_of (inputs : model_inputs) : (string * parameter) list =
  let core (i : residual_income_inputs) =
    [ ("risk_free_rate", i.risk_free_rate); ("equity_risk_premium", i.equity_risk_premium); ("beta", i.beta);
      ("mean_reversion_lambda", i.mean_reversion_lambda) ]
    @ (match i.country_risk_premium with Some c -> [ ("country_risk_premium", c) ] | None -> [])
  in
  match inputs with
  | `Dcf i ->
      [ ("statutory_tax_rate", i.statutory_tax_rate); ("risk_free_rate", i.risk_free_rate);
        ("equity_risk_premium", i.equity_risk_premium); ("beta", i.beta); ("debt_spread", i.debt_spread);
        ("growth_clamp_lower", i.growth_clamp_lower); ("growth_clamp_upper", i.growth_clamp_upper);
        ("mean_reversion_lambda", i.mean_reversion_lambda); ("terminal_growth_rate", i.terminal_growth_rate) ]
      @ (match i.country_risk_premium with Some c -> [ ("country_risk_premium", c) ] | None -> [])
  | `Dcf_midcycle m -> parameters_of (`Dcf m.dcf)
  | `Residual_income i -> core i
  | `Residual_income_insurer i -> core i.core
  | `Reit_ffo_dividend i ->
      [ ("risk_free_rate", i.risk_free_rate); ("equity_risk_premium", i.equity_risk_premium); ("beta", i.beta);
        ("growth_clamp_lower", i.growth_clamp_lower); ("growth_clamp_upper", i.growth_clamp_upper);
        ("mean_reversion_lambda", i.mean_reversion_lambda); ("terminal_growth_rate", i.terminal_growth_rate) ]
      @ (match i.country_risk_premium with Some c -> [ ("country_risk_premium", c) ] | None -> [])

(* The parameters whose vintage postdates the point-in-time date: held, declared. *)
let anachronistic ~(class_check : class_check option) (inputs : model_inputs option) =
  let named =
    (match class_check with Some c -> [ ("bank_nii_ratio_threshold", c.bank_nii_ratio_threshold) ] | None -> [])
    @ (match inputs with Some i -> parameters_of i | None -> [])
  in
  List.filter_map
    (fun (name, (p : parameter)) -> if p.age_days < 0 then Some (Printf.sprintf "%s (vintage %s)" name p.as_of) else None)
    named
  |> List.sort_uniq compare

(* A point-in-time record (17) is refused when the date offered no filed statements, no
   cover-page shares or no rate history; the reason from the fetch is named. *)
let point_in_time_gates (fin : financials) =
  match fin.point_in_time with
  | None -> Ok ()
  | Some pit -> (
      match (pit.statements_unavailable, pit.shares_unavailable, pit.rates_unavailable) with
      | Some why, _, _ -> Error ("no point-in-time statements: " ^ why)
      | None, Some why, _ -> Error ("no point-in-time shares: " ^ why)
      | None, None, Some currency -> Error ("rate source has no history for " ^ currency)
      | None, None, None -> Ok ())

let run ?(thresholds = default_thresholds) ?name_beliefs ?name_required_returns ?options (params : Params.t) ~today ~model_version
    ~declaration (original : financials) : valuation =
  let declared = Option.map (fun d -> d.entity_class) declaration in
  let hold_vintage = Option.is_some original.point_in_time in
  (* Age of the newest filing the statements come from, when they are filed ones. *)
  let filing_age =
    Option.map
      (fun d -> Date.days_between ~from:d ~until:today)
      original.latest_filing
  in
  let filing_age_days =
    match filing_age with Some (Ok n) -> Some n | _ -> None
  in
  (* The entry's own scope limits, then the class's defaults from the admissibility row
     (22), each once. *)
  let scope_limits =
    let own = match declaration with Some d -> d.scope_limits | None -> [] in
    let defaults =
      match Option.map (Admissibility.rule params.admissibility) declared with
      | Some (Ok r) -> r.scope_limits_default
      | _ -> []
    in
    own @ List.filter (fun l -> not (List.mem l own)) defaults
  in
  (* [fin] is the record the model saw: the original, or its converted copy. *)
  let record ~(fin : financials) ?model ?class_check ?inputs ?fair_value ?margin_of_safety
      ?signal ?failed_reason ~price ~status ~floor () =
    {
      ticker = fin.ticker;
      as_of = fin.as_of;
      valued_on = today;
      model_version;
      currency = fin.currency;
      price;
      fair_value;
      margin_of_safety;
      signal;
      entity_class = declared;
      model;
      class_check;
      floor;
      scope_limits;
      statements_provider = original.provider;
      taxonomy = original.taxonomy;
      market_provider = original.market_provider;
      provider_reason = original.provider_reason;
      filing_age_days;
      cross_check = original.cross_check;
      submissions_latest_annual = original.submissions_latest_annual;
      point_in_time =
        Option.map
          (fun (pit : point_in_time) -> { pit with anachronistic_inputs = anachronistic ~class_check inputs })
          original.point_in_time;
      status;
      failed_reason;
      inputs;
      implied = None;
      sensitivity = None;
      belief_map = None;
      belief_map_reason = None;
      belief_version = None;
      belief = None;
      belief_reason = None;
      cost_of_equity_capm = None;
      cost_of_equity_used = None;
      required_return_source = None;
      required_return_version = None;
      surplus_curve = None;
      surplus_curve_reason = None;
      market_implied = None;
      market_implied_reason = None;
    }
  in
  (* The declared required return (34), per name: a names entry, else the class default,
     else CAPM; it replaces the CAPM chain above the risk-free rate on both paths. *)
  let with_required_return (a : Dcf.assumptions) =
    let entity_class = match declared with Some c -> Admissibility.class_name c | None -> "" in
    { a with
      required_return =
        Required_returns.resolve params.required_returns ?names:name_required_returns ~ticker:original.ticker ~entity_class () }
  in
  (* The declared belief (24) on a growth-then-terminal path: the fourth readout and the
     probability of overpaying under it; the residual-income paths and an undeclared class
     carry the reason instead. *)
  let terminal_and_f (inputs : model_inputs) =
      match inputs with
      | `Dcf i ->
          Some (i.terminal_growth_rate.value, i.wacc,
                fun terminal_growth_rate -> Implied.dcf_fair_value i ~terminal_growth_rate ~g0:i.g0 ~lambda:i.mean_reversion_lambda.value)
      | `Dcf_midcycle m ->
          let i = m.dcf in
          Some (i.terminal_growth_rate.value, i.wacc,
                fun terminal_growth_rate -> Implied.dcf_fair_value i ~terminal_growth_rate ~g0:i.g0 ~lambda:i.mean_reversion_lambda.value)
      | `Reit_ffo_dividend i ->
          Some (i.terminal_growth_rate.value, i.cost_of_equity,
                fun terminal_growth_rate -> Implied.reit_fair_value i ~terminal_growth_rate ~g0:i.g0 ~lambda:i.mean_reversion_lambda.value)
      | `Residual_income _ | `Residual_income_insurer _ -> None
  in
  let belief_of ~price ~fair_value (inputs : model_inputs) =
    match terminal_and_f inputs with
    | None -> Error "the residual-income path has no terminal growth; the belief parameter is undefined there"
    | Some (terminal_growth_rate, rate, f) -> (
        let entity_class = match declared with Some c -> Admissibility.class_name c | None -> "" in
        match
          Beliefs.resolve ~classes:params.beliefs ?names:name_beliefs ~ticker:original.ticker ~entity_class
            ~terminal_growth_rate ()
        with
        | None ->
            Error
              (Printf.sprintf "no belief declared for %s: no class default in reference/beliefs.json and no per-name entry"
                 entity_class)
        | Some (b, source) ->
            let source_kind = if String.length source >= 8 && String.sub source 0 8 = "per-name" then "name" else "class" in
            Ok (Beliefs.readout b ~source ~source_kind ~f ~price ~rate ~fair_value, Beliefs.surplus_curve b ~f ~price))
  in
  (* The market-implied readout (36), only under --options: the chain for the name on the
     latest snapshot date, or the reason there is none. *)
  let rf_of (inputs : model_inputs) =
    match inputs with
    | `Dcf i -> i.risk_free_rate.value
    | `Dcf_midcycle m -> m.dcf.risk_free_rate.value
    | `Residual_income i -> i.risk_free_rate.value
    | `Residual_income_insurer i -> i.core.risk_free_rate.value
    | `Reit_ffo_dividend i -> i.risk_free_rate.value
  in
  let market_implied_of ~ke ~fair_value (inputs : model_inputs) =
    match options with
    | None -> (None, None)
    | Some lookup -> (
        match lookup original.ticker with
        | Error r -> (None, Some r)
        | Ok chain -> (
            let growth =
              match terminal_and_f inputs with
              | Some (_, rate, f) -> Ok (rate, f)
              | None -> Error "the residual-income path has no terminal growth; the growth axis is undefined there"
            in
            match Market_implied.of_chain chain ~rf:(rf_of inputs) ~ke ~fair_value ~growth with
            | Ok m -> (Some m, None)
            | Error r -> (None, Some r)))
  in
  let failed ?(fin = original) ?model ?class_check ?inputs ~floor reason =
    record ~fin ?model ?class_check ?inputs ~price:fin.price ~status:`Failed
      ~failed_reason:reason ~floor ()
  in
  let floor_default () =
    match
      Option.bind declared (fun c -> Result.to_option (Admissibility.rule params.admissibility c))
    with
    | Some r -> floor_of_rule r
    | None -> floor_undeclared
  in
  (* After a model produced a fair value: applicability, sanity bound, signal, floor. *)
  let conclude ~fin ~model ~class_check ~rule ~price ~(assumptions : Dcf.assumptions) (inputs : model_inputs) fair_value =
    let failed = failed ~fin ~model ~class_check ~inputs ~floor:(floor_of_rule rule) in
    if fair_value <= 0. then
      failed (Printf.sprintf "non-positive fair value %g: model not applicable" fair_value)
    else
      let margin_of_safety = (fair_value -. price) /. price in
      if margin_of_safety > thresholds.sanity_bound then
        failed
          (Printf.sprintf
             "margin of safety %.2f exceeds sanity bound %.2f: likely structural break; \
              check entity_class"
             margin_of_safety thresholds.sanity_bound)
      else
        let currency = Option.value fin.currency ~default:"" in
        {
          (record ~fin ~model ~class_check ~inputs ~fair_value ~margin_of_safety
             ~signal:(signal thresholds margin_of_safety)
             ~price:(Some price) ~status:`Ok
             ~floor:(floor_verified ~currency inputs ~fair_value)
             ())
          with
          implied = Some (Implied.of_inputs inputs ~price);
          sensitivity = Some (Sensitivity.of_inputs params.params.sensitivity_steps inputs ~fair_value);
          belief_map = Result.to_option (Belief_map.of_inputs inputs ~price);
          belief_map_reason = (match Belief_map.of_inputs inputs ~price with Error r -> Some r | Ok _ -> None);
          belief_version = (match belief_of ~price ~fair_value inputs with Ok (r, _) -> Some r.belief_version | Error _ -> None);
          belief = (match belief_of ~price ~fair_value inputs with Ok (r, _) -> Some r | Error _ -> None);
          belief_reason = (match belief_of ~price ~fair_value inputs with Error r -> Some r | Ok _ -> None);
          surplus_curve = (match belief_of ~price ~fair_value inputs with Ok (_, curve) -> Some curve | Error _ -> None);
          surplus_curve_reason =
            (match belief_of ~price ~fair_value inputs with Error r -> Some ("no surplus curve: " ^ r) | Ok _ -> None);
          cost_of_equity_capm = Some (Dcf.cost_of_equity_capm assumptions);
          cost_of_equity_used = Some (Dcf.cost_of_equity assumptions);
          required_return_source =
            Some (match assumptions.required_return with Some r -> r.source | None -> "capm");
          required_return_version = Option.map (fun (r : Dcf.declared_return) -> r.version) assumptions.required_return;
          market_implied = fst (market_implied_of ~ke:(Dcf.cost_of_equity assumptions) ~fair_value inputs);
          market_implied_reason = snd (market_implied_of ~ke:(Dcf.cost_of_equity assumptions) ~fair_value inputs);
        }
  in
  (* A derived ebit (any recipe but operating income) runs the dcf only when the record's
     cross-check found it within threshold of the vendor's operating income; a miss, or no
     figure to check against, is the policy's Failed. *)
  let ebit_policy (fin : financials) =
    let policy = params.field_definitions.refinement_policy in
    match Period.latest fin with
    | Some ({ ebit_recipe = Some recipe; _ } : fiscal_period) when recipe <> "operating_income" -> (
        let check =
          Option.bind original.cross_check (fun (c : cross_check) ->
              List.find_opt (fun (f : field_check) -> f.field = "ebit") c.fields)
        in
        match check with
        | Some { agree = Some true; _ } -> Ok ()
        | Some ({ agree = Some false; _ } as f) ->
            Error
              (Printf.sprintf "%s (%s: derived %.4g against the vendor's %.4g, %.1f%% beyond the %g%% threshold)"
                 policy.on_miss recipe
                 (Option.value f.primary ~default:nan) (Option.value f.secondary ~default:nan)
                 (Option.value f.relative_difference ~default:nan *. 100.)
                 (match original.cross_check with Some c -> c.threshold *. 100. | None -> nan))
        | _ ->
            Error
              (Printf.sprintf "%s (%s: no vendor operating income to check against)" policy.on_miss
                 recipe))
    | _ -> Ok ()
  in
  let run_model ~fin ?conversion ~model ~class_check ~rule ~country assumptions =
    let failed = failed ~fin ~model ~class_check ~floor:(floor_of_rule rule) in
    let finish ~price inputs fair_value =
      let inputs =
        match conversion with Some c -> with_conversion c inputs | None -> inputs
      in
      conclude ~fin ~model ~class_check ~rule ~price ~assumptions inputs fair_value
    in
    match model with
    | `Dcf -> (
        match ebit_policy fin with
        | Error reason -> failed reason
        | Ok () -> (
            match Dcf.value ~declared:(match declared with Some c -> Admissibility.class_name c | None -> "") assumptions ~country fin with
            | Error reason -> failed reason
            | Ok (inputs, fair_value) -> finish ~price:inputs.price (`Dcf inputs) fair_value))
    | `Residual_income -> (
        match Residual_income.value assumptions ~country fin with
        | Error reason -> failed reason
        | Ok (inputs, fair_value) -> finish ~price:inputs.price (`Residual_income inputs) fair_value)
    | `Residual_income_insurer -> (
        match Insurer.value assumptions ~country fin with
        | Error reason -> failed reason
        | Ok (inputs, fair_value) ->
            finish ~price:inputs.core.price (`Residual_income_insurer inputs) fair_value)
    | `Reit_ffo_dividend -> (
        match Reit.value assumptions ~country fin with
        | Error reason -> failed reason
        | Ok (inputs, fair_value) -> finish ~price:inputs.price (`Reit_ffo_dividend inputs) fair_value)
    | `Dcf_midcycle -> (
        (* No EBIT policy here (25): the model's NOPAT is bottom-up from net income and
           interest expense, so an operating-income line is not an input to it. *)
        match
          Option.bind params.field_definitions.required_on_latest_period (fun (r : Reference_t.required_on_latest_period) ->
              List.assoc_opt "dcf_midcycle" r.models)
        with
        | None -> failed "field_definitions.json carries no required_on_latest_period for dcf_midcycle"
        | Some required -> (
            match Dcf_midcycle.value assumptions ~country ~required fin with
            | Error reason -> failed reason
            | Ok (inputs, fair_value) -> finish ~price:inputs.dcf.price (`Dcf_midcycle inputs) fair_value))
  in
  (* The filing-age gate, then the currency gate: the same-currency path untouched, else
     convert and re-source. *)
  let value ~model ~class_check ~rule ~country =
    let failed = failed ~model ~class_check ~floor:(floor_of_rule rule) in
    let max_age = params.xbrl_tags.max_filing_age_days in
    let gates =
      Result.bind (point_in_time_gates original) (fun () ->
          Result.bind (currency_agreement original) (fun () ->
              definitions_check params.field_definitions original))
    in
    match (gates, filing_age, original.financial_currency, original.trading_currency) with
    | Error reason, _, _, _ -> failed reason
    | Ok (), Some (Error msg), _, _ -> failed (Printf.sprintf "latest_filing: %s" msg)
    | Ok (), Some (Ok n), _, _ when n > max_age ->
        failed
          (Printf.sprintf
             "latest annual filing is %d days old, older than its max_filing_age_days %d" n
             max_age)
    | Ok (), _, None, _ -> failed "missing market data: financial_currency"
    | Ok (), _, _, None -> failed "missing market data: trading_currency"
    | Ok (), _, Some financial, Some trading when financial = trading -> (
        match Params.resolve ~hold_vintage params ~today ~country ~industry:original.industry with
        | Error reason -> failed reason
        | Ok assumptions ->
            run_model ~fin:original ~model ~class_check ~rule ~country (with_required_return assumptions))
    | Ok (), _, Some financial, Some trading -> (
        match Fx.rate params.fx_sources params.fx_rates ~today ~financial ~trading with
        | Error reason -> failed reason
        | Ok legs -> (
            match Fx.country_of params.fx_sources trading with
            | Error reason -> failed reason
            | Ok rate_country -> (
                match
                  Params.resolve_cross ~hold_vintage params ~today ~domicile:country ~rate_country
                    ~industry:original.industry
                with
                | Error reason -> failed reason
                | Ok assumptions ->
                    let converted = Fx.convert ~rate:legs.fx_rate original in
                    let conversion =
                      {
                        financial_currency = financial;
                        trading_currency = trading;
                        fx_rate = legs.fx_rate;
                        fx_usd_per_financial = legs.usd_per_financial;
                        fx_usd_per_trading = legs.usd_per_trading;
                        fx_source = legs.source;
                        fx_as_of = legs.as_of;
                        fx_age_days = legs.age_days;
                        domicile = country;
                        rate_country;
                        growth_country = rate_country;
                        price_unit = original.price_unit;
                        price_unit_divisor = original.price_unit_divisor;
                      }
                    in
                    run_model ~fin:converted ~conversion ~model ~class_check ~rule ~country
                      (with_required_return assumptions))))
  in
  match Params.classification_threshold ~hold_vintage params ~today with
  | Error reason -> failed ~floor:(floor_default ()) reason
  | Ok threshold -> (
      let s = Classify.signature ~threshold original in
      match Classify.check ~declared s with
      | Classify.Refuse (reason, class_check) ->
          failed ~class_check ~floor:(floor_default ()) reason
      | Classify.Proceed class_check -> (
          match declared with
          | None -> failed ~class_check ~floor:floor_undeclared "entity_class not declared"
          | Some cls -> (
              match Admissibility.rule params.admissibility cls with
              | Error reason -> failed ~class_check ~floor:floor_undeclared reason
              | Ok rule -> (
                  match Admissibility.routed rule with
                  | None ->
                      failed ~class_check ~floor:(floor_of_rule rule)
                        (Printf.sprintf "dcf not admissible for %s; lens: %s"
                           (Admissibility.class_name cls) rule.lens)
                  | Some model -> (
                      match original.country with
                      | None ->
                          failed ~model ~class_check ~floor:(floor_of_rule rule)
                            "country not determinable from the fetch"
                      | Some country -> value ~model ~class_check ~rule ~country)))))

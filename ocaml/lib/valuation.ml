open Boundary_t

(* (54) What the record says when the risk-free rate is not the domicile's own. *)
let no_curve_rf_note = "trading currency; domicile curve unavailable"

type thresholds = { buy_above : float; sell_below : float; sanity_bound : float }

let default_thresholds = { buy_above = 0.25; sell_below = -0.25; sanity_bound = 5.0 }

let signal t margin_of_safety : signal =
  if margin_of_safety >= t.buy_above then `Buy
  else if margin_of_safety <= t.sell_below then `Sell
  else `Hold

let uncoded = "uncoded"

type declaration = {
  entity_class : entity_class;
  scope_limits : string list;
  scope_limit_codes : string list;
  adr_ratio : float option;
  build_out_return : Reference_t.declared_build_out option;
  build_out_lag_years : Reference_t.declared_build_out option;
}

let receipt_tolerance = 0.03

let receipt_check ~declared (fin : financials) =
  match (fin.cover_page_shares, fin.cover_page_shares_as_of, fin.market_cap, fin.price) with
  | Some cover, Some as_of, Some cap, Some price when price > 0. && cover > 0. ->
      let cross = match (fin.financial_currency, fin.trading_currency) with Some f, Some t -> f <> t | _ -> false in
      if Option.is_none declared && not cross then None
      else
        let effective = cap /. price in
        (* (44) the cover page's count carried through the vendor's split record to the fetch date *)
        let cover = cover *. Option.value fin.cover_page_split_factor ~default:1. in
        let implied = cover /. effective in
        let flag =
          match declared with
          | Some r when Float.abs ((implied -. r) /. r) > receipt_tolerance ->
              Some
                (Printf.sprintf
                   "depositary ratio mismatch: declared %g, live shares imply %.3f (cover page %.0f ordinary shares as of %s, effective %.0f)"
                   r implied cover as_of effective)
          | Some _ -> None
          | None when Float.abs (implied -. 1.) > receipt_tolerance ->
              Some
                (Printf.sprintf "undeclared depositary ratio: live shares imply %.3f (cover page %.0f ordinary shares as of %s, effective %.0f)"
                   implied cover as_of effective)
          | None -> None
        in
        Some
          { cover_page_shares = cover; cover_page_shares_as_of = as_of; effective_shares = effective; implied_ratio = implied; declared_ratio = declared;
            cover_page_split_factor = fin.cover_page_split_factor; flag }
  | _ -> None

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
    | `Bdc_nav (i : bdc_inputs) ->
        Printf.sprintf
          "bdc nav: net asset value %.2f %s per share as filed for the fiscal period ending %s, price/nav %.2f,            net investment income %.2f per share covering a distribution of %.2f per share (coverage %.2f);            fair value %.2f %s per share against price %.2f; %s"
          i.net_asset_value_per_share currency i.fiscal_period_end i.price_to_nav
          i.net_investment_income_per_share i.distributions_per_share i.nii_coverage fair_value currency
          i.price i.caveat
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
  | `Bdc_nav i -> `Bdc_nav { i with conversion = Some conversion }

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
  (* (59) None: the BDC lens discounts nothing and projects nothing, so no country
     parameter is an input to it. The parameters gate the pipeline, they are not held. *)
  | `Bdc_nav _ -> []

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
  let receipt = receipt_check ~declared:(Option.bind declaration (fun d -> d.adr_ratio)) original in
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
  let scope_limits, scope_limit_codes =
    (* A limit and its code travel as a pair; a list of codes that does not match its
       limits one for one is no coding at all, and each limit then reads uncoded. *)
    let coded limits codes =
      if List.length codes = List.length limits then List.combine limits codes
      else List.map (fun l -> (l, uncoded)) limits
    in
    let own =
      match declaration with Some d -> coded d.scope_limits d.scope_limit_codes | None -> []
    in
    let defaults =
      match Option.map (Admissibility.rule params.admissibility) declared with
      | Some (Ok r) -> coded r.scope_limits_default r.scope_limit_codes_default
      | _ -> []
    in
    List.split (own @ List.filter (fun (l, _) -> not (List.mem_assoc l own)) defaults)
  in
  let rf_of (inputs : model_inputs) =
    match inputs with
    | `Dcf i -> i.risk_free_rate.value
    | `Dcf_midcycle m -> m.dcf.risk_free_rate.value
    | `Residual_income i -> i.risk_free_rate.value
    | `Residual_income_insurer i -> i.core.risk_free_rate.value
    | `Reit_ffo_dividend i -> i.risk_free_rate.value
    | `Bdc_nav _ -> 0.
  in

  (* (68) The earnings gate, on EVERY record, Ok or Failed. The calendar is the fetch's --
     the filed 8-K item 2.02 dates or the vendor's -- and this adds only what needs the
     options store: what the market charges for the event, from the two expiries bracketing
     the next release. It never fails a record and nothing downstream reads it. *)
  let earnings_of (inputs : model_inputs option) =
    match original.earnings_calendar with
    | None -> (None, original.earnings_calendar_reason)
    | Some calendar ->
        let implied =
          match options with
          | None -> Error "no options directory given"
          | Some lookup -> (
              (* the store's own absence reason first and the rate only after it: a name with
                 no chain is told that, not told about a rate it would never have used *)
              match (lookup original.ticker, inputs) with
              | Error r, _ -> Error r
              | Ok _, None ->
                  Error "the record has no resolved risk-free rate: it failed before a model ran, and the two expiries cannot be put on one forward without one"
              | Ok chain, Some inputs ->
                  Earnings.implied_of chain ~rf:(rf_of inputs) ~next:calendar.next_date)
        in
        (Some (Earnings.block_of ~calendar ~valued_on:today ~implied), None)
  in
  (* (68) The mark on the selected expiry. The expiry is NOT reselected and no readout moves;
     a reader is told whether the horizon they are being shown carries the release. *)
  let mark_earnings (m : market_implied option) (e : earnings option) =
    match (m, e) with
    | None, _ -> None
    | Some m, None ->
        Some { m with spans_earnings_reason = Some "the record carries no earnings calendar" }
    | Some m, Some e ->
        Some
          {
            m with
            spans_earnings = Some (Earnings.spans ~expiry:m.expiry ~next:e.calendar.next_date);
            earnings_implied_move = (match e.implied with Some i -> Some i.implied_move | None -> None);
            spans_earnings_reason = (match e.implied with Some _ -> None | None -> e.implied_reason);
          }
  in
  (* (76) The runway readout, from the original statements in their own currency, on an
     Unprofitable record and no other; it rides beside the class's own refusal. *)
  let runway, runway_reason =
    Runway.of_record ~entity_class:declared ~periods:original.periods ~calendar:original.earnings_calendar
      ~calendar_reason:original.earnings_calendar_reason ~valued_on:today
  in
  (* [fin] is the record the model saw: the original, or its converted copy. *)
  let record ~(fin : financials) ?model ?class_check ?inputs ?fair_value ?margin_of_safety
      ?signal ?failed_reason ?build_out ?build_out_reason ~price ~status ~floor () =
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
      scope_limit_codes;
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
      implied_reason = None;
      sensitivity = None;
      sensitivity_reason = None;
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
      receipt_check = receipt;
      stretch = original.stretch;
      stretch_reason = original.stretch_reason;
      insiders = original.insiders;
      insiders_reason = original.insiders_reason;
      build_out;
      build_out_reason;
      earnings = fst (earnings_of inputs);
      earnings_reason = snd (earnings_of inputs);
      runway;
      runway_reason;
      rd_shadow = None;
      rd_shadow_reason = None;
      options_expected_return = None;
      options_expected_return_reason = None;
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
  (* The declared belief (24): the fourth readout and the probability of overpaying under
     it. On a growth-then-terminal path the parameter is long-run growth, anchored on the
     country's terminal growth; on the residual-income path it is (58) the long-run return
     on equity the ROE path reverts to, anchored on the cost of equity, where a zero offset
     is brief 15's anchor and grants nothing. An undeclared class carries the reason. *)
  let axis_of (inputs : model_inputs) =
      let dcf_axis (i : Boundary_t.inputs) =
        (Beliefs.growth_axis, i.terminal_growth_rate.value, "the country's terminal growth", i.wacc,
         (fun terminal_growth_rate -> Implied.dcf_fair_value i ~terminal_growth_rate ~g0:i.g0 ~lambda:i.mean_reversion_lambda.value))
      in
      let roe_axis (i : Boundary_t.residual_income_inputs) =
        (Beliefs.roe_axis, i.cost_of_equity, "the cost of equity", i.cost_of_equity,
         (fun roe_target -> Implied.residual_income_fair_value i ~roe_0:i.roe_0 ~lambda:i.mean_reversion_lambda.value ~roe_target))
      in
      match inputs with
      | `Dcf i -> Some (dcf_axis i)
      | `Dcf_midcycle m -> Some (dcf_axis m.dcf)
      | `Reit_ffo_dividend i ->
          Some (Beliefs.growth_axis, i.terminal_growth_rate.value, "the country's terminal growth", i.cost_of_equity,
                fun terminal_growth_rate -> Implied.reit_fair_value i ~terminal_growth_rate ~g0:i.g0 ~lambda:i.mean_reversion_lambda.value)
      | `Residual_income i -> Some (roe_axis i)
      | `Residual_income_insurer i -> Some (roe_axis i.core)
      (* (59) the BDC lens holds no parameter, so there is nothing for a belief to be
         about and nothing for a surplus curve to sweep; the record says so and the name
         does not enter the frontier *)
      | `Bdc_nav _ -> None
  in
  (* The market-implied readout maps option quantiles onto long-run GROWTH, so it stays on
     the growth-then-terminal paths only: the residual-income path has no growth axis, and
     (58) giving it a belief did not give it one. *)
  let growth_axis_of (inputs : model_inputs) =
      match axis_of inputs with
      | Some (axis, _, _, rate, f) when axis = Beliefs.growth_axis -> Some (rate, f)
      | _ -> None
  in
  let belief_of ~price ~fair_value (inputs : model_inputs) =
    match axis_of inputs with
    | None -> Error Sensitivity.no_projection
    | Some (axis, anchor, anchor_name, rate, f) -> (
        let entity_class = match declared with Some c -> Admissibility.class_name c | None -> "" in
        match
          Beliefs.resolve ~classes:params.beliefs ?names:name_beliefs ~ticker:original.ticker ~entity_class
            ~anchor ~anchor_name ()
        with
        | None ->
            Error
              (Printf.sprintf "no belief declared for %s: no class default in reference/beliefs.json and no per-name entry"
                 entity_class)
        | Some (b, source) ->
            let source_kind = if String.length source >= 8 && String.sub source 0 8 = "per-name" then "name" else "class" in
            let implied, implied_domain, outcome =
              if axis = Beliefs.roe_axis then Beliefs.implied_roe_target ~f ~price ~cost_of_equity:anchor
              else Beliefs.implied_terminal_growth ~f ~price ~rate
            in
            Ok
              ( Beliefs.readout b ~source ~source_kind ~axis ~implied ~implied_domain ~outcome ~price ~fair_value,
                Beliefs.surplus_curve b ~f ~price ))
  in
  (* The market-implied readout (36), only under --options: the chain for the name on the
     latest snapshot date, or the reason there is none. *)
  let market_implied_of ~ke ~fair_value (inputs : model_inputs) =
    match options with
    | None -> (None, None)
    | Some lookup -> (
        match lookup original.ticker with
        | Error r -> (None, Some r)
        | Ok chain -> (
            let growth =
              match growth_axis_of inputs with
              | Some (rate, f) -> Ok (rate, f)
              | None -> Error "the residual-income path has no terminal growth; the growth axis is undefined there"
            in
            match Market_implied.of_chain chain ~rf:(rf_of inputs) ~ke ~fair_value ~growth with
            | Ok m -> (Some m, None)
            | Error r -> (None, Some r)))
  in
  let failed ?(fin = original) ?model ?class_check ?inputs ?build_out ?build_out_reason ~floor reason =
    record ~fin ?model ?class_check ?inputs ?build_out ?build_out_reason ~price:fin.price
      ~status:`Failed ~failed_reason:reason ~floor ()
  in
  (* (60) Both declarations or neither: a number with no lag says nothing, and a lag with no
     return says less. The universe loader refuses one without the other; this says so again
     on the record for an ad-hoc run that has neither. *)
  let declaration_build_out () =
    match Option.bind declaration (fun d -> d.build_out_return),
          Option.bind declaration (fun d -> d.build_out_lag_years) with
    | Some r, Some l -> Ok (r, l)
    | _ -> Error "build-out return and lag not declared"
  in
  (* (60) The build-out readout on a record that has already failed: never a fair value, a
     signal or an input to anything, and the record's own reason stands. The rates are the
     ones the DCF would have used for this name, resolved by the same functions. *)
  let build_out_of ~(fin : financials) ~(a : Dcf.assumptions) reason =
    match Build_out.gate ~entity_class:declared ~failed_reason:reason ~periods:fin.periods with
    | None -> (None, None)
    | Some (Error why) -> (None, Some why)
    | Some (Ok ()) -> (
        match (fin.periods, fin.price, fin.market_cap) with
        | [], _, _ | _, None, _ | _, _, None -> (None, Some "no price, market cap or fiscal period")
        | (p : fiscal_period) :: _, Some price, Some market_cap -> (
            match (p.cash, p.total_debt, p.book_equity) with
            | None, _, _ -> (None, Some "the latest fiscal period carries no cash")
            | _, None, _ -> (None, Some "the latest fiscal period carries no total debt")
            | _, _, None -> (None, Some "the latest fiscal period carries no book equity")
            | Some cash, Some total_debt, Some book_equity -> (
                let tax_rate, _ =
                  Dcf.tax_rate ~statutory:a.statutory_tax_rate.value ~pretax_income:p.pretax_income
                    ~tax_provision:p.tax_provision
                in
                let wacc =
                  Dcf.wacc ~cost_of_equity:(Dcf.cost_of_equity a)
                    ~cost_of_debt:(a.risk_free_rate.value +. a.debt_spread.value) ~tax_rate
                    ~market_cap ~total_debt
                in
                match (declaration_build_out ()) with
                | Error why -> (None, Some why)
                | Ok (declared_return, declared_lag_years) -> (
                    match
                      Build_out.of_record ~declared_return ~declared_lag_years ~periods:fin.periods
                        ~price ~market_cap ~cash ~total_debt ~book_equity ~wacc ~tax_rate
                        ~terminal_growth_rate:a.terminal_growth_rate.value ~scope_limits
                    with
                    | Ok block -> (Some block, None)
                    | Error why -> (None, Some why)))))
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
          implied = Result.to_option (Implied.of_inputs inputs ~price);
          implied_reason = (match Implied.of_inputs inputs ~price with Error r -> Some r | Ok _ -> None);
          sensitivity = Result.to_option (Sensitivity.of_inputs params.params.sensitivity_steps inputs ~fair_value);
          sensitivity_reason =
            (match Sensitivity.of_inputs params.params.sensitivity_steps inputs ~fair_value with
            | Error r -> Some r
            | Ok _ -> None);
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
          market_implied =
            (* (68) marked, never reselected: the expiry is the one the readout already chose *)
            mark_earnings
              (fst (market_implied_of ~ke:(Dcf.cost_of_equity assumptions) ~fair_value inputs))
              (fst (earnings_of (Some inputs)));
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
    (* (60) A refusal on one of the two build-out classes carries the readout, or the reason
       it has none; every other refusal carries neither field. *)
    let failed_with_build_out reason =
      let build_out, build_out_reason = build_out_of ~fin ~a:assumptions reason in
      failed ?build_out ?build_out_reason reason
    in
    let finish ~price inputs fair_value =
      let inputs =
        match conversion with Some c -> with_conversion c inputs | None -> inputs
      in
      conclude ~fin ~model ~class_check ~rule ~price ~assumptions inputs fair_value
    in
    match model with
    | `Dcf -> (
        match ebit_policy fin with
        | Error reason -> { (failed reason) with rd_shadow_reason = Some "no completed DCF to shadow" }
        | Ok () -> (
            let class_name = match declared with Some c -> Admissibility.class_name c | None -> "" in
            match Dcf.value ~declared:class_name assumptions ~country fin with
            | Error reason ->
                { (failed_with_build_out reason) with rd_shadow_reason = Some "no completed DCF to shadow" }
            | Ok (inputs, fair_value) ->
                (* The R&D shadow rides beside whatever the headline concludes, a gate's
                   refusal included: it is computed from the same statements and moves nothing. *)
                let rd_shadow, rd_shadow_reason =
                  Rd_shadow.of_dcf ~declared:class_name ~life:params.params.rd_amortization_years assumptions ~country fin
                    ~headline:(inputs, fair_value)
                in
                { (finish ~price:inputs.price (`Dcf inputs) fair_value) with rd_shadow; rd_shadow_reason }))
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
            | Error reason -> failed_with_build_out reason
            | Ok (inputs, fair_value) -> finish ~price:inputs.dcf.price (`Dcf_midcycle inputs) fair_value))
    | `Bdc_nav -> (
        (* (59) No EBIT policy and no parameter: the anchor is the filed mark. *)
        match Bdc.value assumptions ~country fin with
        | Error reason -> failed reason
        | Ok (inputs, fair_value) -> finish ~price:inputs.price (`Bdc_nav inputs) fair_value)
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
        (* (54) A domicile reference/rate_sources.json declares to have no reachable
           official curve, and that indeed has none, discounts at the currency its
           statements and price are both in and keeps its own country risk premium; the
           risk-free parameter's source records that the rate is the trading currency's.
           Any other domicile without a curve fails naming the curve, as before. *)
        let resolved =
          if
            (not (Params.has_curve params.risk_free ~country))
            && Params.no_curve_declared params.rate_sources ~country
          then
            Result.bind (Fx.country_of params.fx_sources trading) (fun rate_country ->
                Params.resolve_cross ~hold_vintage ~rf_note:no_curve_rf_note params ~today
                  ~domicile:country ~rate_country ~industry:original.industry)
          else Params.resolve ~hold_vintage params ~today ~country ~industry:original.industry
        in
        match resolved with
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
  (* Before anything else: a ticker that no longer names the declared filer is another
     company's data under this entry's class and scope limits, and nothing below is safe. *)
  match original.identity_mismatch with
  | Some why -> failed ~floor:(floor_default ()) ("ticker identity: " ^ why)
  | None -> (
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
                      | Some country -> value ~model ~class_check ~rule ~country))))))

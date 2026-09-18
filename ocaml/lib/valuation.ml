open Boundary_t

type thresholds = { buy_above : float; sell_below : float; sanity_bound : float }

let default_thresholds = { buy_above = 0.25; sell_below = -0.25; sanity_bound = 5.0 }

let signal t margin_of_safety : signal =
  if margin_of_safety >= t.buy_above then `Buy
  else if margin_of_safety <= t.sell_below then `Sell
  else `Hold

type declaration = {
  entity_class : entity_class;
  lens_note : string;
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
  in
  { present = Some true; basis }

let run ?(thresholds = default_thresholds) (params : Params.t) ~today ~declaration
    (fin : financials) : valuation =
  let declared = Option.map (fun d -> d.entity_class) declaration in
  let lens_note, scope_limits =
    match declaration with
    | Some d -> (d.lens_note, d.scope_limits)
    | None -> ("", [])
  in
  let record ?model ?class_check ?inputs ?fair_value ?margin_of_safety ?signal
      ?failed_reason ~price ~status ~floor () =
    {
      ticker = fin.ticker;
      as_of = fin.as_of;
      valued_on = today;
      currency = fin.currency;
      price;
      fair_value;
      margin_of_safety;
      signal;
      entity_class = declared;
      model;
      class_check;
      floor;
      lens_note;
      scope_limits;
      status;
      failed_reason;
      inputs;
    }
  in
  let failed ?model ?class_check ?inputs ~floor reason =
    record ?model ?class_check ?inputs ~price:fin.price ~status:`Failed
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
  let conclude ~model ~class_check ~rule ~price (inputs : model_inputs) fair_value =
    let failed = failed ~model ~class_check ~inputs ~floor:(floor_of_rule rule) in
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
        record ~model ~class_check ~inputs ~fair_value ~margin_of_safety
          ~signal:(signal thresholds margin_of_safety)
          ~price:(Some price) ~status:`Ok
          ~floor:(floor_verified ~currency inputs ~fair_value)
          ()
  in
  let run_model ~model ~class_check ~rule ~country assumptions =
    let failed = failed ~model ~class_check ~floor:(floor_of_rule rule) in
    match model with
    | `Dcf -> (
        match Dcf.value assumptions ~country fin with
        | Error reason -> failed reason
        | Ok (inputs, fair_value) ->
            conclude ~model ~class_check ~rule ~price:inputs.price (`Dcf inputs) fair_value)
    | `Residual_income -> (
        match Params.bank_terminal_roe_spread params ~today with
        | Error reason -> failed reason
        | Ok terminal_spread -> (
            match Residual_income.value assumptions ~terminal_spread ~country fin with
            | Error reason -> failed reason
            | Ok (inputs, fair_value) ->
                conclude ~model ~class_check ~rule ~price:inputs.price
                  (`Residual_income inputs) fair_value))
    | `Residual_income_insurer -> (
        match Params.insurer_terminal_roe_spread params ~today with
        | Error reason -> failed reason
        | Ok terminal_spread -> (
            match Insurer.value assumptions ~terminal_spread ~country fin with
            | Error reason -> failed reason
            | Ok (inputs, fair_value) ->
                conclude ~model ~class_check ~rule ~price:inputs.core.price
                  (`Residual_income_insurer inputs) fair_value))
  in
  match Params.classification_threshold params ~today with
  | Error reason -> failed ~floor:(floor_default ()) reason
  | Ok threshold -> (
      let s = Classify.signature ~threshold fin in
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
                      match fin.country with
                      | None ->
                          failed ~model ~class_check ~floor:(floor_of_rule rule)
                            "country not determinable from the fetch"
                      | Some country -> (
                          match
                            Params.resolve params ~today ~country ~industry:fin.industry
                          with
                          | Error reason ->
                              failed ~model ~class_check ~floor:(floor_of_rule rule) reason
                          | Ok assumptions ->
                              run_model ~model ~class_check ~rule ~country assumptions))))))

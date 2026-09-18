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

let floor_verified ~currency ~(inputs : inputs) ~fair_value : floor =
  {
    present = Some true;
    basis =
      Printf.sprintf
        "dcf: fcff %.4g %s for the fiscal period ending %s, fair value %.2f %s per share \
         against price %.2f"
        inputs.fcff currency inputs.fiscal_period_end fair_value currency inputs.price;
  }

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
  (* The floor for a record that never reached a model: the class default if the
     declaration has a row, else not assessable. *)
  let floor_default () =
    match Option.bind declared (fun c -> Result.to_option (Admissibility.rule params.admissibility c)) with
    | Some r -> floor_of_rule r
    | None -> floor_undeclared
  in
  let dcf ~class_check ~rule ~country assumptions =
    let failed = failed ~model:`Dcf ~class_check in
    match Dcf.value assumptions ~country fin with
    | Error reason -> failed ~floor:(floor_of_rule rule) reason
    | Ok (inputs, fair_value) ->
        if fair_value <= 0. then
          failed ~inputs ~floor:(floor_of_rule rule)
            (Printf.sprintf "non-positive fair value %g: model not applicable"
               fair_value)
        else
          let margin_of_safety = (fair_value -. inputs.price) /. inputs.price in
          if margin_of_safety > thresholds.sanity_bound then
            failed ~inputs ~floor:(floor_of_rule rule)
              (Printf.sprintf
                 "margin of safety %.2f exceeds sanity bound %.2f: likely structural \
                  break; check entity_class"
                 margin_of_safety thresholds.sanity_bound)
          else
            let currency = Option.value fin.currency ~default:"" in
            record ~model:`Dcf ~class_check ~inputs ~fair_value ~margin_of_safety
              ~signal:(signal thresholds margin_of_safety)
              ~price:(Some inputs.price) ~status:`Ok
              ~floor:(floor_verified ~currency ~inputs ~fair_value)
              ()
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
              | Ok rule ->
                  if not (Admissibility.admits rule `Dcf) then
                    failed ~class_check ~floor:(floor_of_rule rule)
                      (Printf.sprintf "dcf not admissible for %s; lens: %s"
                         (Admissibility.class_name cls) rule.lens)
                  else
                    match fin.country with
                    | None ->
                        failed ~model:`Dcf ~class_check ~floor:(floor_of_rule rule)
                          "country not determinable from the fetch"
                    | Some country -> (
                        match
                          Params.resolve params ~today ~country ~industry:fin.industry
                        with
                        | Error reason ->
                            failed ~model:`Dcf ~class_check ~floor:(floor_of_rule rule)
                              reason
                        | Ok assumptions -> dcf ~class_check ~rule ~country assumptions))))

open Boundary_t

type thresholds = { buy_above : float; sell_below : float; sanity_bound : float }

let default_thresholds = { buy_above = 0.25; sell_below = -0.25; sanity_bound = 5.0 }

let signal t margin_of_safety : signal =
  if margin_of_safety >= t.buy_above then `Buy
  else if margin_of_safety <= t.sell_below then `Sell
  else `Hold

let run ?(thresholds = default_thresholds) (params : Params.t) ~today
    (fin : financials) : valuation =
  let failed ?model ?classification ?inputs reason =
    {
      ticker = fin.ticker;
      as_of = fin.as_of;
      valued_on = today;
      currency = fin.currency;
      price = fin.price;
      fair_value = None;
      margin_of_safety = None;
      signal = None;
      model;
      classification;
      status = `Failed;
      failed_reason = Some reason;
      inputs;
    }
  in
  let generic ~classification ~country assumptions =
    let failed = failed ~model:`Generic ~classification in
    match Dcf.value assumptions ~country fin with
    | Error reason -> failed reason
    | Ok (inputs, fair_value) ->
        if fair_value <= 0. then
          failed ~inputs
            (Printf.sprintf "non-positive fair value %g: model not applicable"
               fair_value)
        else
          let margin_of_safety = (fair_value -. inputs.price) /. inputs.price in
          if margin_of_safety > thresholds.sanity_bound then
            failed ~inputs
              (Printf.sprintf "margin of safety %.2f exceeds sanity bound %.2f"
                 margin_of_safety thresholds.sanity_bound)
          else
            {
              ticker = fin.ticker;
              as_of = fin.as_of;
              valued_on = today;
              currency = fin.currency;
              price = Some inputs.price;
              fair_value = Some fair_value;
              margin_of_safety = Some margin_of_safety;
              signal = Some (signal thresholds margin_of_safety);
              model = Some `Generic;
              classification = Some classification;
              status = `Ok;
              failed_reason = None;
              inputs = Some inputs;
            }
  in
  let not_implemented classification model =
    failed ~model ~classification
      (Printf.sprintf "model not implemented: %s" (Classify.model_name model))
  in
  match Params.classification_threshold params ~today with
  | Error reason -> failed reason
  | Ok threshold -> (
      let outcome, classification = Classify.classify ~threshold fin in
      match outcome with
      | Classify.Unresolved reason -> failed ~classification reason
      | Classify.Classified `Bank -> not_implemented classification `Bank
      | Classify.Classified `Insurer -> not_implemented classification `Insurer
      | Classify.Classified `Generic -> (
          match fin.country with
          | None ->
              failed ~model:`Generic ~classification
                "country not determinable from the fetch"
          | Some country -> (
              match
                Params.resolve params ~today ~country ~industry:fin.industry
              with
              | Error reason -> failed ~model:`Generic ~classification reason
              | Ok assumptions -> generic ~classification ~country assumptions)))

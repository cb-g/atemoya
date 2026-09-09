open Boundary_t

type thresholds = { buy_above : float; sell_below : float; sanity_bound : float }

let default_thresholds = { buy_above = 0.25; sell_below = -0.25; sanity_bound = 5.0 }

let signal t margin_of_safety : signal =
  if margin_of_safety >= t.buy_above then `Buy
  else if margin_of_safety <= t.sell_below then `Sell
  else `Hold

let run ?(assumptions = Dcf.us_defaults) ?(thresholds = default_thresholds)
    (fin : financials) : valuation =
  let model = Classify.classify fin in
  let failed ?inputs reason =
    {
      ticker = fin.ticker;
      as_of = fin.as_of;
      currency = fin.currency;
      price = fin.price;
      fair_value = None;
      margin_of_safety = None;
      signal = None;
      model;
      status = `Failed;
      failed_reason = Some reason;
      inputs;
    }
  in
  match model with
  | `Generic -> (
      match Dcf.value assumptions fin with
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
                (Printf.sprintf
                   "margin of safety %.2f exceeds sanity bound %.2f"
                   margin_of_safety thresholds.sanity_bound)
            else
              {
                ticker = fin.ticker;
                as_of = fin.as_of;
                currency = fin.currency;
                price = Some inputs.price;
                fair_value = Some fair_value;
                margin_of_safety = Some margin_of_safety;
                signal = Some (signal thresholds margin_of_safety);
                model;
                status = `Ok;
                failed_reason = None;
                inputs = Some inputs;
              })

open Boundary_t

let capped_historical (i : inputs) =
  Option.map
    (fun g -> match i.roic with Some roic when g > roic -> (roic, `Historical_capped_at_roic) | _ -> (g, `Historical))
    i.g_historical

let fundamental (i : inputs) =
  match (i.g_fundamental, i.reinvestment_rate) with
  | Some g, Some rr when i.nopat > 0. && rr > 0. -> Some (g, `Fundamental)
  | _ -> None

let higher (i : inputs) =
  match (fundamental i, capped_historical i) with
  | Some (f, fs), Some (h, hs) -> if h > f then Some (h, hs) else Some (f, fs)
  | Some x, None | None, Some x -> Some x
  | None, None -> None

let scope_limits =
  [ "the higher of two estimates is a rule, not a forecast: it removes the switch at zero net reinvestment and says nothing about which estimate is right for a name";
    "revenue history is held to the return on capital, as on the headline, and still reads a rebound or an acquisition as growth";
    "a shadow: the record's fair value, margin of safety and signal are the headline's and are not moved by this block" ]

let of_inputs (i : inputs) ~fair_value =
  let selected, source =
    match higher i with Some x -> x | None -> (i.g0, i.growth_source)
  in
  let g0_shadow, clamped = Growth.clamp ~lower:i.growth_clamp_lower.value ~upper:i.growth_clamp_upper.value selected in
  let shadow_value = Implied.dcf_fair_value i ~g0:g0_shadow ~lambda:i.mean_reversion_lambda.value in
  {
    rule = "the higher of the fundamental estimate and the historical one held to the return on capital";
    g_fundamental = Option.map fst (fundamental i);
    g_historical = i.g_historical;
    g_historical_capped = Option.map fst (capped_historical i);
    g0 = i.g0;
    growth_source = i.growth_source;
    g0_shadow;
    growth_source_shadow = source;
    growth_clamped_shadow = clamped;
    headline_fair_value = fair_value;
    fair_value = shadow_value;
    margin_of_safety = (shadow_value -. i.price) /. i.price;
    scope_limits;
  }

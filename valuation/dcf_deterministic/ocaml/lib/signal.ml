(** Investment signal generation and analysis *)

type valuation_relationship =
  | Above
  | Fair
  | Below

let classify_valuation ~intrinsic_value ~market_price ~tolerance =
  let ratio = intrinsic_value /. market_price in
  if ratio > (1.0 +. tolerance) then
    Above  (* Undervalued *)
  else if ratio < (1.0 -. tolerance) then
    Below  (* Overvalued *)
  else
    Fair   (* Fairly valued *)

let classify_investment_signal ~ivps_fcfe ~ivps_fcff ~market_price ~tolerance =
  let open Types in

  let fcfe_rel = classify_valuation ~intrinsic_value:ivps_fcfe ~market_price ~tolerance in
  let fcff_rel = classify_valuation ~intrinsic_value:ivps_fcff ~market_price ~tolerance in

  match fcfe_rel, fcff_rel with
  | Above, Above -> StrongBuy
  | Fair, Above -> Buy
  | Above, Fair -> BuyEquityUpside
  | Below, Above -> CautionLong
  | Fair, Fair -> Hold
  | Above, Below -> CautionLeverage
  | Below, Fair -> SpeculativeHighLeverage
  | Fair, Below -> SpeculativeExecutionRisk
  | Below, Below -> Avoid

let calculate_margin_of_safety ~intrinsic_value ~market_price =
  if market_price = 0.0 then
    0.0
  else
    (intrinsic_value -. market_price) /. market_price

let signal_to_string = function
  | Types.StrongBuy -> "Strong Buy"
  | Types.Buy -> "Buy"
  | Types.BuyEquityUpside -> "Buy (Equity Upside)"
  | Types.CautionLong -> "Caution (Long)"
  | Types.Hold -> "Hold"
  | Types.CautionLeverage -> "Caution (Leverage)"
  | Types.SpeculativeHighLeverage -> "Speculative (High Leverage)"
  | Types.SpeculativeExecutionRisk -> "Speculative (Execution Risk)"
  | Types.Avoid -> "Avoid/Sell"

let signal_to_colored_string signal =
  (* ANSI color codes *)
  let bold_green = "\027[1;32m" in      (* Strong Buy *)
  let green = "\027[0;32m" in           (* Buy *)
  let bright_green = "\027[0;92m" in    (* Buy (Equity Upside) *)
  let yellow = "\027[0;33m" in          (* Caution signals *)
  let bright_yellow = "\027[0;93m" in   (* Hold *)
  let orange = "\027[0;91m" in          (* Speculative signals *)
  let bold_red = "\027[1;31m" in        (* Avoid *)
  let reset = "\027[0m" in

  let color_code = match signal with
    | Types.StrongBuy -> bold_green
    | Types.Buy -> green
    | Types.BuyEquityUpside -> bright_green
    | Types.CautionLong -> yellow
    | Types.Hold -> bright_yellow
    | Types.CautionLeverage -> yellow
    | Types.SpeculativeHighLeverage -> orange
    | Types.SpeculativeExecutionRisk -> orange
    | Types.Avoid -> bold_red
  in

  Printf.sprintf "%s%s%s" color_code (signal_to_string signal) reset

let signal_explanation = function
  | Types.StrongBuy ->
      "Both FCFE and FCFF valuations exceed market price. Assets underpriced with healthy capital structure."
  | Types.Buy ->
      "Firm value (FCFF) exceeds price, equity value (FCFE) fairly valued. Solid fundamentals."
  | Types.BuyEquityUpside ->
      "Equity value (FCFE) exceeds price, firm value (FCFF) fairly valued. Equity holders capture disproportionate value."
  | Types.CautionLong ->
      "Firm value (FCFF) exceeds price, but equity value (FCFE) below price. Assets cheap but debt absorbs value."
  | Types.Hold ->
      "Both valuations near market price. Fairly valued, no significant mispricing."
  | Types.CautionLeverage ->
      "Equity value (FCFE) exceeds price, but firm value (FCFF) below. Business fundamentally weak despite equity appearing cheap."
  | Types.SpeculativeHighLeverage ->
      "Equity value (FCFE) below price, firm value (FCFF) fairly valued. High leverage compresses equity value."
  | Types.SpeculativeExecutionRisk ->
      "Equity value (FCFE) fairly valued, but firm value (FCFF) below price. Business fundamentals weak."
  | Types.Avoid ->
      "Both valuations below market price. Insufficient cash flows to justify current valuation."

(** Cash flow calculations for DCF valuation *)

let calculate_fcfe ~financial_data ~market_data =
  let open Types in

  (* Calculate reinvestment: CapEx + ΔWC - Depreciation *)
  let reinvestment =
    financial_data.capex +. financial_data.delta_wc -. financial_data.depreciation
  in

  (* Calculate Target Debt Ratio (TDR) = MVB / (MVE + MVB) *)
  let total_value = market_data.mve +. market_data.mvb in
  let tdr =
    if total_value = 0.0 then 0.0
    else market_data.mvb /. total_value
  in

  (* Calculate net borrowing to maintain leverage ratio:
     Net_Borrowing = TDR × Reinvestment *)
  let net_borrowing = tdr *. reinvestment in

  (* FCFE = NI + D - CapEx - ΔWC + Net_Borrowing
          = NI + D - (CapEx + ΔWC) + Net_Borrowing
          = NI + D - Reinvestment + Net_Borrowing *)
  financial_data.net_income
    +. financial_data.depreciation
    -. reinvestment
    +. net_borrowing

let calculate_nopat ~ebit ~tax_rate =
  (* NOPAT = EBIT × (1 - tax_rate) *)
  ebit *. (1.0 -. tax_rate)

let calculate_fcff ~financial_data ~tax_rate =
  let open Types in

  (* Calculate NOPAT *)
  let nopat = calculate_nopat ~ebit:financial_data.ebit ~tax_rate in

  (* FCFF = NOPAT + D - CapEx - ΔWC *)
  nopat
    +. financial_data.depreciation
    -. financial_data.capex
    -. financial_data.delta_wc

(** Cash flow calculations for DCF valuation *)

(** Calculate Free Cash Flow to Equity (FCFE):
    FCFE = NI + D - CapEx - ΔWC + Net_Borrowing
    where Net_Borrowing = TDR × (CapEx + ΔWC - D) to maintain leverage ratio *)
val calculate_fcfe :
  financial_data:Types.financial_data ->
  market_data:Types.market_data ->
  float

(** Calculate NOPAT (Net Operating Profit After Tax):
    NOPAT = EBIT × (1 - tax_rate) *)
val calculate_nopat :
  ebit:float ->
  tax_rate:float ->
  float

(** Calculate Free Cash Flow to Firm (FCFF):
    FCFF = NOPAT + D - CapEx - ΔWC *)
val calculate_fcff :
  financial_data:Types.financial_data ->
  tax_rate:float ->
  float

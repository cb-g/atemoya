(** Investment signal generation and analysis *)

(** Valuation relationship to market price *)
type valuation_relationship =
  | Above  (** Intrinsic value > market price (undervalued) *)
  | Fair   (** Intrinsic value ≈ market price (fairly valued, within tolerance) *)
  | Below  (** Intrinsic value < market price (overvalued) *)

(** Classify valuation relationship using tolerance band (default ±5%) *)
val classify_valuation :
  intrinsic_value:float ->
  market_price:float ->
  tolerance:float ->
  valuation_relationship

(** Generate 9-category investment signal based on dual valuation:
    - StrongBuy: Both FCFE and FCFF > price
    - Buy: FCFF > price, FCFE ≈ price
    - BuyEquityUpside: FCFE > price, FCFF ≈ price
    - CautionLong: FCFF > price, FCFE < price
    - Hold: Both ≈ price
    - CautionLeverage: FCFE > price, FCFF < price
    - SpeculativeHighLeverage: FCFE < price, FCFF ≈ price
    - SpeculativeExecutionRisk: FCFE ≈ price, FCFF < price
    - Avoid: Both < price *)
val classify_investment_signal :
  ivps_fcfe:float ->
  ivps_fcff:float ->
  market_price:float ->
  tolerance:float ->
  Types.investment_signal

(** Calculate margin of safety: (intrinsic_value - market_price) / market_price *)
val calculate_margin_of_safety :
  intrinsic_value:float ->
  market_price:float ->
  float

(** Convert investment signal to human-readable string *)
val signal_to_string : Types.investment_signal -> string

(** Convert investment signal to colored string using ANSI codes *)
val signal_to_colored_string : Types.investment_signal -> string

(** Get a brief explanation of what the signal means *)
val signal_explanation : Types.investment_signal -> string

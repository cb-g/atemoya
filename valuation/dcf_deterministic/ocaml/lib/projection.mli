(** Multi-year cash flow projection *)

(** Project FCFE over h years:
    FCFE_t = FCFE_0 × (1 + g)^t for t = 1..h *)
val project_fcfe :
  fcfe_0:float ->
  growth_rate:float ->
  years:int ->
  float array  (** Array indexed 0..(years-1) representing years 1..h *)

(** Project FCFF over h years:
    FCFF_t = FCFF_0 × (1 + g)^t for t = 1..h *)
val project_fcff :
  fcff_0:float ->
  growth_rate:float ->
  years:int ->
  float array  (** Array indexed 0..(years-1) representing years 1..h *)

(** Create complete cash flow projection *)
val create_projection :
  financial_data:Types.financial_data ->
  market_data:Types.market_data ->
  tax_rate:float ->
  params:Types.valuation_params ->
  Types.cash_flow_projection

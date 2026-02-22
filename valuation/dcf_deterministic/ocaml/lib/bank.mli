(** Bank valuation using Excess Return Model

    Banks are valued as:
    Fair Value = Book Value + PV of Future Excess Returns
    where Excess Return = (ROE - Cost of Equity) × Book Value

    This model is more appropriate than FCFF/FCFE for banks because:
    - Interest expense is operating cost for banks
    - Deposits (debt) are the raw material of the business
    - Regulatory capital requirements drive growth constraints
*)

(** Calculate bank-specific metrics from financial data *)
val calculate_bank_metrics :
  financial:Types.financial_data ->
  market:Types.market_data ->
  Types.bank_metrics

(** Calculate cost of equity for a bank using CAPM with bank-specific beta *)
val calculate_bank_cost_of_equity :
  risk_free_rate:float ->
  equity_risk_premium:float ->
  market:Types.market_data ->
  float

(** Calculate present value of excess returns stream *)
val calculate_excess_return_value :
  roe:float ->
  cost_of_equity:float ->
  book_value:float ->
  growth_rate:float ->
  projection_years:int ->
  terminal_growth:float ->
  float

(** Solve for implied ROE given market price *)
val solve_implied_roe :
  market_price:float ->
  book_value:float ->
  cost_of_equity:float ->
  shares_outstanding:float ->
  growth_rate:float ->
  projection_years:int ->
  terminal_growth:float ->
  float option

(** Calculate fair value using Price-to-Book method *)
val value_by_price_to_book :
  book_value_per_share:float ->
  target_pb:float ->
  float

(** Target P/BV based on ROE vs Cost of Equity *)
val calculate_target_pb :
  roe:float ->
  cost_of_equity:float ->
  growth_rate:float ->
  float

(** Generate investment signal for bank *)
val classify_bank_signal :
  ivps:float ->
  market_price:float ->
  metrics:Types.bank_metrics ->
  cost_of_equity:float ->
  Types.investment_signal

(** Full bank valuation using excess return model *)
val value_bank :
  financial:Types.financial_data ->
  market:Types.market_data ->
  risk_free_rate:float ->
  equity_risk_premium:float ->
  terminal_growth_rate:float ->
  projection_years:int ->
  Types.bank_valuation_result

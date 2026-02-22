(** Sensitivity analysis for DCF valuation parameters *)

(** Sensitivity result for a single parameter value *)
type sensitivity_point = {
  param_value : float;
  fcfe_ivps : float;
  fcff_ivps : float;
}

(** Complete sensitivity analysis results *)
type sensitivity_results = {
  growth_rate : sensitivity_point list;
  discount_rate : sensitivity_point list;
  terminal_growth : sensitivity_point list;
}

(** Run comprehensive sensitivity analysis for a ticker

    @param market_data Market data for the ticker
    @param financial_data Financial statements data
    @param config Base configuration (provides defaults)
    @param cost_of_capital Base cost of capital calculation
    @param tax_rate Corporate tax rate
    @return Sensitivity analysis results across all parameters
*)
val run_sensitivity_analysis :
  market_data:Types.market_data ->
  financial_data:Types.financial_data ->
  config:Types.config ->
  cost_of_capital:Types.cost_of_capital ->
  tax_rate:float ->
  sensitivity_results

(** Write sensitivity results to CSV files

    @param output_dir Directory to write CSV files
    @param ticker Ticker symbol (for filename)
    @param results Sensitivity analysis results
    @param market_price Current market price (for reference)
*)
val write_sensitivity_csv :
  output_dir:string ->
  ticker:string ->
  results:sensitivity_results ->
  market_price:float ->
  unit

(** Specialized sensitivity point (single fair value, not FCFE/FCFF pair) *)
type specialized_point = {
  param_value : float;
  fair_value : float;
}

(** Bank sensitivity results *)
type bank_sensitivity_results = {
  roe : specialized_point list;
  cost_of_equity : specialized_point list;
  growth : specialized_point list;
}

(** Insurance sensitivity results *)
type insurance_sensitivity_results = {
  combined_ratio : specialized_point list;
  investment_yield : specialized_point list;
  ins_cost_of_equity : specialized_point list;
}

(** Oil & Gas sensitivity results *)
type oil_gas_sensitivity_results = {
  oil_price : specialized_point list;
  lifting_cost : specialized_point list;
  og_discount_rate : specialized_point list;
}

val run_bank_sensitivity :
  financial:Types.financial_data ->
  market:Types.market_data ->
  risk_free_rate:float ->
  equity_risk_premium:float ->
  terminal_growth_rate:float ->
  projection_years:int ->
  bank_sensitivity_results

val write_bank_sensitivity_csv :
  output_dir:string ->
  ticker:string ->
  results:bank_sensitivity_results ->
  market_price:float ->
  unit

val run_insurance_sensitivity :
  financial:Types.financial_data ->
  market:Types.market_data ->
  risk_free_rate:float ->
  equity_risk_premium:float ->
  terminal_growth_rate:float ->
  projection_years:int ->
  insurance_sensitivity_results

val write_insurance_sensitivity_csv :
  output_dir:string ->
  ticker:string ->
  results:insurance_sensitivity_results ->
  market_price:float ->
  unit

val run_oil_gas_sensitivity :
  financial:Types.financial_data ->
  market:Types.market_data ->
  risk_free_rate:float ->
  equity_risk_premium:float ->
  tax_rate:float ->
  oil_price:float ->
  gas_price:float ->
  oil_gas_sensitivity_results

val write_oil_gas_sensitivity_csv :
  output_dir:string ->
  ticker:string ->
  results:oil_gas_sensitivity_results ->
  market_price:float ->
  unit

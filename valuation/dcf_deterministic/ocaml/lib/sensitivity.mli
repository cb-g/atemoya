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

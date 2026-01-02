(** I/O operations for configuration and data files *)

(** Load valuation parameters from JSON file *)
val load_params : string -> Types.valuation_params

(** Load risk-free rates from JSON file *)
val load_risk_free_rates : string -> (Types.country * (int * float) list) list

(** Load equity risk premiums from JSON file *)
val load_equity_risk_premiums : string -> (Types.country * float) list

(** Load industry betas from JSON file *)
val load_industry_betas : string -> (Types.industry * float) list

(** Load corporate tax rates from JSON file *)
val load_tax_rates : string -> (Types.country * float) list

(** Load complete configuration from data directory *)
val load_config : string -> Types.config

(** Load market data from JSON file (output from Python fetcher) *)
val load_market_data : string -> Types.market_data

(** Load financial data from JSON file (output from Python fetcher) *)
val load_financial_data : string -> Types.financial_data

(** Format a valuation result as a human-readable string *)
val format_valuation_result : Types.valuation_result -> string

(** Write valuation result to log file *)
val write_log : filename:string -> result:Types.valuation_result -> unit

(** Create log filename with timestamp *)
val create_log_filename : base_dir:string -> ticker:Types.ticker -> string

(** Write scenario comparison to CSV file *)
val write_scenario_csv : filename:string -> comparison:Scenarios.scenario_comparison -> unit

(** Format scenario comparison as human-readable string *)
val format_scenario_comparison : Scenarios.scenario_comparison -> string

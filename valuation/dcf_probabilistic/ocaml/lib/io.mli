(** I/O operations for probabilistic DCF *)

(** Load simulation configuration from JSON *)
val load_simulation_config : string -> Types.simulation_config

(** Load Bayesian priors from JSON (returns list of sector -> priors mappings) *)
val load_bayesian_priors : string -> (Types.sector * Types.sector_priors) list

(** Load risk-free rates, ERPs, betas, tax rates (shared with deterministic) *)
val load_risk_free_rates : string -> (Types.country * (int * float) list) list
val load_equity_risk_premiums : string -> (Types.country * float) list
val load_industry_betas : string -> (Types.industry * float) list
val load_tax_rates : string -> (Types.country * float) list

(** Load complete configuration *)
val load_config : string -> Types.config

(** Get priors for a specific sector (fallback to default if not found) *)
val get_sector_priors : Types.config -> Types.sector -> Types.sector_priors

(** Load market data from JSON *)
val load_market_data : string -> Types.market_data

(** Load time series data from JSON *)
val load_time_series : string -> Types.time_series

(** Write simulation results to CSV *)
val write_summary_csv : filename:string -> results:Types.valuation_result list -> unit

(** Write simulation matrices to CSV (for visualization) *)
val write_simulation_matrices :
  fcfe_file:string ->
  fcff_file:string ->
  results:Types.valuation_result list ->
  unit

(** Write market prices to CSV (for visualization reference) *)
val write_market_prices : filename:string -> results:Types.valuation_result list -> unit

(** Format valuation result as human-readable string *)
val format_valuation_result : Types.valuation_result -> string

(** Write valuation result to log file *)
val write_log : filename:string -> result:Types.valuation_result -> unit

(** Create log filename with timestamp *)
val create_log_filename : base_dir:string -> ticker:Types.ticker -> string

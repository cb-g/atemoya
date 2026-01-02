(** Statistical analysis for probabilistic DCF *)

(** Compute valuation statistics from simulation results *)
val compute_statistics : float array -> Types.valuation_statistics

(** Compute probability metrics relative to market price *)
val compute_probability_metrics :
  simulations:float array ->
  price:float ->
  Types.probability_metrics

(** Compute tail risk metrics (VaR, CVaR, max drawdown) *)
val compute_tail_risk_metrics :
  simulations:float array ->
  price:float ->
  Types.tail_risk_metrics

(** Classify valuation relationship to market price *)
val classify_valuation :
  mean_ivps:float ->
  price:float ->
  tolerance:float ->
  Types.valuation_class

(** Generate investment signal from FCFE and FCFF classifications *)
val generate_signal :
  fcfe_class:Types.valuation_class ->
  fcff_class:Types.valuation_class ->
  Types.investment_signal

(** Convert investment signal to string *)
val signal_to_string : Types.investment_signal -> string

(** Convert investment signal to colored string using ANSI codes *)
val signal_to_colored_string : Types.investment_signal -> string

(** Get signal explanation *)
val signal_explanation : Types.investment_signal -> string

(** Convert valuation class to string *)
val class_to_string : Types.valuation_class -> string

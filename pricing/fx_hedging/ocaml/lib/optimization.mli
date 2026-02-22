(* Interface for hedge ratio optimization *)

(** Minimum variance hedge ratio **)

(* Calculate minimum variance hedge ratio

   h* = Cov(ΔS, ΔF) / Var(ΔF)

   Estimated from historical data:
   h* ≈ ρ × (σ_S / σ_F)

   where:
     ΔS = change in spot exposure
     ΔF = change in futures
     ρ = correlation
     σ_S, σ_F = standard deviations
*)
val min_variance_hedge_ratio :
  exposure_returns:float array ->
  futures_returns:float array ->
  float

(* Calculate minimum variance hedge ratio using regression

   Regress spot returns on futures returns:
   R_spot = α + β × R_futures + ε

   Optimal hedge ratio h* = β
*)
val regression_hedge_ratio :
  exposure_returns:float array ->
  futures_returns:float array ->
  float

(** Optimal hedge with costs **)

(* Calculate optimal hedge ratio considering transaction costs

   Trades off variance reduction vs hedging costs

   U = -λ × Var(hedged) - Cost(hedge)

   where λ = risk aversion parameter
*)
val optimal_hedge_with_costs :
  exposure_returns:float array ->
  futures_returns:float array ->
  transaction_cost_bps:float ->
  risk_aversion:float ->
  float

(** Cross-hedge optimization **)

(* Optimal hedge using multiple instruments

   For example: hedge EUR exposure using both EUR/USD and GBP/USD futures
*)
val multi_instrument_hedge :
  exposure_returns:float array ->
  futures_returns_array:float array array ->  (* Multiple futures series *)
  float array  (* Hedge ratios for each futures *)

(** Statistical measures **)

(* Calculate correlation between two series *)
val correlation :
  series1:float array ->
  series2:float array ->
  float

(* Calculate covariance *)
val covariance :
  series1:float array ->
  series2:float array ->
  float

(* Calculate variance *)
val variance :
  series:float array ->
  float

(* Calculate standard deviation *)
val std_dev :
  series:float array ->
  float

(* Calculate beta (sensitivity) *)
val beta :
  dependent:float array ->
  independent:float array ->
  float

(** Hedge effectiveness metrics **)

(* Calculate R² (coefficient of determination) *)
val r_squared :
  actual:float array ->
  predicted:float array ->
  float

(* Calculate hedge effectiveness ratio

   HE = 1 - Var(hedged) / Var(unhedged)
*)
val hedge_effectiveness_ratio :
  unhedged_returns:float array ->
  hedged_returns:float array ->
  float

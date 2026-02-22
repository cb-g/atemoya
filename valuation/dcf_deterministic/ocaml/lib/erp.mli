(** Equity Risk Premium (ERP) Calculation Module

    Provides static (Damodaran) and dynamic (VIX-adjusted) ERP calculation.
*)

(** Default VIX parameters *)
val default_vix_mean : float
val default_vix_sensitivity : float

(** Create a static ERP configuration (Damodaran mode) *)
val default_erp_config : base_erp:float -> Types.erp_config

(** Create a dynamic ERP configuration (VIX-adjusted mode) *)
val dynamic_erp_config :
  base_erp:float ->
  current_vix:float ->
  ?vix_mean:float ->
  ?sensitivity:float ->
  unit -> Types.erp_config

(** Calculate VIX adjustment factor: (VIX / VIX_mean) ^ sensitivity *)
val calculate_vix_adjustment :
  current_vix:float ->
  vix_mean:float ->
  sensitivity:float ->
  float

(** Calculate effective ERP from configuration
    Returns (erp, adjustment_factor) *)
val calculate_erp : Types.erp_config -> float * float

(** Get ERP for a country with optional VIX override
    vix_config = Some (current_vix, vix_mean, sensitivity) for dynamic mode *)
val get_erp_for_country :
  erp_list:(Types.country * float) list ->
  country:Types.country ->
  ?vix_config:(float * float * float) ->
  unit -> float * float

(** Describe ERP source for logging/display *)
val describe_erp_source : Types.erp_config -> float * float -> string

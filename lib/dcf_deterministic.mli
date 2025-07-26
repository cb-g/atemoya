val calculate_cost_of_equity : rfr:float -> beta_l:float -> erp:float -> float
val calculate_leveraged_beta : beta_u:float -> ctr:float -> mvb:float -> mve:float -> float
val calculate_wacc : mve:float -> mvb:float -> ce:float -> cb:float -> ctr:float -> float

val calculate_fcfe :
  ni:float ->
  capx:float -> d:float ->
  ca:float -> cl:float ->
  prev_ca:float -> prev_cl:float ->
  net_borrowing:float -> float

val calculate_fcff :
  ebit:float -> ctr:float -> b:float ->
  capx:float -> ca:float -> cl:float ->
  prev_ca:float -> prev_cl:float -> float

val calculate_fcfe_growth_rate : ni:float -> bve:float -> dp:float -> float
val calculate_fcff_growth_rate :
  ebit:float -> ite:float -> ic:float ->
  capx:float -> d:float -> ca:float -> cl:float -> float

val project_fcfe :
  ni:float -> capx:float -> d:float ->
  ca:float -> cl:float -> tdr:float ->
  years:int -> fcfegr:float -> float list

val project_fcff :
  ebit:float -> ctr:float -> capx:float -> d:float ->
  ca:float -> cl:float -> years:int -> fcffgr:float -> float list

val calculate_pve_from_projection : fcfe_list:float list -> ce:float -> tgr:float -> float
val calculate_pvf_from_projection : fcff_list:float list -> wacc:float -> tgr:float -> float

val average_growth_rate : float list -> float

val implied_fcfe_growth_rate_over_h :
  fcfe0:float -> ce:float -> tgr:float -> h:int -> so:float -> price:float -> float

val implied_fcff_growth_rate_over_h :
  fcff0:float -> wacc:float -> tgr:float -> h:int -> mve:float -> mvb:float -> float

val display_valuation_summary :
  ticker:string -> currency:string ->
  ce:float -> cb:float -> wacc:float ->
  fcfe0:float -> fcff0:float ->
  fcfegr:float -> fcffgr:float ->
  capped_fcfegr:bool -> capped_fcffgr:bool -> floored_fcfegr:bool -> floored_fcffgr:bool ->
  fcfegr_clamp_upper:float -> fcfegr_clamp_lower:float ->
  fcffgr_clamp_upper:float -> fcffgr_clamp_lower:float ->
  tgr:float -> so:float -> price:float ->
  pvf:float -> pve:float ->
  avg_fcfegr:float -> avg_fcffgr:float ->
  implied_fcfegr:float -> implied_fcffgr:float ->
  h:int -> long_name:string -> unit


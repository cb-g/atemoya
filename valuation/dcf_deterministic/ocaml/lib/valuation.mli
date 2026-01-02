(** Present value calculations and terminal value *)

(** Calculate terminal value:
    TV = CF_h × (1 + TGR) / (discount_rate - TGR)
    Returns None if discount_rate <= TGR (invalid) *)
val calculate_terminal_value :
  final_cash_flow:float ->
  terminal_growth_rate:float ->
  discount_rate:float ->
  float option

(** Calculate present value of a cash flow stream plus terminal value:
    PV = Σ[t=1 to h] CF_t / (1 + r)^t + TV / (1 + r)^h *)
val calculate_present_value :
  cash_flows:float array ->
  discount_rate:float ->
  terminal_growth_rate:float ->
  float option  (** Returns None if terminal value calculation fails *)

(** Calculate present value of equity (PVE) from FCFE projection *)
val calculate_pve :
  projection:Types.cash_flow_projection ->
  cost_of_equity:float ->
  terminal_growth_rate:float ->
  float option

(** Calculate present value of firm (PVF) from FCFF projection *)
val calculate_pvf :
  projection:Types.cash_flow_projection ->
  wacc:float ->
  terminal_growth_rate:float ->
  float option

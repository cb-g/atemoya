(** The belief map (23): the whole line between the implied readouts' two ends, on a
    plain-language readout model stated on the record and distinct from the headline's
    decaying path: growth held at g for N years with no decay, then the settled terminal
    growth forever, everything else (discount rate, base cash flow, net debt, shares) at
    its recorded value. The grid (g from 0 to 50% in 2 pp steps, N from 1 to 40) goes to
    a file; the record carries the price contour: for each N, the g at which fair value
    equals price, by bisection on the grid's model, null with reason where no g in the
    domain reaches it. Only the growth-then-terminal paths have a map (dcf, dcf_midcycle,
    reit_ffo_dividend); the residual-income paths are [Error] with the reason. *)

val map_model : string
val growth_domain : float * float
val growth_step : float
val horizon_max : int
val growth_grid : float list
val horizon_grid : int list

val fair_value :
  base:float -> rate:float -> terminal:float -> net_debt:float -> shares:float -> growth:float -> years:int -> float
(** [(sum_(t=1..N) base (1+g)^t / (1+r)^t + base (1+g)^N (1+gT) / (r - gT) / (1+r)^N - net_debt) / shares]. *)

val of_inputs : Boundary_t.model_inputs -> price:float -> (Boundary_t.belief_map, string) result

val grid : Boundary_t.belief_map -> ticker:string -> price:float -> Boundary_t.belief_grid

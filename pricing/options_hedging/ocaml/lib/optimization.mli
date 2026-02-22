(* Multi-Objective Optimization - Pareto Frontier *)

(* Optimization problem specification *)
type optimization_problem = {
  underlying_position : float;
  underlying_data : Types.underlying_data;
  vol_surface : Types.vol_surface;
  rate : float;

  (* Candidate strategies *)
  expiries : float array;
  strike_grid : float array;

  (* Constraints *)
  min_protection : float option;
  max_cost : float option;
  max_contracts : int option;
}

(* Optimization configuration *)
type optimization_config = {
  num_pareto_points : int;
  num_mc_paths : int;
  risk_measure : [ `CVaR | `VaR | `MinValue ];
}

(* Create optimization problem *)
val create_problem :
  underlying_position:float ->
  underlying_data:Types.underlying_data ->
  vol_surface:Types.vol_surface ->
  rate:float ->
  expiries:float array ->
  strike_grid:float array ->
  ?min_protection:float ->
  ?max_cost:float ->
  ?max_contracts:int ->
  unit ->
  optimization_problem

(* Generate Pareto frontier *)
val generate_pareto_frontier :
  optimization_problem ->
  optimization_config ->
  Types.optimization_result

(* Check if strategy is Pareto dominated *)
val is_pareto_dominated :
  Types.pareto_point ->
  candidates:Types.pareto_point array ->
  bool

(* Filter for Pareto efficient points *)
val filter_pareto_efficient :
  Types.pareto_point array ->
  Types.pareto_point array

(* Recommend strategy based on user preference *)
val recommend_strategy :
  Types.pareto_point array ->
  preference:[ `MinCost | `MaxProtection | `Balanced ] ->
  Types.hedge_strategy option

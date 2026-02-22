(* Multi-Objective Optimization - Pareto Frontier *)

open Types

(* Optimization problem specification *)
type optimization_problem = {
  underlying_position : float;
  underlying_data : underlying_data;
  vol_surface : vol_surface;
  rate : float;
  expiries : float array;
  strike_grid : float array;
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
let create_problem
    ~underlying_position
    ~underlying_data
    ~vol_surface
    ~rate
    ~expiries
    ~strike_grid
    ?min_protection
    ?max_cost
    ?max_contracts
    () =
  {
    underlying_position;
    underlying_data;
    vol_surface;
    rate;
    expiries;
    strike_grid;
    min_protection;
    max_cost;
    max_contracts;
  }

(* Check if point is Pareto dominated *)
let is_pareto_dominated point ~candidates =
  (* A point is dominated if there exists another point with:
     - lower or equal cost AND higher protection
     - OR lower cost AND higher or equal protection
  *)
  Array.exists (fun candidate ->
    if candidate == point then false
    else
      let cost_better = candidate.cost < point.cost in
      let cost_equal = abs_float (candidate.cost -. point.cost) < 0.01 in
      let protection_better = candidate.protection_level > point.protection_level in
      let protection_equal = abs_float (candidate.protection_level -. point.protection_level) < 0.01 in

      (cost_better && (protection_better || protection_equal)) ||
      ((cost_better || cost_equal) && protection_better)
  ) candidates

(* Filter for Pareto efficient points *)
let filter_pareto_efficient points =
  Array.of_list (
    List.filter (fun point ->
      not (is_pareto_dominated point ~candidates:points)
    ) (Array.to_list points)
  )

(* Generate candidate strategies for all combinations *)
let generate_candidates problem _config =
  let spot = problem.underlying_data.spot_price in
  let candidates = ref [] in

  (* For each expiry *)
  Array.iter (fun expiry ->

    (* For each strike *)
    Array.iter (fun strike ->
      let moneyness = strike /. spot in

      (* 1. Protective Put (OTM puts, moneyness < 1.0) *)
      if moneyness >= 0.80 && moneyness <= 0.95 then begin
        try
          let strategy = Strategies.protective_put
            ~underlying_position:problem.underlying_position
            ~put_strike:strike
            ~expiry
            ~underlying_data:problem.underlying_data
            ~vol_surface:problem.vol_surface
            ~rate:problem.rate
          in

          (* Check constraints *)
          let passes_constraints =
            (match problem.max_cost with
             | None -> true
             | Some max_cost -> strategy.cost <= max_cost) &&
            (match problem.min_protection with
             | None -> true
             | Some min_prot -> strategy.protection_level >= min_prot) &&
            (match problem.max_contracts with
             | None -> true
             | Some max_contracts -> strategy.contracts <= max_contracts)
          in

          if passes_constraints then
            candidates := { cost = strategy.cost; protection_level = strategy.protection_level; strategy } :: !candidates
        with Failure _ -> ()
      end;

      (* 2. Covered Call (OTM calls, moneyness > 1.0) *)
      if moneyness >= 1.05 && moneyness <= 1.20 then begin
        try
          let strategy = Strategies.covered_call
            ~underlying_position:problem.underlying_position
            ~call_strike:strike
            ~expiry
            ~underlying_data:problem.underlying_data
            ~vol_surface:problem.vol_surface
            ~rate:problem.rate
          in

          if (match problem.max_cost with None -> true | Some mc -> strategy.cost <= mc) then
            candidates := { cost = strategy.cost; protection_level = strategy.protection_level; strategy } :: !candidates
        with Failure _ -> ()
      end;

      (* 3. Collar (OTM put + OTM call) *)
      if moneyness >= 0.85 && moneyness <= 0.95 then begin
        (* Try pairing with OTM calls *)
        Array.iter (fun call_strike ->
          let call_moneyness = call_strike /. spot in
          if call_moneyness >= 1.05 && call_moneyness <= 1.15 then begin
            try
              let strategy = Strategies.collar
                ~underlying_position:problem.underlying_position
                ~put_strike:strike
                ~call_strike
                ~expiry
                ~underlying_data:problem.underlying_data
                ~vol_surface:problem.vol_surface
                ~rate:problem.rate
              in

              if (match problem.max_cost with None -> true | Some mc -> strategy.cost <= mc) then
                candidates := { cost = strategy.cost; protection_level = strategy.protection_level; strategy } :: !candidates
            with Failure _ -> ()
          end
        ) problem.strike_grid
      end;

      (* 4. Vertical Spread (buy OTM put + sell further OTM put) *)
      if moneyness >= 0.85 && moneyness <= 0.95 then begin
        Array.iter (fun short_strike ->
          if short_strike < strike && short_strike /. spot >= 0.75 then begin
            try
              let strategy = Strategies.vertical_put_spread
                ~underlying_position:problem.underlying_position
                ~long_put_strike:strike
                ~short_put_strike:short_strike
                ~expiry
                ~underlying_data:problem.underlying_data
                ~vol_surface:problem.vol_surface
                ~rate:problem.rate
              in

              if (match problem.max_cost with None -> true | Some mc -> strategy.cost <= mc) then
                candidates := { cost = strategy.cost; protection_level = strategy.protection_level; strategy } :: !candidates
            with Failure _ -> ()
          end
        ) problem.strike_grid
      end

    ) problem.strike_grid
  ) problem.expiries;

  Array.of_list !candidates

(* Recommend strategy based on user preference *)
let recommend_strategy frontier ~preference =
  if Array.length frontier = 0 then
    None
  else
    let idx = match preference with
    | `MinCost ->
        (* Find strategy with minimum cost *)
        let min_idx = ref 0 in
        for i = 1 to Array.length frontier - 1 do
          if frontier.(i).cost < frontier.(!min_idx).cost then
            min_idx := i
        done;
        !min_idx

    | `MaxProtection ->
        (* Find strategy with maximum protection *)
        let max_idx = ref 0 in
        for i = 1 to Array.length frontier - 1 do
          if frontier.(i).protection_level > frontier.(!max_idx).protection_level then
            max_idx := i
        done;
        !max_idx

    | `Balanced ->
        (* Find strategy with best cost/protection ratio *)
        (* Normalize both objectives to [0, 1] *)
        let costs = Array.map (fun p -> p.cost) frontier in
        let protections = Array.map (fun p -> p.protection_level) frontier in

        let min_cost = Array.fold_left min Float.infinity costs in
        let max_cost = Array.fold_left max Float.neg_infinity costs in
        let min_prot = Array.fold_left min Float.infinity protections in
        let max_prot = Array.fold_left max Float.neg_infinity protections in

        let cost_range = max_cost -. min_cost in
        let prot_range = max_prot -. min_prot in

        let best_idx = ref 0 in
        let best_score = ref Float.neg_infinity in

        for i = 0 to Array.length frontier - 1 do
          let norm_cost = if cost_range > 0.0 then
            (frontier.(i).cost -. min_cost) /. cost_range
          else 0.5
          in
          let norm_prot = if prot_range > 0.0 then
            (frontier.(i).protection_level -. min_prot) /. prot_range
          else 0.5
          in

          (* Score = protection - cost (both normalized) *)
          let score = norm_prot -. norm_cost in

          if score > !best_score then begin
            best_score := score;
            best_idx := i
          end
        done;
        !best_idx
    in

    Some frontier.(idx).strategy

(* Generate Pareto frontier *)
let generate_pareto_frontier problem config =
  (* Generate all candidate strategies *)
  let candidates = generate_candidates problem config in

  (* Filter for Pareto efficient points *)
  let frontier = filter_pareto_efficient candidates in

  (* Sort by cost (ascending) *)
  Array.sort (fun p1 p2 -> Float.compare p1.cost p2.cost) frontier;

  (* Recommend strategy (default: balanced) *)
  let recommended_strategy = recommend_strategy frontier ~preference:`Balanced in

  {
    pareto_frontier = frontier;
    recommended_strategy;
  }

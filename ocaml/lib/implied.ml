open Boundary_t

type outcome = Root of float | Beyond_high | Beyond_low | Flat

let level_domain = (-0.50, 3.00)
let roe_domain = (-0.50, 1.00)
let lambda_domain = (0.01, 5.0)
let tolerance = 1e-7

let bisect ~f ~target ~lo ~hi ~tolerance =
  let g x = f x -. target in
  let glo = g lo and ghi = g hi in
  if glo = 0. then Root lo
  else if ghi = 0. then Root hi
  else if glo = ghi then Flat
  else if glo *. ghi > 0. then
    (* No root: an increasing f with both ends above the target has its answer below lo;
       both below, above hi. A decreasing f, the reverse. *)
    let increasing = ghi > glo in
    if glo > 0. then (if increasing then Beyond_low else Beyond_high)
    else if increasing then Beyond_high
    else Beyond_low
  else
    let rec go lo glo hi n =
      let mid = 0.5 *. (lo +. hi) in
      if hi -. lo <= tolerance || n = 0 then Root mid
      else
        let gmid = g mid in
        if gmid = 0. then Root mid
        else if gmid *. glo < 0. then go lo glo mid (n - 1)
        else go mid gmid hi (n - 1)
    in
    go lo glo hi 200

let max_horizon = 40

let dcf_fair_value ?projection_years (i : inputs) ~g0 ~lambda =
  let projection_years = Option.value projection_years ~default:i.projection_years.value in
  let terminal_growth_rate = i.terminal_growth_rate.value in
  let growth_path = Growth.path ~g0 ~terminal_growth_rate ~lambda ~projection_years in
  let ev = Dcf.enterprise_value ~fcff:i.fcff ~wacc:i.wacc ~growth_path ~terminal_growth_rate in
  (ev -. i.net_debt) /. i.shares

let residual_income_fair_value ?projection_years (i : residual_income_inputs) ~roe_0 ~lambda =
  let projection_years = Option.value projection_years ~default:i.projection_years.value in
  let roe_path =
    Residual_income.roe_path ~roe_0 ~cost_of_equity:i.cost_of_equity ~lambda ~projection_years
  in
  let s =
    Residual_income.schedule ~book_equity:i.book_equity ~cost_of_equity:i.cost_of_equity
      ~retention:i.retention ~roe_path
  in
  (i.book_equity +. s.pv_excess_returns) /. i.shares

let reit_fair_value ?projection_years (i : reit_inputs) ~g0 ~lambda =
  let projection_years = Option.value projection_years ~default:i.projection_years.value in
  let terminal_growth_rate = i.terminal_growth_rate.value in
  let growth_path = Growth.path ~g0 ~terminal_growth_rate ~lambda ~projection_years in
  let dividend_path = Reit.dividend_path ~d0:i.dividend_per_share ~growth_path in
  let pv, _, pv_terminal = Reit.present_value ~dividend_path ~cost_of_equity:i.cost_of_equity ~terminal_growth_rate in
  pv +. pv_terminal

let readout value = { value = Some value; reason = None }
let null reason = { value = None; reason = Some reason }

(* The level readout: the start at which fair value equals price. *)
let solve_level ~what ~f ~price ~domain:(lo, hi) =
  match bisect ~f ~target:price ~lo ~hi ~tolerance with
  | Root x -> readout x
  | Beyond_high -> null (Printf.sprintf "the price needs a %s above %.2f, the top of the domain" what hi)
  | Beyond_low -> null (Printf.sprintf "the price needs a %s below %.2f, the bottom of the domain" what lo)
  | Flat -> null (Printf.sprintf "fair value does not vary with the %s" what)

(* The half-life readout, holding the observed start: the lambda at which fair value equals
   price, as ln 2 / lambda, only where the start lies above its target. *)
let solve_half_life ~driver ~target_name ~start ~target ~f ~price =
  if start <= target then
    null (Printf.sprintf "observed %s is below %s; persistence is not the question" driver target_name)
  else
    let lo, hi = lambda_domain in
    match bisect ~f ~target:price ~lo ~hi ~tolerance with
    | Root lambda -> readout (log 2. /. lambda)
    | Beyond_low -> null (Printf.sprintf "%s would have to never decay and the price is still above the result" driver)
    | Beyond_high -> null (Printf.sprintf "price is below the no-%s value" driver)
    | Flat -> null (Printf.sprintf "fair value does not vary with the %s half-life" driver)

(* The horizon readout, holding the observed start: the smallest whole number of explicit
   years at which fair value reaches the price, scanned over 1..40 because the explicit
   period is a whole number of years. Under the guard fair value is monotone increasing in
   the horizon and converges, so "not reached at 40" means persistence cannot get there. *)
type horizon = { years : readout; bracket : float list; at_40 : float option }

let solve_horizon ~driver ~target_name ~start ~target ~(f : int -> float) ~price =
  if start <= target then
    { years = null (Printf.sprintf "observed %s is below %s; persistence is not the question" driver target_name);
      bracket = []; at_40 = None }
  else
    let at_40 = f max_horizon in
    if f 1 >= price then
      { years = null "price is at or below the one-year value"; bracket = []; at_40 = Some at_40 }
    else
      let rec scan n previous =
        if n > max_horizon then
          { years =
              null
                (Printf.sprintf
                   "even indefinite persistence of the decaying %s path does not reach the price: fair value at %d years %.2f against price %.2f"
                   driver max_horizon at_40 price);
            bracket = []; at_40 = Some at_40 }
        else
          let current = f n in
          if current >= price then
            { years = readout (float_of_int n); bracket = [ previous; current ]; at_40 = Some at_40 }
          else scan (n + 1) current
      in
      scan 2 (f 1)

let rf_tenor_note = "held at the recorded 7y point, not re-selected per horizon"

let block ~level_name ~level ~level_domain:(lo, hi) ~half_life_years ~horizon ~guard ~guard_rule ~held =
  let llo, lhi = lambda_domain in
  let meaningful, rule =
    if not guard then ("level", guard_rule ^ ": level")
    else
      match horizon.years.value with
      | Some n -> ("horizon", Printf.sprintf "%s; a horizon solves at %.0f years: horizon" guard_rule n)
      | None -> ("level", guard_rule ^ "; no horizon at or below 40 years reaches the price: level")
  in
  {
    level_name;
    level;
    level_domain = [ lo; hi ];
    half_life_years;
    lambda_domain = [ llo; lhi ];
    horizon_years = Some horizon.years;
    horizon_bracket = horizon.bracket;
    fair_value_at_40 = horizon.at_40;
    rf_tenor = rf_tenor_note;
    meaningful_readout = meaningful;
    meaningful_rule = rule;
    solver = "bisection";
    tolerance;
    held = List.map (fun (name, value) -> { name; value }) held;
  }

let of_inputs (m : model_inputs) ~price =
  match m with
  | `Dcf (i : inputs) ->
      let terminal = i.terminal_growth_rate.value in
      let lambda = i.mean_reversion_lambda.value in
      let level =
        solve_level ~what:"starting growth" ~price ~domain:level_domain
          ~f:(fun g0 -> dcf_fair_value i ~g0 ~lambda)
      in
      let half_life_years =
        solve_half_life ~driver:"growth" ~target_name:"terminal" ~start:i.g0 ~target:terminal ~price
          ~f:(fun lambda -> dcf_fair_value i ~g0:i.g0 ~lambda)
      in
      let above = i.g0 > terminal in
      let horizon =
        solve_horizon ~driver:"growth" ~target_name:"terminal" ~start:i.g0 ~target:terminal ~price
          ~f:(fun n -> dcf_fair_value ~projection_years:n i ~g0:i.g0 ~lambda)
      in
      block ~level_name:"implied_g0" ~level ~level_domain ~half_life_years ~horizon ~guard:above
        ~guard_rule:(Printf.sprintf "g0 %.4f %s terminal growth %.4f" i.g0 (if above then ">" else "<=") terminal)
        ~held:
          [ ("fcff", i.fcff); ("wacc", i.wacc); ("terminal_growth_rate", terminal);
            ("projection_years", float_of_int i.projection_years.value); ("net_debt", i.net_debt);
            ("shares", i.shares); ("g0", i.g0); ("mean_reversion_lambda", lambda);
            ("risk_free_rate", i.risk_free_rate.value) ]
  | `Reit_ffo_dividend (i : reit_inputs) ->
      let terminal = i.terminal_growth_rate.value in
      let lambda = i.mean_reversion_lambda.value in
      let level =
        solve_level ~what:"starting growth" ~price ~domain:level_domain ~f:(fun g0 -> reit_fair_value i ~g0 ~lambda)
      in
      let half_life_years =
        solve_half_life ~driver:"growth" ~target_name:"terminal" ~start:i.g0 ~target:terminal ~price
          ~f:(fun lambda -> reit_fair_value i ~g0:i.g0 ~lambda)
      in
      let above = i.g0 > terminal in
      let horizon =
        solve_horizon ~driver:"growth" ~target_name:"terminal" ~start:i.g0 ~target:terminal ~price
          ~f:(fun n -> reit_fair_value ~projection_years:n i ~g0:i.g0 ~lambda)
      in
      block ~level_name:"implied_g0" ~level ~level_domain ~half_life_years ~horizon ~guard:above
        ~guard_rule:(Printf.sprintf "g0 %.4f %s terminal growth %.4f" i.g0 (if above then ">" else "<=") terminal)
        ~held:
          [ ("dividend_per_share", i.dividend_per_share); ("cost_of_equity", i.cost_of_equity);
            ("terminal_growth_rate", terminal); ("projection_years", float_of_int i.projection_years.value);
            ("g0", i.g0); ("mean_reversion_lambda", lambda); ("risk_free_rate", i.risk_free_rate.value) ]
  | `Residual_income i | `Residual_income_insurer { core = i; _ } ->
      let lambda = i.mean_reversion_lambda.value in
      let level =
        solve_level ~what:"starting roe" ~price ~domain:roe_domain
          ~f:(fun roe_0 -> residual_income_fair_value i ~roe_0 ~lambda)
      in
      let half_life_years =
        solve_half_life ~driver:"roe" ~target_name:"the cost of equity" ~start:i.roe_0 ~target:i.cost_of_equity ~price
          ~f:(fun lambda -> residual_income_fair_value i ~roe_0:i.roe_0 ~lambda)
      in
      let above = i.roe_0 > i.cost_of_equity in
      let horizon =
        solve_horizon ~driver:"roe" ~target_name:"the cost of equity" ~start:i.roe_0 ~target:i.cost_of_equity ~price
          ~f:(fun n -> residual_income_fair_value ~projection_years:n i ~roe_0:i.roe_0 ~lambda)
      in
      block ~level_name:"implied_roe0" ~level ~level_domain:roe_domain ~half_life_years ~horizon ~guard:above
        ~guard_rule:(Printf.sprintf "roe_0 %.4f %s cost of equity %.4f" i.roe_0 (if above then ">" else "<=") i.cost_of_equity)
        ~held:
          [ ("book_equity", i.book_equity); ("retention", i.retention); ("cost_of_equity", i.cost_of_equity);
            ("projection_years", float_of_int i.projection_years.value); ("shares", i.shares);
            ("roe_0", i.roe_0); ("mean_reversion_lambda", lambda); ("risk_free_rate", i.risk_free_rate.value) ]

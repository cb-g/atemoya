(** Implied growth rate solver using Newton-Raphson + bisection *)

(** Calculate PV as a function of growth rate for FCFE *)
let pv_fcfe ~fcfe_0 ~growth_rate ~cost_of_equity ~terminal_growth_rate ~years =
  if growth_rate >= cost_of_equity || growth_rate >= terminal_growth_rate then
    None  (* Invalid parameters *)
  else
    (* Project cash flows *)
    let cash_flows = Projection.project_fcfe ~fcfe_0 ~growth_rate ~years in
    (* Calculate PV *)
    Valuation.calculate_present_value
      ~cash_flows
      ~discount_rate:cost_of_equity
      ~terminal_growth_rate

(** Calculate PV as a function of growth rate for FCFF *)
let pv_fcff ~fcff_0 ~growth_rate ~wacc ~terminal_growth_rate ~years =
  if growth_rate >= wacc || growth_rate >= terminal_growth_rate then
    None  (* Invalid parameters *)
  else
    (* Project cash flows *)
    let cash_flows = Projection.project_fcff ~fcff_0 ~growth_rate ~years in
    (* Calculate PV *)
    Valuation.calculate_present_value
      ~cash_flows
      ~discount_rate:wacc
      ~terminal_growth_rate

(** Numerical derivative approximation *)
let derivative ~f ~x ~h =
  match f (x +. h), f (x -. h) with
  | Some f_plus, Some f_minus -> Some ((f_plus -. f_minus) /. (2.0 *. h))
  | _ -> None

(** Bisection method fallback *)
let rec bisection ~f ~target ~lower ~upper ~tolerance ~max_iterations =
  if max_iterations <= 0 then
    None
  else
    let mid = (lower +. upper) /. 2.0 in
    match f mid with
    | None -> None  (* Function evaluation failed *)
    | Some f_mid ->
        let error = f_mid -. target in
        if abs_float error < tolerance then
          Some mid
        else if error > 0.0 then
          (* PV too high, need lower growth rate *)
          bisection ~f ~target ~lower ~upper:mid ~tolerance ~max_iterations:(max_iterations - 1)
        else
          (* PV too low, need higher growth rate *)
          bisection ~f ~target ~lower:mid ~upper ~tolerance ~max_iterations:(max_iterations - 1)

(** Newton-Raphson method with bisection fallback *)
let solve_for_growth ~f ~target ~initial_guess ~lower_bound ~upper_bound ~tolerance ~max_iterations =
  let h = 0.0001 in  (* Step size for numerical derivative *)

  let rec newton_raphson ~x ~iterations =
    if iterations >= max_iterations then
      (* Newton-Raphson didn't converge, fall back to bisection *)
      bisection ~f ~target ~lower:lower_bound ~upper:upper_bound ~tolerance ~max_iterations
    else
      match f x, derivative ~f ~x ~h with
      | Some f_x, Some f_prime when f_prime <> 0.0 ->
          let error = f_x -. target in
          if abs_float error < tolerance then
            Some x
          else
            (* Newton-Raphson update: x_new = x - (f(x) - target) / f'(x) *)
            let x_new = x -. (error /. f_prime) in
            (* Keep x within bounds *)
            let x_new = max lower_bound (min upper_bound x_new) in
            newton_raphson ~x:x_new ~iterations:(iterations + 1)
      | _ ->
          (* Derivative is zero or function failed, fall back to bisection *)
          bisection ~f ~target ~lower:lower_bound ~upper:upper_bound ~tolerance ~max_iterations
  in

  newton_raphson ~x:initial_guess ~iterations:0

let solve_implied_fcfe_growth
    ~fcfe_0
    ~shares_outstanding
    ~market_price
    ~cost_of_equity
    ~terminal_growth_rate
    ~projection_years
    ~max_iterations
    ~tolerance =

  (* Target: total equity value = market_price × shares_outstanding *)
  let target_equity_value = market_price *. shares_outstanding in

  (* PV function *)
  let f growth_rate =
    pv_fcfe ~fcfe_0 ~growth_rate ~cost_of_equity ~terminal_growth_rate ~years:projection_years
  in

  (* Initial guess: middle of reasonable range *)
  let initial_guess = (terminal_growth_rate +. 0.05) /. 2.0 in

  (* Bounds: growth must be less than cost of equity and terminal growth rate *)
  let lower_bound = -0.5 in
  let upper_bound = min (cost_of_equity -. 0.001) (terminal_growth_rate -. 0.001) in

  if upper_bound <= lower_bound then
    None  (* No valid solution possible *)
  else
    solve_for_growth
      ~f
      ~target:target_equity_value
      ~initial_guess
      ~lower_bound
      ~upper_bound
      ~tolerance
      ~max_iterations

let solve_implied_fcff_growth
    ~fcff_0
    ~shares_outstanding
    ~market_price
    ~debt
    ~wacc
    ~terminal_growth_rate
    ~projection_years
    ~max_iterations
    ~tolerance =

  (* Target: total firm value = (market_price × shares_outstanding) + debt *)
  let target_firm_value = (market_price *. shares_outstanding) +. debt in

  (* PV function *)
  let f growth_rate =
    pv_fcff ~fcff_0 ~growth_rate ~wacc ~terminal_growth_rate ~years:projection_years
  in

  (* Initial guess: middle of reasonable range *)
  let initial_guess = (terminal_growth_rate +. 0.05) /. 2.0 in

  (* Bounds: growth must be less than WACC and terminal growth rate *)
  let lower_bound = -0.5 in
  let upper_bound = min (wacc -. 0.001) (terminal_growth_rate -. 0.001) in

  if upper_bound <= lower_bound then
    None  (* No valid solution possible *)
  else
    solve_for_growth
      ~f
      ~target:target_firm_value
      ~initial_guess
      ~lower_bound
      ~upper_bound
      ~tolerance
      ~max_iterations

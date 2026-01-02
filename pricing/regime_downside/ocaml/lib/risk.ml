(** Risk measure calculations for downside optimization *)

open Types

(** Calculate Lower Partial Moment of order 1
    LPM1 = E[(tau - a_t)_+]
    where (x)_+ = max(0, x) *)
let lpm1 ~threshold ~active_returns =
  let n = Array.length active_returns in
  if n = 0 then 0.0
  else
    let sum_shortfalls =
      Array.fold_left
        (fun acc a_t ->
          let shortfall = threshold -. a_t in
          acc +. max 0.0 shortfall)
        0.0
        active_returns
    in
    sum_shortfalls /. float_of_int n

(** Calculate Conditional Value at Risk at 95% confidence level
    CVaR = eta + (1 / (alpha * T)) * sum(u_t)
    where u_t >= max(0, loss_t - eta)
    and loss_t = max(0, -a_t) *)
let cvar_95 ~active_returns =
  let n = Array.length active_returns in
  if n = 0 then 0.0
  else
    let alpha = 0.05 in

    (* Calculate active losses: l_t = max(0, -a_t) *)
    let losses =
      Array.map (fun a_t -> max 0.0 (-.a_t)) active_returns
    in

    (* Sort losses to find VaR (eta) *)
    let sorted_losses = Array.copy losses in
    Array.sort compare sorted_losses;

    (* VaR at 95% is the (1-alpha) quantile *)
    let var_idx = int_of_float (float_of_int n *. (1.0 -. alpha)) in
    let var_idx = min var_idx (n - 1) in
    let eta = sorted_losses.(var_idx) in

    (* Calculate CVaR using the dual formulation *)
    let sum_exceedances =
      Array.fold_left
        (fun acc loss_t ->
          let u_t = max 0.0 (loss_t -. eta) in
          acc +. u_t)
        0.0
        losses
    in

    eta +. (sum_exceedances /. (alpha *. float_of_int n))

(** Calculate portfolio beta given weights and asset betas *)
let portfolio_beta ~weights ~asset_betas =
  List.fold_left
    (fun acc (ticker, weight) ->
      match List.assoc_opt ticker asset_betas with
      | Some beta -> acc +. (weight *. beta)
      | None -> acc  (* Asset not found, assume beta = 0 *)
    )
    0.0
    weights.assets

(** Calculate all risk metrics for given active returns, weights, and betas *)
let calculate_risk_metrics ~threshold ~active_returns ~weights ~asset_betas =
  {
    lpm1 = lpm1 ~threshold ~active_returns;
    cvar_95 = cvar_95 ~active_returns;
    portfolio_beta = portfolio_beta ~weights ~asset_betas;
  }

(* FX Exposure Analysis *)

open Types

(** Portfolio exposure calculation **)

(* Aggregate exposures by currency *)
let calculate_portfolio_exposure ~positions =
  (* Build a hash table to accumulate exposures by currency *)
  let exposure_map = Hashtbl.create 10 in

  (* Iterate through positions and accumulate exposures *)
  Array.iter (fun pos ->
    List.iter (fun (curr, pct) ->
      let exposure_usd = pos.market_value_usd *. pct in

      let current =
        try Hashtbl.find exposure_map curr
        with Not_found -> { currency = curr; net_exposure_usd = 0.0; pct_of_portfolio = 0.0; positions = [] }
      in

      let updated = {
        current with
        net_exposure_usd = current.net_exposure_usd +. exposure_usd;
        positions = pos :: current.positions;
      }
      in
      Hashtbl.replace exposure_map curr updated
    ) pos.currency_exposure
  ) positions;

  (* Calculate total portfolio value *)
  let total_value = Array.fold_left (fun acc pos -> acc +. pos.market_value_usd) 0.0 positions in

  (* Convert hash table to array and calculate percentages *)
  let exposures = Hashtbl.fold (fun _curr exp acc ->
    let exp_with_pct = {
      exp with
      pct_of_portfolio = if total_value > 0.0 then
        (exp.net_exposure_usd /. total_value) *. 100.0
      else 0.0
    } in
    exp_with_pct :: acc
  ) exposure_map [] in

  Array.of_list exposures

(* Net exposure for single currency *)
let net_currency_exposure ~positions ~currency =
  Array.fold_left (fun acc pos ->
    let curr_exposure = List.fold_left (fun sum (curr, pct) ->
      if curr = currency then
        sum +. (pos.market_value_usd *. pct)
      else
        sum
    ) 0.0 pos.currency_exposure in
    acc +. curr_exposure
  ) 0.0 positions

(* Total portfolio value *)
let total_portfolio_value ~positions =
  Array.fold_left (fun acc pos -> acc +. pos.market_value_usd) 0.0 positions

(* Exposure percentages *)
let exposure_percentages ~positions =
  let exposures = calculate_portfolio_exposure ~positions in
  Array.to_list (Array.map (fun exp -> (exp.currency, exp.pct_of_portfolio)) exposures)

(** Hedge sizing **)

(* Hedge notional = exposure × hedge ratio *)
let hedge_notional ~exposure_usd ~hedge_ratio =
  exposure_usd *. abs_float hedge_ratio

(* Number of futures contracts

   Contracts = (Exposure × Hedge_Ratio) / (Futures_Price × Contract_Size)
*)
let futures_contracts_needed ~exposure_usd ~hedge_ratio ~futures_price ~contract_size =
  let notional = hedge_notional ~exposure_usd ~hedge_ratio in
  let notional_per_contract = futures_price *. contract_size in
  let contracts_exact = notional /. notional_per_contract in

  (* Round to nearest integer, preserve sign *)
  let sign = if hedge_ratio >= 0.0 then 1 else -1 in
  sign * int_of_float (abs_float contracts_exact +. 0.5)

(* Number of options contracts (delta-adjusted)

   For options, need to account for delta:
   Contracts = (Exposure × Hedge_Ratio) / (Delta × Futures_Price × Contract_Size)
*)
let options_contracts_needed ~exposure_usd ~hedge_ratio ~option_delta ~futures_price ~contract_size =
  if abs_float option_delta < 0.01 then
    0  (* Delta too small *)
  else
    let notional = hedge_notional ~exposure_usd ~hedge_ratio in
    let notional_per_contract = abs_float option_delta *. futures_price *. contract_size in
    let contracts_exact = notional /. notional_per_contract in

    let sign = if hedge_ratio >= 0.0 then 1 else -1 in
    sign * int_of_float (abs_float contracts_exact +. 0.5)

(** Direct vs Indirect exposure **)

(* Split exposure into direct and indirect components

   Direct: Position is denominated in foreign currency (100% exposure)
   Indirect: Position has partial exposure through revenue/operations
*)
let split_direct_indirect ~position =
  let direct = ref 0.0 in
  let indirect = ref 0.0 in

  List.iter (fun (_curr, pct) ->
    let exposure = position.market_value_usd *. pct in
    if pct >= 0.99 then
      direct := !direct +. exposure
    else
      indirect := !indirect +. exposure
  ) position.currency_exposure;

  (!direct, !indirect)

(* FX beta (sensitivity to FX rate changes)

   For now, assume beta ≈ exposure percentage
   More sophisticated: regress position returns on FX returns
*)
let fx_beta ~position ~currency =
  List.fold_left (fun acc (curr, pct) ->
    if curr = currency then pct else acc
  ) 0.0 position.currency_exposure

(** Risk metrics **)

(* Value at Risk from FX exposure

   VaR_α = Exposure × σ × √(T/252) × z_α

   where:
     α = confidence level (e.g., 0.95)
     z_α = standard normal quantile
     σ = annual FX volatility
     T = horizon in days
*)
let fx_var ~exposure_usd ~fx_volatility ~confidence_level ~horizon_days =
  (* Standard normal quantiles *)
  let z_score = match confidence_level with
    | x when x >= 0.99 -> 2.33  (* 99% *)
    | x when x >= 0.95 -> 1.65  (* 95% *)
    | x when x >= 0.90 -> 1.28  (* 90% *)
    | _ -> 1.65  (* default to 95% *)
  in

  let horizon_years = float_of_int horizon_days /. 252.0 in
  let horizon_vol = fx_volatility *. sqrt horizon_years in

  abs_float exposure_usd *. horizon_vol *. z_score

(* Expected Shortfall (Conditional VaR)

   ES_α = Exposure × σ × √(T/252) × φ(z_α) / (1 - α)

   where:
     φ = standard normal PDF
*)
let fx_cvar ~exposure_usd ~fx_volatility ~confidence_level ~horizon_days =
  let var = fx_var ~exposure_usd ~fx_volatility ~confidence_level ~horizon_days in

  (* CVaR ≈ VaR × 1.3 for normal distribution (approximate) *)
  var *. 1.3

(** Scenario analysis **)

(* P&L from FX rate change

   P&L = Exposure × (Rate_new - Rate_old) / Rate_old
*)
let fx_scenario_pnl ~exposure_usd ~fx_rate_initial ~fx_rate_scenario =
  let pct_change = (fx_rate_scenario -. fx_rate_initial) /. fx_rate_initial in
  exposure_usd *. pct_change

(* Portfolio-level scenario analysis *)
let portfolio_fx_scenario ~positions ~fx_shocks =
  let exposures = calculate_portfolio_exposure ~positions in

  Array.fold_left (fun total_pnl exp ->
    (* Find shock for this currency *)
    let shock = List.fold_left (fun acc (curr, shock_pct) ->
      if curr = exp.currency then shock_pct else acc
    ) 0.0 fx_shocks in

    (* Calculate P&L impact *)
    let pnl = exp.net_exposure_usd *. shock in
    total_pnl +. pnl
  ) 0.0 exposures

(** Probabilistic O&G valuation using NAV Model

    Monte Carlo simulation of:
    FV = PV(Reserves) - Debt

    Stochastic inputs per iteration:
    - Oil price: lognormal around current (~25% annual vol)
    - Gas price: lognormal around current (~30% annual vol)
    - Lifting cost: normal with 10% perturbation
    - Discount rate: regime-switching sampling
*)

open Types

let mcf_per_boe = 6.0

(** Calculate PV of proven reserves with decline curve *)
let calculate_reserve_value ~proven_reserves ~production_boe_day ~oil_pct
    ~lifting_cost ~oil_price ~gas_price ~discount_rate ~tax_rate =
  if proven_reserves <= 0.0 || production_boe_day <= 0.0 then 0.0
  else if discount_rate <= 0.0 then 0.0
  else
    let reserves_boe = proven_reserves *. 1_000_000.0 in
    let initial_annual_production = production_boe_day *. 365.0 in
    let reserve_life = reserves_boe /. initial_annual_production in
    let projection_years = int_of_float (min reserve_life 30.0) in
    let decline_rate = 0.08 in

    let revenue_per_boe =
      oil_pct *. oil_price +. (1.0 -. oil_pct) *. gas_price *. mcf_per_boe
    in

    let rec project_pv acc year remaining_reserves production =
      if year > projection_years || remaining_reserves <= 0.0 then acc
      else
        let actual_production = min production remaining_reserves in
        let revenue = actual_production *. revenue_per_boe in
        let operating_cost = actual_production *. lifting_cost in
        let operating_profit = revenue -. operating_cost in
        let after_tax_cf = operating_profit *. (1.0 -. tax_rate) in
        let discount_factor = (1.0 +. discount_rate) ** float_of_int year in
        let pv = after_tax_cf /. discount_factor in
        let next_production = production *. (1.0 -. decline_rate) in
        let next_reserves = remaining_reserves -. actual_production in
        project_pv (acc +. pv) (year + 1) next_reserves next_production
    in
    project_pv 0.0 1 reserves_boe initial_annual_production

(** Simulate one O&G fair value *)
let simulate_oil_gas_once ~(og_data : oil_gas_data) ~(market_data : market_data)
    ~(cost_of_capital : cost_of_capital) ~(config : simulation_config)
    ~tax_rate ~base_oil_price ~base_gas_price =

  (* Sample oil price: lognormal with ~25% vol *)
  let oil_price = Sampling.lognormal_sample ~mean:base_oil_price ~std:(base_oil_price *. 0.25) in
  let oil_price = Sampling.clamp ~value:oil_price ~lower:20.0 ~upper:200.0 in

  (* Sample gas price: lognormal with ~30% vol *)
  let gas_price = Sampling.lognormal_sample ~mean:base_gas_price ~std:(base_gas_price *. 0.30) in
  let gas_price = Sampling.clamp ~value:gas_price ~lower:1.0 ~upper:15.0 in

  (* Sample lifting cost: normal with 10% perturbation *)
  let lifting_cost = Sampling.gaussian_sample
    ~mean:og_data.og_lifting_cost
    ~std:(og_data.og_lifting_cost *. 0.10)
  in
  let lifting_cost = Sampling.clamp ~value:lifting_cost ~lower:2.0 ~upper:50.0 in

  (* Sample discount rate using regime-switching *)
  let discount_rate =
    match config.regime_config with
    | Some regime_config ->
      let (rfr, erp, beta, _) = Sampling.sample_discount_rates_regime_switching
        ~base_rfr:cost_of_capital.risk_free_rate
        ~base_erp:cost_of_capital.equity_risk_premium
        ~base_beta:cost_of_capital.leveraged_beta
        ~regime_config
      in
      rfr +. (beta *. erp)
    | None ->
      Sampling.gaussian_sample ~mean:cost_of_capital.wacc ~std:0.01
  in

  let reserve_value = calculate_reserve_value
    ~proven_reserves:og_data.og_proven_reserves
    ~production_boe_day:og_data.og_production_boe_day
    ~oil_pct:og_data.og_oil_pct
    ~lifting_cost ~oil_price ~gas_price
    ~discount_rate ~tax_rate
  in

  let nav = reserve_value -. og_data.og_debt in
  if market_data.shares_outstanding > 0.0 then
    nav /. market_data.shares_outstanding
  else 0.0

let run_oil_gas_simulations ~oil_gas_data ~market_data ~cost_of_capital
    ~(config : simulation_config) ~tax_rate ~oil_price ~gas_price =
  Array.init config.num_simulations (fun _ ->
    simulate_oil_gas_once ~og_data:oil_gas_data ~market_data ~cost_of_capital ~config
      ~tax_rate ~base_oil_price:oil_price ~base_gas_price:gas_price
  )

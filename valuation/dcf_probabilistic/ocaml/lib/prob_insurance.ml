(** Probabilistic insurance valuation using Float-Based Model

    Monte Carlo simulation of:
    FV = Book Value + PV(Underwriting Profits) + Float Value

    Stochastic inputs per iteration:
    - Combined ratio: sampled from historical CR distribution
    - Investment yield: sampled from historical yield distribution
    - Cost of Equity: regime-switching sampling
    - Premium growth: small perturbation around 3%
*)

open Types

(** Calculate PV of underwriting profits *)
let calculate_underwriting_value ~premiums ~combined_ratio ~cost_of_equity
    ~growth_rate ~projection_years ~terminal_growth =
  if cost_of_equity <= terminal_growth then 0.0
  else if combined_ratio >= 1.0 then 0.0
  else
    let target_cr = 0.98 in
    let lambda = 0.10 in
    let rec project_value acc year prem current_cr =
      if year > projection_years then acc
      else
        let underwriting_profit = prem *. (1.0 -. current_cr) in
        let discount_factor = (1.0 +. cost_of_equity) ** float_of_int year in
        let pv = underwriting_profit /. discount_factor in
        let next_prem = prem *. (1.0 +. growth_rate) in
        let next_cr = current_cr +. lambda *. (target_cr -. current_cr) in
        project_value (acc +. pv) (year + 1) next_prem next_cr
    in
    let explicit_pv = project_value 0.0 1 premiums combined_ratio in
    let terminal_cr = min combined_ratio target_cr in
    let terminal_premium =
      premiums *. ((1.0 +. growth_rate) ** float_of_int projection_years)
    in
    let terminal_profit = terminal_premium *. (1.0 -. terminal_cr) in
    let terminal_value = terminal_profit /. (cost_of_equity -. terminal_growth) in
    let terminal_pv =
      terminal_value /. ((1.0 +. cost_of_equity) ** float_of_int projection_years)
    in
    explicit_pv +. terminal_pv

(** Calculate value of float *)
let calculate_float_value ~float_amount ~investment_yield ~combined_ratio
    ~cost_of_equity ~terminal_growth =
  if cost_of_equity <= terminal_growth || float_amount <= 0.0 then 0.0
  else
    let cost_of_float =
      if combined_ratio > 1.0 then combined_ratio -. 1.0
      else 0.0
    in
    let float_benefit_rate = investment_yield -. cost_of_float in
    if float_benefit_rate <= 0.0 then 0.0
    else
      let annual_float_benefit = float_amount *. float_benefit_rate in
      annual_float_benefit /. (cost_of_equity -. terminal_growth)

(** Simulate one insurance fair value *)
let simulate_insurance_once ~(ins_data : insurance_data) ~(market_data : market_data)
    ~(cost_of_capital : cost_of_capital) ~(config : simulation_config) =

  (* Sample combined ratio from historical distribution *)
  let cr_mean = Sampling.mean ins_data.ins_cr_history in
  let cr_std = Sampling.std ins_data.ins_cr_history in
  let cr_std = if cr_std < 0.01 then 0.03 else cr_std in
  let cr_sampled = Sampling.gaussian_sample ~mean:cr_mean ~std:cr_std in
  let cr_sampled = Sampling.clamp ~value:cr_sampled ~lower:0.70 ~upper:1.20 in

  (* Sample investment yield from historical distribution *)
  let yield_mean = Sampling.mean ins_data.ins_yield_history in
  let yield_std = Sampling.std ins_data.ins_yield_history in
  let yield_std = if yield_std < 0.005 then 0.01 else yield_std in
  let yield_sampled = Sampling.gaussian_sample ~mean:yield_mean ~std:yield_std in
  let yield_sampled = Sampling.clamp ~value:yield_sampled ~lower:0.01 ~upper:0.10 in

  (* Sample cost of equity using regime-switching *)
  let cost_of_equity =
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
      Sampling.gaussian_sample ~mean:cost_of_capital.ce ~std:0.01
  in

  (* Sample premium growth rate *)
  let prem_growth = Sampling.gaussian_sample ~mean:0.03 ~std:0.015 in
  let prem_growth = Sampling.clamp ~value:prem_growth ~lower:(-0.05) ~upper:0.10 in

  let projection_years = config.projection_years in
  let terminal_growth = config.terminal_growth_rate in

  let underwriting_value = calculate_underwriting_value
    ~premiums:ins_data.ins_premiums ~combined_ratio:cr_sampled ~cost_of_equity
    ~growth_rate:prem_growth ~projection_years ~terminal_growth
  in

  let float_value = calculate_float_value
    ~float_amount:ins_data.ins_float_amount ~investment_yield:yield_sampled
    ~combined_ratio:cr_sampled ~cost_of_equity ~terminal_growth
  in

  let fair_value = ins_data.ins_book_value +. underwriting_value +. float_value in
  if market_data.shares_outstanding > 0.0 then
    fair_value /. market_data.shares_outstanding
  else 0.0

let run_insurance_simulations ~insurance_data ~market_data ~cost_of_capital
    ~(config : simulation_config) =
  Array.init config.num_simulations (fun _ ->
    simulate_insurance_once ~ins_data:insurance_data ~market_data ~cost_of_capital ~config
  )

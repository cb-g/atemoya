(** Probabilistic bank valuation using Excess Return Model

    Monte Carlo simulation of:
    FV = Book Value + PV(Excess Returns)
    where Excess Return = (ROE - CoE) * BV

    Stochastic inputs per iteration:
    - ROE: sampled from historical ROE distribution
    - Cost of Equity: regime-switching sampling
    - BV growth rate: small perturbation around 3%
*)

open Types

(** Calculate PV of excess returns for one simulation *)
let calculate_excess_return_value ~roe ~cost_of_equity
    ~book_value ~growth_rate ~projection_years ~terminal_growth =
  if cost_of_equity <= terminal_growth then 0.0
  else
    let lambda = 0.15 in
    let rec project_value acc year bv current_roe =
      if year > projection_years then acc
      else
        let excess_return = (current_roe -. cost_of_equity) *. bv in
        let discount_factor = (1.0 +. cost_of_equity) ** float_of_int year in
        let pv_excess = excess_return /. discount_factor in
        let retention_rate = 0.6 in
        let earnings = current_roe *. bv in
        let retained = earnings *. retention_rate in
        let next_bv = bv +. retained +. (bv *. growth_rate *. 0.3) in
        let next_roe = current_roe +. lambda *. (cost_of_equity -. current_roe) in
        project_value (acc +. pv_excess) (year + 1) next_bv next_roe
    in
    let explicit_pv = project_value 0.0 1 book_value roe in

    (* Terminal value *)
    let terminal_roe_spread = 0.02 in
    let terminal_roe = cost_of_equity +. terminal_roe_spread in
    let rec terminal_bv bv current_roe year =
      if year > projection_years then bv
      else
        let retention_rate = 0.6 in
        let earnings = current_roe *. bv in
        let retained = earnings *. retention_rate in
        let next_bv = bv +. retained +. (bv *. growth_rate *. 0.3) in
        let next_roe = current_roe +. lambda *. (cost_of_equity -. current_roe) in
        terminal_bv next_bv next_roe (year + 1)
    in
    let final_bv = terminal_bv book_value roe 1 in
    let terminal_excess = (terminal_roe -. cost_of_equity) *. final_bv in
    let terminal_value = terminal_excess /. (cost_of_equity -. terminal_growth) in
    let terminal_pv =
      terminal_value /. ((1.0 +. cost_of_equity) ** float_of_int projection_years)
    in
    explicit_pv +. terminal_pv

(** Simulate one bank fair value *)
let simulate_bank_once ~(bank_data : bank_data) ~(market_data : market_data)
    ~(cost_of_capital : cost_of_capital) ~(config : simulation_config) =

  (* Sample ROE from historical distribution *)
  let roe_mean = Sampling.mean bank_data.bank_roe_history in
  let roe_std = Sampling.std bank_data.bank_roe_history in
  let roe_std = if roe_std < 0.01 then 0.02 else roe_std in
  let roe_sampled = Sampling.gaussian_sample ~mean:roe_mean ~std:roe_std in
  let roe_sampled = Sampling.clamp ~value:roe_sampled ~lower:(-0.10) ~upper:0.40 in

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
      Sampling.gaussian_sample
        ~mean:cost_of_capital.ce
        ~std:0.01
  in

  (* Sample BV growth rate *)
  let bv_growth = Sampling.gaussian_sample ~mean:0.03 ~std:0.01 in
  let bv_growth = Sampling.clamp ~value:bv_growth ~lower:(-0.02) ~upper:0.08 in

  let projection_years = config.projection_years in
  let terminal_growth = config.terminal_growth_rate in

  let excess_pv = calculate_excess_return_value
    ~roe:roe_sampled ~cost_of_equity
    ~book_value:bank_data.bank_book_value
    ~growth_rate:bv_growth ~projection_years ~terminal_growth
  in

  let fair_value = bank_data.bank_book_value +. excess_pv in
  if market_data.shares_outstanding > 0.0 then
    fair_value /. market_data.shares_outstanding
  else 0.0

let run_bank_simulations ~bank_data ~market_data ~cost_of_capital
    ~(config : simulation_config) =
  Array.init config.num_simulations (fun _ ->
    simulate_bank_once ~bank_data ~market_data ~cost_of_capital ~config
  )

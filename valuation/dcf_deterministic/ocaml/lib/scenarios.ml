(** Scenario analysis: bull, base, and bear valuations *)

type scenario_type =
  | Bull
  | Base
  | Bear
[@@deriving show]

type scenario_adjustment = {
  growth_delta : float;
  discount_rate_delta : float;
}
[@@deriving show]

type scenario_result = {
  scenario : scenario_type;
  ivps_fcfe : float;
  ivps_fcff : float;
  margin_of_safety_fcfe : float;
  margin_of_safety_fcff : float;
  cost_of_equity : float;
  wacc : float;
  growth_rate_fcfe : float;
  growth_rate_fcff : float;
}
[@@deriving show]

type scenario_comparison = {
  ticker : Types.ticker;
  price : float;
  bull : scenario_result;
  base : scenario_result;
  bear : scenario_result;
}
[@@deriving show]

(** Default scenario adjustments *)
let default_adjustments = function
  | Bull -> { growth_delta = 0.05; discount_rate_delta = -0.005 }  (* +5% growth, -50bps discount *)
  | Base -> { growth_delta = 0.0; discount_rate_delta = 0.0 }
  | Bear -> { growth_delta = -0.05; discount_rate_delta = 0.005 }  (* -5% growth, +50bps discount *)

(** Adjust valuation parameters for scenario *)
let adjust_params (params : Types.valuation_params) (adj : scenario_adjustment) : Types.valuation_params =
  (* Note: We adjust terminal growth rate as a proxy for overall growth expectations *)
  let adjusted_tgr = params.terminal_growth_rate +. (adj.growth_delta *. 0.2) in  (* Scale down adjustment for TGR *)
  { params with
    terminal_growth_rate = max 0.0 (min 0.05 adjusted_tgr);  (* Clamp TGR to reasonable range *)
  }

(** Create adjusted config for scenario *)
let adjust_config (config : Types.config) (adj : scenario_adjustment) : Types.config =
  (* Adjust risk-free rates *)
  let adjusted_rfrs = List.map
    (fun (country, rates) ->
       (country, List.map (fun (dur, rate) -> (dur, rate +. adj.discount_rate_delta)) rates))
    config.risk_free_rates in

  (* Adjust equity risk premiums *)
  let adjusted_erps = List.map
    (fun (country, erp) -> (country, erp +. adj.discount_rate_delta))
    config.equity_risk_premiums in

  (* Adjust parameters *)
  let adjusted_params = adjust_params config.params adj in

  { config with
    risk_free_rates = adjusted_rfrs;
    equity_risk_premiums = adjusted_erps;
    params = adjusted_params;
  }

(** Run single scenario valuation - simplified version that just adjusts parameters *)
let run_single_scenario
    ~scenario
    ~market_data
    ~financial_data
    ~base_config =

  let adj = default_adjustments scenario in
  let adjusted_config = adjust_config base_config adj in

  (* Look up adjusted parameters *)
  let country = market_data.Types.country in
  let industry = market_data.Types.industry in

  let rfr_duration = adjusted_config.Types.params.rfr_duration in
  let risk_free_rate =
    match List.assoc_opt country adjusted_config.Types.risk_free_rates with
    | Some rates -> (
        match List.assoc_opt rfr_duration rates with
        | Some rate -> rate
        | None -> snd (List.hd rates))
    | None -> 0.04 in

  let equity_risk_premium =
    match List.assoc_opt country adjusted_config.Types.equity_risk_premiums with
    | Some erp -> erp
    | None -> 0.05 in

  let unlevered_beta =
    match List.assoc_opt industry adjusted_config.Types.industry_betas with
    | Some beta -> beta
    | None -> 1.0 in

  let tax_rate =
    match List.assoc_opt country adjusted_config.Types.tax_rates with
    | Some rate -> rate
    | None -> 0.21 in

  let terminal_growth_rate = adjusted_config.Types.params.terminal_growth_rate in

  (* Calculate cost of capital with adjusted rates *)
  let cost_of_capital = Capital_structure.calculate_cost_of_capital
    ~market_data
    ~financial_data
    ~unlevered_beta
    ~risk_free_rate
    ~equity_risk_premium
    ~tax_rate in

  (* Create projection with adjusted parameters *)
  let projection = Projection.create_projection
    ~financial_data
    ~market_data
    ~tax_rate
    ~params:adjusted_config.Types.params in

  (* Calculate present values *)
  let pve_opt = Valuation.calculate_pve
    ~projection
    ~cost_of_equity:cost_of_capital.ce
    ~terminal_growth_rate in

  let pvf_opt = Valuation.calculate_pvf
    ~projection
    ~wacc:cost_of_capital.wacc
    ~terminal_growth_rate in

  match pve_opt, pvf_opt with
  | Some pve, Some pvf ->
      let ivps_fcfe = pve /. market_data.Types.shares_outstanding in
      let pvf_minus_debt = pvf -. market_data.Types.mvb in
      let ivps_fcff = pvf_minus_debt /. market_data.Types.shares_outstanding in
      let mos_fcfe = (ivps_fcfe -. market_data.Types.price) /. market_data.Types.price in
      let mos_fcff = (ivps_fcff -. market_data.Types.price) /. market_data.Types.price in

      Some {
        scenario;
        ivps_fcfe;
        ivps_fcff;
        margin_of_safety_fcfe = mos_fcfe;
        margin_of_safety_fcff = mos_fcff;
        cost_of_equity = cost_of_capital.ce;
        wacc = cost_of_capital.wacc;
        growth_rate_fcfe = projection.growth_rate_fcfe;
        growth_rate_fcff = projection.growth_rate_fcff;
      }
  | _ -> None

(** Run scenario analysis for a ticker *)
let run_scenario_analysis ~market_data ~financial_data ~config =
  (* Run all three scenarios *)
  let bull_opt = run_single_scenario ~scenario:Bull ~market_data ~financial_data ~base_config:config in
  let base_opt = run_single_scenario ~scenario:Base ~market_data ~financial_data ~base_config:config in
  let bear_opt = run_single_scenario ~scenario:Bear ~market_data ~financial_data ~base_config:config in

  match bull_opt, base_opt, bear_opt with
  | Some bull, Some base, Some bear ->
      Some {
        ticker = market_data.Types.ticker;
        price = market_data.Types.price;
        bull;
        base;
        bear;
      }
  | _ -> None

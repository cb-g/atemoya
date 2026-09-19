open Boundary_t

type assumptions = {
  risk_free_rate : parameter;
  equity_risk_premium : parameter;
  country_risk_premium : parameter option;
  beta : parameter;
  beta_source : beta_source;
  debt_spread : parameter;
  growth_clamp_lower : parameter;
  growth_clamp_upper : parameter;
  mean_reversion_lambda : parameter;
  terminal_growth_rate : parameter;
  projection_years : int_parameter;
  statutory_tax_rate : parameter;
  midcycle_window_years : int_parameter;
}

let max_effective_tax_rate = 0.5

let fcff ~ebit ~tax_rate ~depreciation_amortization ~capex ~delta_nwc =
  (ebit *. (1. -. tax_rate)) +. depreciation_amortization -. capex -. delta_nwc

let wacc ~cost_of_equity ~cost_of_debt ~tax_rate ~market_cap ~total_debt =
  let capital = market_cap +. total_debt in
  (market_cap /. capital *. cost_of_equity)
  +. (total_debt /. capital *. cost_of_debt *. (1. -. tax_rate))

let enterprise_value ~fcff ~wacc ~growth_path ~terminal_growth_rate =
  let discount i = (1. +. wacc) ** float_of_int i in
  let rec explicit i cash_flow acc = function
    | [] -> (acc, cash_flow, i - 1)
    | g :: rest ->
        let cash_flow = cash_flow *. (1. +. g) in
        explicit (i + 1) cash_flow (acc +. (cash_flow /. discount i)) rest
  in
  let pv_explicit, last_cash_flow, years = explicit 1 fcff 0. growth_path in
  let terminal =
    last_cash_flow
    *. (1. +. terminal_growth_rate)
    /. (wacc -. terminal_growth_rate)
  in
  pv_explicit +. (terminal /. discount years)

let tax_rate ~statutory ~pretax_income ~tax_provision =
  match (pretax_income, tax_provision) with
  | Some pretax, Some tax when pretax > 0. ->
      let effective = tax /. pretax in
      if effective >= 0. && effective <= max_effective_tax_rate then
        (effective, `Effective)
      else (statutory, `Statutory)
  | _ -> (statutory, `Statutory)

let cost_of_equity a =
  let domestic = a.risk_free_rate.value +. (a.beta.value *. a.equity_risk_premium.value) in
  match a.country_risk_premium with None -> domestic | Some crp -> domestic +. crp.value

let latest_period fin =
  match Period.latest fin with
  | None -> Error "no fiscal periods in statements"
  | Some p -> Ok p

let absent name opt = if Option.is_none opt then Some name else None

(* Fields carried by every period that has them, most recent first. *)
let series fin field =
  List.filter_map
    (fun (q : fiscal_period) -> Option.map (fun v -> (q.period_end, v)) (field q))
    fin.periods
  |> List.sort (fun (a, _) (b, _) -> compare b a)

let missing_report (fin : financials) (p : fiscal_period) ~nwc_periods =
  let market =
    List.filter_map Fun.id
      [
        absent "currency" fin.currency;
        absent "price" fin.price;
        absent "market_cap" fin.market_cap;
      ]
  in
  let statement =
    List.filter_map Fun.id
      [
        absent "ebit" p.ebit;
        absent "depreciation_amortization" p.depreciation_amortization;
        absent "capex" p.capex;
        absent "cash" p.cash;
        absent "total_debt" p.total_debt;
        absent "book_equity" p.book_equity;
        (if nwc_periods < 2 then
           Some
             (Printf.sprintf "delta_nwc (need 2 fiscal periods carrying it, have %d)"
                nwc_periods)
         else None);
      ]
  in
  let part label = function
    | [] -> None
    | names -> Some (label ^ ": " ^ String.concat ", " names)
  in
  String.concat "; "
    (List.filter_map Fun.id
       [
         part "missing market data" market;
         part
           (Printf.sprintf "missing statement fields for fiscal period ending %s"
              p.period_end)
           statement;
       ])

let mean xs = List.fold_left ( +. ) 0. xs /. float_of_int (List.length xs)

let value a ~country (fin : financials) =
  let ( let* ) = Result.bind in
  let* p = latest_period fin in
  let nwc = series fin (fun q -> q.delta_nwc) in
  (* The composition of each averaged delta_nwc, aligned with [nwc]. *)
  let nwc_compositions =
    List.map
      (fun (period_end, _) ->
        Option.bind
          (List.find_opt (fun (q : fiscal_period) -> q.period_end = period_end) fin.periods)
          (fun (q : fiscal_period) -> q.delta_nwc_composition))
      nwc
  in
  let revenues = series fin (fun q -> q.total_revenue) in
  match
    ( fin.currency,
      fin.price,
      fin.market_cap,
      p.ebit,
      p.depreciation_amortization,
      p.capex,
      p.cash,
      p.total_debt,
      p.book_equity )
  with
  | ( Some _currency,
      Some price,
      Some market_cap,
      Some ebit,
      Some depreciation_amortization,
      Some capex,
      Some cash,
      Some total_debt,
      Some book_equity )
    when List.length nwc >= 2 ->
      let projection_years = a.projection_years.value in
      if price <= 0. || market_cap <= 0. then
        Error
          (Printf.sprintf "price %g and market cap %g must be positive" price
             market_cap)
      else if projection_years < 0 then
        Error
          (Printf.sprintf "projection horizon %d years is negative"
             projection_years)
      else
        let delta_nwc = mean (List.map snd nwc) in
        let tax_rate, tax_rate_source =
          tax_rate ~statutory:a.statutory_tax_rate.value
            ~pretax_income:p.pretax_income ~tax_provision:p.tax_provision
        in
        let cost_of_equity = cost_of_equity a in
        let cost_of_debt = a.risk_free_rate.value +. a.debt_spread.value in
        let wacc =
          wacc ~cost_of_equity ~cost_of_debt ~tax_rate ~market_cap ~total_debt
        in
        if wacc <= a.terminal_growth_rate.value then
          Error
            (Printf.sprintf "wacc %.4f does not exceed terminal growth %.4f"
               wacc a.terminal_growth_rate.value)
        else
          let estimate =
            Growth.estimate ~ebit ~tax_rate ~book_equity ~total_debt ~capex
              ~delta_nwc ~depreciation_amortization ~revenues
          in
          let* selected, growth_source = Growth.select estimate in
          let g0, growth_clamped =
            Growth.clamp ~lower:a.growth_clamp_lower.value
              ~upper:a.growth_clamp_upper.value selected
          in
          let growth_path =
            Growth.path ~g0 ~terminal_growth_rate:a.terminal_growth_rate.value
              ~lambda:a.mean_reversion_lambda.value ~projection_years
          in
          let fcff =
            fcff ~ebit ~tax_rate ~depreciation_amortization ~capex ~delta_nwc
          in
          let enterprise_value =
            enterprise_value ~fcff ~wacc ~growth_path
              ~terminal_growth_rate:a.terminal_growth_rate.value
          in
          let shares = market_cap /. price in
          let net_debt = total_debt -. cash in
          let equity_value = enterprise_value -. net_debt in
          let fair_value = equity_value /. shares in
          if not (Float.is_finite fair_value) then
            Error
              (Printf.sprintf
                 "fair value is not finite (enterprise value %g, shares %g)"
                 enterprise_value shares)
          else
            Ok
              ( {
                  fiscal_period_end = p.period_end;
                  country;
                  industry = fin.industry;
                  price;
                  market_cap;
                  shares;
                  ebit = Some ebit;
                  ebit_recipe = p.ebit_recipe;
                  ebit_composition = p.ebit_composition;
                  tax_rate;
                  tax_rate_source;
                  statutory_tax_rate = a.statutory_tax_rate;
                  nopat = estimate.nopat;
                  depreciation_amortization = Some depreciation_amortization;
                  depreciation_amortization_row = p.depreciation_amortization_row;
                  capex = Some capex;
                  delta_nwc = Some delta_nwc;
                  delta_nwc_periods = List.map fst nwc;
                  delta_nwc_compositions = nwc_compositions;
                  fcff;
                  cash;
                  cash_composition = p.cash_composition;
                  total_debt;
                  total_debt_source = p.total_debt_source;
                  total_debt_composition = p.total_debt_composition;
                  net_debt;
                  book_equity;
                  invested_capital = estimate.invested_capital;
                  roic = estimate.roic;
                  reinvestment = estimate.reinvestment;
                  reinvestment_rate = estimate.reinvestment_rate;
                  g_fundamental = estimate.g_fundamental;
                  g_historical = estimate.g_historical;
                  revenue_periods = estimate.revenue_periods;
                  growth_source;
                  g0;
                  growth_clamped;
                  growth_clamp_lower = a.growth_clamp_lower;
                  growth_clamp_upper = a.growth_clamp_upper;
                  mean_reversion_lambda = a.mean_reversion_lambda;
                  growth_path;
                  risk_free_rate = a.risk_free_rate;
                  equity_risk_premium = a.equity_risk_premium;
                  country_risk_premium = a.country_risk_premium;
                  beta = a.beta;
                  beta_source = a.beta_source;
                  cost_of_equity;
                  conversion = None;
                  debt_spread = a.debt_spread;
                  cost_of_debt;
                  wacc;
                  terminal_growth_rate = a.terminal_growth_rate;
                  projection_years = a.projection_years;
                  enterprise_value;
                  equity_value;
                },
                fair_value )
  | _ -> Error (missing_report fin p ~nwc_periods:(List.length nwc))

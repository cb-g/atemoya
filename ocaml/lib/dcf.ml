open Boundary_t

type assumptions = {
  risk_free_rate : parameter;
  equity_risk_premium : parameter;
  beta : parameter;
  beta_source : beta_source;
  debt_spread : parameter;
  growth_rate : parameter;
  terminal_growth_rate : parameter;
  projection_years : int_parameter;
  statutory_tax_rate : parameter;
}

let max_effective_tax_rate = 0.5

let fcff ~ebit ~tax_rate ~depreciation_amortization ~capex ~delta_nwc =
  (ebit *. (1. -. tax_rate)) +. depreciation_amortization -. capex -. delta_nwc

let wacc ~cost_of_equity ~cost_of_debt ~tax_rate ~market_cap ~total_debt =
  let capital = market_cap +. total_debt in
  (market_cap /. capital *. cost_of_equity)
  +. (total_debt /. capital *. cost_of_debt *. (1. -. tax_rate))

let enterprise_value ~fcff ~wacc ~growth_rate ~terminal_growth_rate
    ~projection_years =
  let discount i = (1. +. wacc) ** float_of_int i in
  let cash_flow i = fcff *. ((1. +. growth_rate) ** float_of_int i) in
  let rec explicit i acc =
    if i > projection_years then acc
    else explicit (i + 1) (acc +. (cash_flow i /. discount i))
  in
  let terminal =
    cash_flow projection_years
    *. (1. +. terminal_growth_rate)
    /. (wacc -. terminal_growth_rate)
  in
  explicit 1 0. +. (terminal /. discount projection_years)

let tax_rate ~statutory ~pretax_income ~tax_provision =
  match (pretax_income, tax_provision) with
  | Some pretax, Some tax when pretax > 0. ->
      let effective = tax /. pretax in
      if effective >= 0. && effective <= max_effective_tax_rate then
        (effective, `Effective)
      else (statutory, `Statutory)
  | _ -> (statutory, `Statutory)

let latest_period (fin : financials) =
  (* ISO dates order lexicographically. *)
  match
    List.sort (fun a b -> compare b.period_end a.period_end) fin.periods
  with
  | [] -> Error "no fiscal periods in statements"
  | p :: _ -> Ok p

let absent name opt = if Option.is_none opt then Some name else None

let missing_report (fin : financials) (p : fiscal_period) =
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
        absent "delta_nwc" p.delta_nwc;
        absent "cash" p.cash;
        absent "total_debt" p.total_debt;
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

let value a ~country (fin : financials) =
  let ( let* ) = Result.bind in
  let* p = latest_period fin in
  match
    ( fin.currency,
      fin.price,
      fin.market_cap,
      p.ebit,
      p.depreciation_amortization,
      p.capex,
      p.delta_nwc,
      p.cash,
      p.total_debt )
  with
  | ( Some _currency,
      Some price,
      Some market_cap,
      Some ebit,
      Some depreciation_amortization,
      Some capex,
      Some delta_nwc,
      Some cash,
      Some total_debt ) ->
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
        let tax_rate, tax_rate_source =
          tax_rate ~statutory:a.statutory_tax_rate.value
            ~pretax_income:p.pretax_income ~tax_provision:p.tax_provision
        in
        let cost_of_equity =
          a.risk_free_rate.value +. (a.beta.value *. a.equity_risk_premium.value)
        in
        let cost_of_debt = a.risk_free_rate.value +. a.debt_spread.value in
        let wacc =
          wacc ~cost_of_equity ~cost_of_debt ~tax_rate ~market_cap ~total_debt
        in
        if wacc <= a.terminal_growth_rate.value then
          Error
            (Printf.sprintf "wacc %.4f does not exceed terminal growth %.4f"
               wacc a.terminal_growth_rate.value)
        else
          let fcff =
            fcff ~ebit ~tax_rate ~depreciation_amortization ~capex ~delta_nwc
          in
          let enterprise_value =
            enterprise_value ~fcff ~wacc ~growth_rate:a.growth_rate.value
              ~terminal_growth_rate:a.terminal_growth_rate.value
              ~projection_years
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
                  ebit;
                  tax_rate;
                  tax_rate_source;
                  statutory_tax_rate = a.statutory_tax_rate;
                  depreciation_amortization;
                  capex;
                  delta_nwc;
                  fcff;
                  cash;
                  total_debt;
                  net_debt;
                  risk_free_rate = a.risk_free_rate;
                  equity_risk_premium = a.equity_risk_premium;
                  beta = a.beta;
                  beta_source = a.beta_source;
                  cost_of_equity;
                  debt_spread = a.debt_spread;
                  cost_of_debt;
                  wacc;
                  growth_rate = a.growth_rate;
                  terminal_growth_rate = a.terminal_growth_rate;
                  projection_years = a.projection_years;
                  enterprise_value;
                  equity_value;
                },
                fair_value )
  | _ -> Error (missing_report fin p)

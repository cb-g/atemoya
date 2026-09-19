open Boundary_t

let minimum_observations = 8

let invested_capital (p : fiscal_period) =
  match (p.book_equity, p.total_debt, p.cash) with
  | Some e, Some d, Some c -> Some (e +. d -. c)
  | _ -> None

let mean xs = List.fold_left ( +. ) 0. xs /. float_of_int (List.length xs)

let median xs =
  let sorted = List.sort compare xs in
  let n = List.length sorted in
  if n mod 2 = 1 then List.nth sorted (n / 2)
  else (List.nth sorted ((n / 2) - 1) +. List.nth sorted (n / 2)) /. 2.

let rec take n = function [] -> [] | x :: rest -> if n <= 0 then [] else x :: take (n - 1) rest

let value (a : Dcf.assumptions) ~country (fin : financials) =
  let ( let* ) = Result.bind in
  let* latest = match Period.latest fin with None -> Error "no fiscal periods in statements" | Some p -> Ok p in
  let sorted = List.sort (fun (p : fiscal_period) (q : fiscal_period) -> compare q.period_end p.period_end) fin.periods in
  let window = take a.midcycle_window_years.value sorted in
  let tax_rate = a.statutory_tax_rate.value in
  (* NOPAT bottom-up from filed lines (25): net income + interest expense x (1 - t). No
     operating-income line is needed, and the through-cycle mean dampens one-offs. *)
  let nopat_of (p : fiscal_period) =
    match (p.net_income, p.interest_expense) with
    | Some ni, Some ie -> Some (ni, ie, ni +. (ie *. (1. -. tax_rate)))
    | _ -> None
  in
  (* Consecutive pairs in the window: the period's nopat over the previous period's capital. *)
  let rec pairs = function
    | (t : fiscal_period) :: ((prior : fiscal_period) :: _ as rest) -> (
        match (nopat_of t, invested_capital prior) with
        | Some (net_income, interest_expense, nopat), Some ic when ic > 0. ->
            { period_end = t.period_end; prior_period_end = prior.period_end; net_income; interest_expense; nopat;
              invested_capital_prior = ic; roic = nopat /. ic }
            :: pairs rest
        | _ -> pairs rest)
    | _ -> []
  in
  let observations = pairs window in
  let n_obs = List.length observations in
  if n_obs < minimum_observations then
    Error
      (Printf.sprintf
         "mid-cycle normalisation needs at least %d annual return observations, have %d; the provider carries %d periods"
         minimum_observations n_obs (List.length fin.periods))
  else
    match
      ( fin.currency, fin.price, fin.market_cap, nopat_of latest, latest.depreciation_amortization, latest.capex,
        latest.delta_nwc, latest.cash, latest.total_debt, latest.book_equity )
    with
    | ( Some _, Some price, Some market_cap, Some (_, _, nopat_spot), Some depreciation_amortization, Some capex, Some delta_nwc,
        Some cash, Some total_debt, Some book_equity ) ->
        let projection_years = a.projection_years.value in
        if price <= 0. || market_cap <= 0. then
          Error (Printf.sprintf "price %g and market cap %g must be positive" price market_cap)
        else if projection_years < 0 then
          Error (Printf.sprintf "projection horizon %d years is negative" projection_years)
        else
          let roics = List.map (fun (o : roic_observation) -> o.roic) observations in
          let roic_mid = mean roics and roic_median = median roics in
          let invested_capital_latest = book_equity +. total_debt -. cash in
          let nopat_mid = roic_mid *. invested_capital_latest in
          (* The reinvestment rate: sums over the window periods carrying all four flows. *)
          let reinvestment_periods, reinvestment_sum, nopat_sum =
            List.fold_right
              (fun (p : fiscal_period) (ends, r, n) ->
                match (nopat_of p, p.capex, p.depreciation_amortization, p.delta_nwc) with
                | Some (_, _, nopat), Some c, Some d, Some w -> (p.period_end :: ends, r +. (c -. d +. w), n +. nopat)
                | _ -> (ends, r, n))
              window ([], 0., 0.)
          in
          if roic_mid <= 0. then
            Error
              (Printf.sprintf
                 "through the cycle the business did not earn a positive return on its capital (mean roic %.4f over %d observations)"
                 roic_mid n_obs)
          else if nopat_sum <= 0. then
            Error
              (Printf.sprintf
                 "through the cycle the business did not earn a positive return on its capital (the sum of nopat over %d periods, %.4g, is not positive)"
                 (List.length reinvestment_periods) nopat_sum)
          else
            let reinvestment_rate_mid = reinvestment_sum /. nopat_sum in
            if reinvestment_rate_mid >= 1. then
              Error
                (Printf.sprintf "through the cycle the business reinvested more than it earned (reinvestment rate %.4f)"
                   reinvestment_rate_mid)
            else
              let fcff_mid = nopat_mid *. (1. -. reinvestment_rate_mid) in
              let g_fundamental = roic_mid *. reinvestment_rate_mid in
              let cost_of_equity = Dcf.cost_of_equity a in
              let cost_of_debt = a.risk_free_rate.value +. a.debt_spread.value in
              let wacc = Dcf.wacc ~cost_of_equity ~cost_of_debt ~tax_rate ~market_cap ~total_debt in
              if wacc <= a.terminal_growth_rate.value then
                Error (Printf.sprintf "wacc %.4f does not exceed terminal growth %.4f" wacc a.terminal_growth_rate.value)
              else
                let g0, growth_clamped =
                  Growth.clamp ~lower:a.growth_clamp_lower.value ~upper:a.growth_clamp_upper.value g_fundamental
                in
                let growth_path =
                  Growth.path ~g0 ~terminal_growth_rate:a.terminal_growth_rate.value ~lambda:a.mean_reversion_lambda.value
                    ~projection_years
                in
                let enterprise_value =
                  Dcf.enterprise_value ~fcff:fcff_mid ~wacc ~growth_path ~terminal_growth_rate:a.terminal_growth_rate.value
                in
                let shares = market_cap /. price in
                let net_debt = total_debt -. cash in
                let equity_value = enterprise_value -. net_debt in
                let fair_value = equity_value /. shares in
                let ebit = nopat_spot /. (1. -. tax_rate) in
                let spot_fcff = nopat_spot +. depreciation_amortization -. capex -. delta_nwc in
                if not (Float.is_finite fair_value) then
                  Error (Printf.sprintf "fair value is not finite (enterprise value %g, shares %g)" enterprise_value shares)
                else
                  let dcf : inputs =
                    {
                      fiscal_period_end = latest.period_end;
                      country;
                      industry = fin.industry;
                      price;
                      market_cap;
                      shares;
                      ebit;
                      ebit_recipe = Some "nopat_bottom_up";
                      ebit_composition = None;
                      tax_rate;
                      tax_rate_source = `Statutory;
                      statutory_tax_rate = a.statutory_tax_rate;
                      nopat = nopat_mid;
                      depreciation_amortization;
                      depreciation_amortization_row = latest.depreciation_amortization_row;
                      capex;
                      delta_nwc;
                      delta_nwc_periods = [ latest.period_end ];
                      delta_nwc_compositions = [ latest.delta_nwc_composition ];
                      fcff = fcff_mid;
                      cash;
                      cash_composition = latest.cash_composition;
                      total_debt;
                      total_debt_source = latest.total_debt_source;
                      total_debt_composition = latest.total_debt_composition;
                      net_debt;
                      book_equity;
                      invested_capital = invested_capital_latest;
                      roic = Some roic_mid;
                      reinvestment = reinvestment_sum;
                      reinvestment_rate = Some reinvestment_rate_mid;
                      g_fundamental = Some g_fundamental;
                      g_historical = None;
                      revenue_periods = [];
                      growth_source = `Fundamental;
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
                    }
                  in
                  Ok
                    ( {
                        dcf;
                        nopat_recipe = "nopat_bottom_up";
                        midcycle_window_years = a.midcycle_window_years;
                        window = List.map (fun (p : fiscal_period) -> p.period_end) window;
                        observations;
                        roic_mid;
                        roic_median;
                        invested_capital_latest;
                        nopat_mid;
                        reinvestment_periods;
                        reinvestment_sum;
                        nopat_sum;
                        reinvestment_rate_mid;
                        fcff_mid;
                        spot_fcff;
                        spot_to_midcycle = spot_fcff /. fcff_mid;
                      },
                      fair_value )
    | _ ->
        let absent name opt = if Option.is_none opt then Some name else None in
        let market = List.filter_map Fun.id [ absent "currency" fin.currency; absent "price" fin.price; absent "market_cap" fin.market_cap ] in
        let statement =
          List.filter_map Fun.id
            [ absent "net_income" latest.net_income; absent "interest_expense" latest.interest_expense;
              absent "depreciation_amortization" latest.depreciation_amortization; absent "capex" latest.capex;
              absent "delta_nwc" latest.delta_nwc; absent "cash" latest.cash; absent "total_debt" latest.total_debt;
              absent "book_equity" latest.book_equity ]
        in
        let part label = function [] -> None | names -> Some (label ^ ": " ^ String.concat ", " names) in
        Error
          (String.concat "; "
             (List.filter_map Fun.id
                [ part "missing market data" market;
                  part (Printf.sprintf "missing statement fields for fiscal period ending %s" latest.period_end) statement ]))

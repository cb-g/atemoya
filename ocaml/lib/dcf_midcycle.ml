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

let minimum_reinvestment_periods = 8

let value (a : Dcf.assumptions) ~country ~required (fin : financials) =
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
  let recipe_of (p : fiscal_period) = Option.value p.interest_recipe ~default:"" in
  let exclude period_end sum missing = { period_end; sum; missing } in
  (* Consecutive pairs in the window: the period's nopat over the previous period's capital;
     a pair that lacks either is excluded from the roic series and named (27). *)
  let rec pairs = function
    | (t : fiscal_period) :: ((prior : fiscal_period) :: _ as rest) -> (
        let obs, excl = pairs rest in
        match (nopat_of t, invested_capital prior) with
        | Some (net_income, interest_expense, nopat), Some ic when ic > 0. ->
            ( { period_end = t.period_end; prior_period_end = prior.period_end; net_income; interest_expense;
                interest_recipe = recipe_of t; nopat; invested_capital_prior = ic; roic = nopat /. ic }
              :: obs,
              excl )
        | None, _ ->
            (obs, List.map (fun f -> exclude t.period_end "roic" f) (Period.missing t [ "net_income"; "interest_expense" ]) @ excl)
        | Some _, None ->
            (obs, List.map (fun f -> exclude t.period_end "roic" ("prior period's " ^ f)) (Period.missing prior [ "book_equity"; "total_debt"; "cash" ]) @ excl)
        | Some _, Some _ -> (obs, exclude t.period_end "roic" "positive prior invested capital" :: excl))
    | _ -> ([], [])
  in
  let observations, roic_exclusions = pairs window in
  let n_obs = List.length observations in
  (* The reinvestment sums over the window periods carrying all five flows; a period lacking
     one is excluded from the sums and named (27). *)
  let reinvestment_periods, reinvestment_sum, nopat_sum, reinvestment_exclusions =
    List.fold_right
      (fun (p : fiscal_period) (ends, r, n, excl) ->
        match (nopat_of p, p.capex, p.depreciation_amortization, p.delta_nwc) with
        | Some (_, _, nopat), Some c, Some d, Some w -> (p.period_end :: ends, r +. (c -. d +. w), n +. nopat, excl)
        | _ ->
            ( ends, r, n,
              List.map (fun f -> exclude p.period_end "reinvestment" f)
                (Period.missing p [ "net_income"; "interest_expense"; "capex"; "depreciation_amortization"; "delta_nwc" ])
              @ excl ))
      window ([], 0., 0., [])
  in
  let exclusions = roic_exclusions @ reinvestment_exclusions in
  if n_obs < minimum_observations then
    Error
      (Printf.sprintf
         "mid-cycle normalisation needs at least %d annual return observations, have %d; the provider carries %d periods"
         minimum_observations n_obs (List.length fin.periods))
  else if List.length reinvestment_periods < minimum_reinvestment_periods then
    Error
      (Printf.sprintf
         "mid-cycle reinvestment needs at least %d periods with capex, d&a, delta_nwc and nopat, have %d; the provider carries %d periods"
         minimum_reinvestment_periods (List.length reinvestment_periods) (List.length fin.periods))
  else
    (* The latest period must carry what the definitions require of it for this model (27):
       the balance sheet, since the model applies a through-cycle return to today's capital. *)
    let statement_missing = Period.missing latest required in
    let market_missing =
      List.filter_map Fun.id
        [ (if Option.is_none fin.currency then Some "currency" else None);
          (if Option.is_none fin.price then Some "price" else None);
          (if Option.is_none fin.market_cap then Some "market_cap" else None) ]
    in
    match (fin.currency, fin.price, fin.market_cap, latest.cash, latest.total_debt, latest.book_equity) with
    | Some _, Some price, Some market_cap, Some cash, Some total_debt, Some book_equity when statement_missing = [] ->
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
                (* The spot readout (27): the latest period's own fcff when it carries the flows. *)
                let nopat_spot = Option.map (fun (_, _, n) -> n) (nopat_of latest) in
                let spot_missing =
                  Period.missing latest [ "net_income"; "interest_expense"; "depreciation_amortization"; "capex"; "delta_nwc" ]
                in
                let spot_fcff =
                  match (nopat_spot, latest.depreciation_amortization, latest.capex, latest.delta_nwc) with
                  | Some n, Some d, Some c, Some w -> Some (n +. d -. c -. w)
                  | _ -> None
                in
                let spot_reason =
                  if spot_missing = [] then None
                  else Some (Printf.sprintf "the latest period lacks %s: no spot fcff" (String.concat ", " spot_missing))
                in
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
                      ebit = Option.map (fun n -> n /. (1. -. tax_rate)) nopat_spot;
                      ebit_recipe = Some "nopat_bottom_up";
                      ebit_composition = None;
                      tax_rate;
                      tax_rate_source = `Statutory;
                      statutory_tax_rate = a.statutory_tax_rate;
                      nopat = nopat_mid;
                      depreciation_amortization = latest.depreciation_amortization;
                      depreciation_amortization_row = latest.depreciation_amortization_row;
                      capex = latest.capex;
                      delta_nwc = latest.delta_nwc;
                      delta_nwc_periods = (if Option.is_some latest.delta_nwc then [ latest.period_end ] else []);
                      delta_nwc_compositions = (if Option.is_some latest.delta_nwc then [ latest.delta_nwc_composition ] else []);
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
                        exclusions;
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
                        spot_to_midcycle = Option.map (fun s -> s /. fcff_mid) spot_fcff;
                        spot_reason;
                      },
                      fair_value )
    | _ ->
        let part label = function [] -> None | names -> Some (label ^ ": " ^ String.concat ", " names) in
        Error
          (String.concat "; "
             (List.filter_map Fun.id
                [ part "missing market data" market_missing;
                  part (Printf.sprintf "missing statement fields for fiscal period ending %s" latest.period_end) statement_missing ]))

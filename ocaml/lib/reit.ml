open Boundary_t

let caveat =
  "FFO overstates distributable cash by the recurring capex, straight-line rent and \
   lease-intangible amortisation the filer does not tag; AFFO is not derivable from filed tags"

let dividend_path ~d0 ~growth_path =
  let rec go d acc = function
    | [] -> List.rev acc
    | g :: rest ->
        let d = d *. (1. +. g) in
        go d (d :: acc) rest
  in
  go d0 [] growth_path

let present_value ~dividend_path ~cost_of_equity ~terminal_growth_rate =
  let discount t = (1. +. cost_of_equity) ** float_of_int t in
  let pv, _ =
    List.fold_left (fun (acc, t) d -> (acc +. (d /. discount t), t + 1)) (0., 1) dividend_path
  in
  let n = List.length dividend_path in
  let last = match List.rev dividend_path with d :: _ -> d | [] -> 0. in
  let terminal = last *. (1. +. terminal_growth_rate) /. (cost_of_equity -. terminal_growth_rate) in
  (pv, terminal, terminal /. discount n)

let absent name opt = if Option.is_none opt then Some name else None

let value (a : Dcf.assumptions) ~country (fin : financials) =
  let ( let* ) = Result.bind in
  let* p =
    match Period.latest fin with
    | None -> Error "no fiscal periods in statements"
    | Some p -> Ok p
  in
  let market =
    List.filter_map Fun.id
      [ absent "currency" fin.currency; absent "price" fin.price; absent "market_cap" fin.market_cap ]
  in
  let statement =
    List.filter_map Fun.id [ absent "ffo" p.ffo; absent "dividends_paid" p.dividends_paid ]
  in
  let part label = function [] -> None | names -> Some (label ^ ": " ^ String.concat ", " names) in
  let missing =
    String.concat "; "
      (List.filter_map Fun.id
         [ part "missing market data" market;
           part (Printf.sprintf "missing statement fields for fiscal period ending %s" p.period_end) statement ])
  in
  match (fin.currency, fin.price, fin.market_cap, p.ffo, p.dividends_paid) with
  | Some _, Some price, Some market_cap, Some ffo, Some dividends_paid ->
      if price <= 0. || market_cap <= 0. then
        Error (Printf.sprintf "price %g and market cap %g must be positive" price market_cap)
      else if ffo <= 0. then Error (Printf.sprintf "ffo %g is not positive" ffo)
      else if a.projection_years.value < 0 then
        Error (Printf.sprintf "projection horizon %d years is negative" a.projection_years.value)
      else
        (* FFO per weighted-average diluted share, every period that carries both, for the
           growth: the period's own count, per shares_for_flows; the period record carries
           no point count, so no other denominator is possible here. *)
        let series =
          List.filter_map
            (fun (q : fiscal_period) ->
              match (q.ffo, q.weighted_shares, q.weighted_shares_tag) with
              | Some f, Some sh, Some tag when sh > 0. -> Some (q.period_end, f /. sh, tag)
              | _ -> None)
            fin.periods
          |> List.sort (fun (x, _, _) (y, _, _) -> compare y x)
        in
        let weighted_shares_tags = List.map (fun (e, _, tag) -> (e, tag)) series in
        let series = List.map (fun (e, v, _) -> (e, v)) series in
        let* g_historical, ffo_periods =
          match series with
          | (last_end, last) :: _ when List.length series >= 2 -> (
              let first_end, first = List.nth series (List.length series - 1) in
              match Date.days_between ~from:first_end ~until:last_end with
              | Ok days when days > 0 && first > 0. && last > 0. ->
                  Ok (((last /. first) ** (365.25 /. float_of_int days)) -. 1., List.map fst series)
              | _ ->
                  Error
                    (Printf.sprintf "ffo growth needs two periods with positive ffo per share (%s to %s: %g to %g)"
                       first_end last_end first last))
          | _ ->
              Error
                (Printf.sprintf "ffo growth needs two periods with ffo and weighted-average shares, have %d"
                   (List.length series))
        in
        let cost_of_equity =
          let domestic = a.risk_free_rate.value +. (a.beta.value *. a.equity_risk_premium.value) in
          match a.country_risk_premium with None -> domestic | Some crp -> domestic +. crp.value
        in
        let terminal_growth_rate = a.terminal_growth_rate.value in
        if cost_of_equity <= terminal_growth_rate then
          Error
            (Printf.sprintf "cost of equity %.4f does not exceed terminal growth %.4f" cost_of_equity
               terminal_growth_rate)
        else
          let g0, growth_clamped =
            Growth.clamp ~lower:a.growth_clamp_lower.value ~upper:a.growth_clamp_upper.value g_historical
          in
          let projection_years = a.projection_years.value in
          let growth_path =
            Growth.path ~g0 ~terminal_growth_rate ~lambda:a.mean_reversion_lambda.value ~projection_years
          in
          let shares = market_cap /. price in
          let covered_dividend = Float.min dividends_paid ffo in
          let dividend_per_share = covered_dividend /. shares in
          let dividend_path = dividend_path ~d0:dividend_per_share ~growth_path in
          let pv_dividends, terminal_value, pv_terminal_value =
            present_value ~dividend_path ~cost_of_equity ~terminal_growth_rate
          in
          let equity_value = pv_dividends +. pv_terminal_value in
          if not (Float.is_finite equity_value) then
            Error (Printf.sprintf "fair value is not finite (equity value %g, shares %g)" equity_value shares)
          else
            Ok
              ( {
                  fiscal_period_end = p.period_end;
                  country;
                  industry = fin.industry;
                  price;
                  market_cap;
                  shares;
                  ffo;
                  ffo_composition = p.ffo_composition;
                  ffo_per_share = ffo /. shares;
                  price_to_ffo = price /. (ffo /. shares);
                  dividends_paid;
                  dividends_paid_row = p.dividends_paid_row;
                  coverage = dividends_paid /. ffo;
                  covered_dividend;
                  dividend_per_share;
                  ffo_per_weighted_share = series;
                  weighted_shares_tags;
                  ffo_periods;
                  g_historical;
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
                  terminal_growth_rate = a.terminal_growth_rate;
                  projection_years = a.projection_years;
                  dividend_path;
                  pv_dividends;
                  terminal_value;
                  pv_terminal_value;
                  equity_value;
                  caveat;
                },
                equity_value )
  | _ -> Error missing

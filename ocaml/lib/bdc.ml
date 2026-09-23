open Boundary_t

let absent name opt = if Option.is_none opt then Some name else None

let caveat =
  "the net asset value is the filer's own quarterly mark on a portfolio of private loans and equity \
   stakes with no quoted price; the tool records that mark and does not verify it, so every readout \
   here is a statement about the filing, not about the portfolio"

let covered_note ~coverage =
  if coverage >= 1. then
    Printf.sprintf
      "net investment income covers the distribution %.3f times; the excess is retained and lifts the net asset value"
      coverage
  else
    Printf.sprintf
      "net investment income covers only %.3f of the distribution; the shortfall is paid out of capital and erodes \
       the net asset value, which the trend below shows"
      coverage

(* The net asset value per share the filer states, over the periods that carry one: the
   trend of the mark itself, measured in calendar years as every other growth here is. *)
let nav_series (fin : financials) =
  List.filter_map
    (fun (q : fiscal_period) ->
      match q.net_asset_value_per_share with Some v when v > 0. -> Some (q.period_end, v) | _ -> None)
    fin.periods
  |> List.sort (fun (x, _) (y, _) -> compare y x)

let value (_ : Dcf.assumptions) ~country (fin : financials) =
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
    List.filter_map Fun.id
      [ absent "net_asset_value_per_share" p.net_asset_value_per_share;
        absent "net_investment_income" p.net_investment_income;
        absent "distributions_per_share" p.distributions_per_share;
        absent "weighted_shares" p.weighted_shares ]
  in
  let part label = function [] -> None | names -> Some (label ^ ": " ^ String.concat ", " names) in
  let missing =
    String.concat "; "
      (List.filter_map Fun.id
         [ part "missing market data" market;
           part (Printf.sprintf "missing statement fields for fiscal period ending %s" p.period_end) statement ])
  in
  match
    (fin.currency, fin.price, fin.market_cap, p.net_asset_value_per_share, p.net_investment_income,
     p.distributions_per_share, p.weighted_shares)
  with
  | Some _, Some price, Some market_cap, Some nav, Some nii, Some dps, Some weighted_shares ->
      if price <= 0. || market_cap <= 0. then
        Error (Printf.sprintf "price %g and market cap %g must be positive" price market_cap)
      else if nav <= 0. then Error (Printf.sprintf "net asset value per share %g is not positive" nav)
      else if weighted_shares <= 0. then
        Error (Printf.sprintf "weighted-average shares %g is not positive" weighted_shares)
      else if dps <= 0. then
        Error
          (Printf.sprintf
             "distributions per share %g is not positive; there is no coverage to read, and the distribution is the \
              point of the lens"
             dps)
      else
        let series = nav_series fin in
        let* nav_cagr, nav_periods =
          match series with
          | (last_end, last) :: _ when List.length series >= 2 -> (
              let first_end, first = List.nth series (List.length series - 1) in
              match Date.days_between ~from:first_end ~until:last_end with
              | Ok days when days > 0 ->
                  Ok (((last /. first) ** (365.25 /. float_of_int days)) -. 1., List.map fst series)
              | _ ->
                  Error
                    (Printf.sprintf
                       "net asset value growth needs two periods a year or more apart (%s to %s)" first_end last_end))
          | _ ->
              Error
                (Printf.sprintf "net asset value growth needs two periods carrying a filed net asset value per share, have %d"
                   (List.length series))
        in
        let nii_per_share = nii /. weighted_shares in
        let coverage = nii_per_share /. dps in
        let fair_value = nav in
        Ok
          ( {
              fiscal_period_end = p.period_end;
              country;
              industry = fin.industry;
              price;
              market_cap;
              shares = market_cap /. price;
              net_asset_value_per_share = nav;
              net_asset_value_row = Option.value p.net_asset_value_per_share_row ~default:"";
              net_asset_value_composition = p.net_asset_value_composition;
              net_investment_income = nii;
              net_investment_income_row = Option.value p.net_investment_income_row ~default:"";
              net_investment_income_composition = p.net_investment_income_composition;
              weighted_shares;
              weighted_shares_tag = Option.value p.weighted_shares_tag ~default:"";
              net_investment_income_per_share = nii_per_share;
              distributions_per_share = dps;
              distributions_per_share_row = Option.value p.distributions_per_share_row ~default:"";
              price_to_nav = price /. nav;
              nii_yield_on_nav = nii_per_share /. nav;
              distribution_yield = dps /. price;
              nii_coverage = coverage;
              coverage_note = covered_note ~coverage;
              nav_per_share_series = series;
              nav_periods;
              nav_cagr;
              conversion = None;
              caveat;
            },
            fair_value )
  | _ -> Error missing

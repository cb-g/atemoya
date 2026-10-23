open Reference_t

type size = Large | Small

type rule = { spreads : default_spreads; age_days : int; size : size; size_note : string }

let row rows coverage =
  List.fold_left (fun found (r : default_spread_row) -> if coverage >= r.above then Some r else found) None rows

let with_size rule ~market_cap_usd =
  let threshold = rule.spreads.small_firm_market_cap_usd in
  match market_cap_usd with
  | Ok usd when usd < threshold ->
      { rule with size = Small;
        size_note = Printf.sprintf "market cap %.4g dollars, below %.4g: the smaller and riskier firms' table" usd threshold }
  | Ok usd -> { rule with size = Large; size_note = Printf.sprintf "market cap %.4g dollars: the large firms' table" usd }
  | Error why ->
      { rule with size = Large; size_note = Printf.sprintf "market cap not in dollars (%s): the large firms' table" why }

let resolve rule ~(fallback : Boundary_t.parameter) ~ebit ~interest_expense ~total_debt ~period_end : Boundary_t.parameter =
  let table = match rule.size with Large -> rule.spreads.large | Small -> rule.spreads.small in
  match interest_expense with
  | Some interest when interest > 0. -> (
      let coverage = ebit /. interest in
      match row table coverage with
      | Some r ->
          { fallback with
            value = r.spread; key = r.rating;
            source =
              Printf.sprintf
                "synthetic rating %s from interest coverage %.2f, operating income %.4g over interest expense %.4g for the fiscal period ending %s; %s; %s"
                r.rating coverage ebit interest period_end rule.size_note rule.spreads.source;
            as_of = rule.spreads.as_of; age_days = rule.age_days }
      | None -> fallback)
  | _ when total_debt <= 0. ->
      { fallback with
        source =
          Printf.sprintf "no debt and no interest expense for the fiscal period ending %s, so the spread carries no weight; %s" period_end
            fallback.source }
  | _ ->
      { fallback with
        source =
          Printf.sprintf "no interest expense for the fiscal period ending %s beside debt of %.4g, so no rating is read; %s" period_end
            total_debt fallback.source }

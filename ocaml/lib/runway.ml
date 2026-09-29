open Boundary_t

let free_cash_flow (p : fiscal_period) =
  match (p.operating_cash_flow, p.capex) with
  | Some ocf, Some capex -> Some (ocf -. capex)
  | _ -> None

let releases_within ~years ~days_to_next ~cadence_days =
  let horizon = years *. 365.25 in
  if cadence_days <= 0. || days_to_next < 0 || float_of_int days_to_next > horizon then 0
  else 1 + int_of_float ((horizon -. float_of_int days_to_next) /. cadence_days)

let of_record ~entity_class ~periods ~(calendar : earnings_calendar option) ~calendar_reason ~valued_on =
  match entity_class with
  | Some `Unprofitable -> (
      match periods with
      | [] -> (None, Some "no fiscal period")
      | (latest : fiscal_period) :: _ -> (
          let missing =
            List.filter_map
              (fun (name, v) -> if Option.is_none v then Some name else None)
              [ ("cash", latest.cash); ("operating_cash_flow", latest.operating_cash_flow); ("capex", latest.capex) ]
          in
          match (missing, latest.cash, free_cash_flow latest) with
          | _ :: _, _, _ | _, None, _ | _, _, None ->
              (None, Some (Printf.sprintf "the latest fiscal period (%s) carries no %s" latest.period_end (String.concat ", " missing)))
          | [], Some cash, Some fcf ->
              let burn = if fcf < 0. then Some (-.fcf) else None in
              let years = match burn with Some b when b > 0. -> Some (cash /. b) | _ -> None in
              let history =
                List.filter_map
                  (fun (p : fiscal_period) -> Option.map (fun f -> { period_end = p.period_end; free_cash_flow = f }) (free_cash_flow p))
                  periods
              in
              let next_release, days_to_next, cadence_days, releases, why =
                match calendar with
                | None -> (None, None, None, None, Some (Option.value calendar_reason ~default:"no earnings calendar on the record"))
                | Some c -> (
                    let days = match Date.days_between ~from:valued_on ~until:c.next_date with Ok d -> Some d | Error _ -> None in
                    match (years, days, c.cadence_days) with
                    | Some y, Some d, Some cad -> (Some c.next_date, Some d, Some cad, Some (releases_within ~years:y ~days_to_next:d ~cadence_days:cad), None)
                    | None, d, cad -> (Some c.next_date, d, cad, None, Some "the period funded itself, so there is no runway to count releases against")
                    | Some _, None, _ -> (Some c.next_date, None, c.cadence_days, None, Some "the calendar's next date does not parse against valued_on")
                    | Some _, Some d, None -> (Some c.next_date, Some d, None, None, Some "the calendar carries no cadence, so the releases inside the runway cannot be counted"))
              in
              ( Some
                  {
                    period_end = latest.period_end;
                    cash;
                    total_debt = latest.total_debt;
                    free_cash_flow = fcf;
                    burn;
                    years_of_runway = years;
                    self_funding = Option.is_none burn;
                    history;
                    next_release;
                    days_to_next;
                    cadence_days;
                    releases_within_runway = releases;
                    calendar_reason = why;
                    basis =
                      "cash and short-term investments over the burn of the latest fiscal period, the burn being the cash-flow statement's net cash \
                       from operating activities less capital spending, both as filed, in the statement currency; a state, not a forecast";
                  },
                None )))
  | _ -> (None, None)

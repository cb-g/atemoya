open Boundary_t

let adjusted_book (p : fiscal_period) =
  match (p.book_equity, p.aoci) with
  | Some equity, Some aoci -> Some (equity -. aoci)
  | _ -> None

let requires_filed (fin : financials) =
  let prefix = "insurer model requires filed-statement data" in
  if fin.statements_unavailable <> "" then
    Some (Printf.sprintf "%s; %s" prefix fin.statements_unavailable)
  else
    match Period.latest fin with
    | None -> Some (Printf.sprintf "%s; no filed statements for %s" prefix fin.ticker)
    | Some p ->
        if Option.is_none p.aoci || Option.is_none p.premiums_earned then
          Some
            (Printf.sprintf
               "%s; the fiscal period ending %s carries no AOCI or premiums earned (provider %s)"
               prefix p.period_end
               (if fin.provider = "" then "unknown" else fin.provider))
        else None

let ratio num den =
  match (num, den) with Some n, Some d when d > 0. -> Some (n /. d) | _ -> None

let value a ~terminal_spread ~country (fin : financials) =
  let ( let* ) = Result.bind in
  let* () = match requires_filed fin with Some reason -> Error reason | None -> Ok () in
  let* core, fair_value =
    Residual_income.value ~book:adjusted_book a ~terminal_spread ~country fin
  in
  let p = Option.get (Period.latest fin) in
  let reported_book_equity = Option.get p.book_equity in
  let aoci = Option.get p.aoci in
  let premiums_earned = Option.get p.premiums_earned in
  let combined_ratio_proxy, combined_ratio_basis =
    match (p.benefits_losses_and_expenses, p.claims_incurred) with
    | Some total, _ ->
        ( Some (total /. premiums_earned),
          "benefits, losses and expenses (the filed total) over premiums earned" )
    | None, Some claims ->
        let expenses =
          Option.value p.policy_acquisition_expense ~default:0.
          +. Option.value p.operating_expense ~default:0.
        in
        ( Some ((claims +. expenses) /. premiums_earned),
          "claims incurred plus policy acquisition and operating expense where filed, over \
           premiums earned" )
    | None, None -> (None, "no claims or total benefits line filed")
  in
  let reserves =
    match (p.future_policy_benefits, p.claims_liability) with
    | None, None -> None
    | a, b -> Some (Option.value a ~default:0. +. Option.value b ~default:0.)
  in
  Ok
    ( {
        core;
        provider = fin.provider;
        filed = p.filed;
        accession = p.accession;
        reported_book_equity;
        aoci;
        aoci_row = p.aoci_row;
        aoci_to_reported_book = aoci /. reported_book_equity;
        premiums_earned;
        premiums_earned_row = p.premiums_earned_row;
        claims_incurred = p.claims_incurred;
        claims_incurred_row = p.claims_incurred_row;
        benefits_losses_and_expenses = p.benefits_losses_and_expenses;
        benefits_losses_and_expenses_row = p.benefits_losses_and_expenses_row;
        policy_acquisition_expense = p.policy_acquisition_expense;
        policy_acquisition_expense_row = p.policy_acquisition_expense_row;
        operating_expense = p.operating_expense;
        operating_expense_row = p.operating_expense_row;
        combined_ratio_proxy;
        combined_ratio_basis;
        future_policy_benefits = p.future_policy_benefits;
        future_policy_benefits_row = p.future_policy_benefits_row;
        claims_liability = p.claims_liability;
        claims_liability_row = p.claims_liability_row;
        reserves_to_premiums = ratio reserves (Some premiums_earned);
        solvency = None;
        solvency_basis = "not available from filed financial statements";
      },
      fair_value )

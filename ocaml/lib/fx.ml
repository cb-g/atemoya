open Boundary_t

type legs = {
  fx_rate : float;
  usd_per_financial : float;
  usd_per_trading : float;
  source : string;
  as_of : string;
  age_days : int;
}

let ( let* ) = Result.bind

(* One leg: USD per unit, with its date; USD itself is 1 with no date. *)
let leg (sources : Reference_t.fx_sources) (rates : Reference_t.fx_rates) ~today ~pair code =
  if code = "USD" then Ok (1.0, None)
  else
    match List.assoc_opt code rates.currencies with
    | None -> Error (Printf.sprintf "fx not available for %s" pair)
    | Some (r : Reference_t.fx_rate) ->
        let* age = Date.days_between ~from:r.as_of ~until:today in
        if age < 0 then
          Error
            (Printf.sprintf "fx for %s has as_of %s, later than the valuation date %s" code
               r.as_of today)
        else if age > sources.max_age_days then
          Error
            (Printf.sprintf
               "fx for %s (as_of %s) is %d days old, older than its max_age_days %d" code
               r.as_of age sources.max_age_days)
        else if r.usd_per_unit <= 0. then
          Error (Printf.sprintf "fx for %s is not positive" code)
        else Ok (r.usd_per_unit, Some (r.as_of, age, r.series))

let rate sources rates ~today ~financial ~trading =
  let pair = financial ^ "/" ^ trading in
  let* usd_per_financial, fin_leg = leg sources rates ~today ~pair financial in
  let* usd_per_trading, trade_leg = leg sources rates ~today ~pair trading in
  let described =
    List.filter_map
      (fun (code, l) -> Option.map (fun (as_of, age, series) -> (code, as_of, age, series)) l)
      [ (financial, fin_leg); (trading, trade_leg) ]
  in
  let as_of, age_days =
    (* the older leg dates the conversion *)
    List.fold_left
      (fun (d, a) (_, as_of, age, _) -> if age > a then (as_of, age) else (d, a))
      (today, 0) described
  in
  let source =
    match described with
    | [] -> "USD to USD"
    | legs ->
        String.concat "; "
          (List.map (fun (code, _, _, series) -> Printf.sprintf "%s via FRED %s" code series) legs)
        ^ (if List.length legs = 2 then ", cross rate through USD" else "")
  in
  Ok { fx_rate = usd_per_financial /. usd_per_trading; usd_per_financial; usd_per_trading; source; as_of; age_days }

let country_of (sources : Reference_t.fx_sources) currency =
  match List.assoc_opt currency sources.currency_countries with
  | Some c -> Ok c
  | None -> Error (Printf.sprintf "no country for trading currency %s in fx_sources" currency)

let scale rate = Option.map (fun v -> v *. rate)

let scale_composition rate =
  Option.map (fun (c : composition) ->
      { c with components = List.map (fun (k : component) -> { k with value = k.value *. rate }) c.components })

let convert ~rate (fin : financials) =
  let period (p : fiscal_period) =
    {
      p with
      ebit = scale rate p.ebit;
      pretax_income = scale rate p.pretax_income;
      tax_provision = scale rate p.tax_provision;
      total_revenue = scale rate p.total_revenue;
      net_interest_income = scale rate p.net_interest_income;
      premiums_earned = scale rate p.premiums_earned;
      depreciation_amortization = scale rate p.depreciation_amortization;
      capex = scale rate p.capex;
      delta_nwc = scale rate p.delta_nwc;
      cash = scale rate p.cash;
      total_debt = scale rate p.total_debt;
      book_equity = scale rate p.book_equity;
      net_income = scale rate p.net_income;
      dividends_paid = scale rate p.dividends_paid;
      provision_for_credit_losses = scale rate p.provision_for_credit_losses;
      net_loans = scale rate p.net_loans;
      aoci = scale rate p.aoci;
      claims_incurred = scale rate p.claims_incurred;
      benefits_losses_and_expenses = scale rate p.benefits_losses_and_expenses;
      policy_acquisition_expense = scale rate p.policy_acquisition_expense;
      operating_expense = scale rate p.operating_expense;
      future_policy_benefits = scale rate p.future_policy_benefits;
      claims_liability = scale rate p.claims_liability;
      ebit_composition = scale_composition rate p.ebit_composition;
      cash_composition = scale_composition rate p.cash_composition;
      total_debt_composition = scale_composition rate p.total_debt_composition;
      delta_nwc_composition = scale_composition rate p.delta_nwc_composition;
    }
  in
  { fin with periods = List.map period fin.periods; currency = fin.trading_currency }

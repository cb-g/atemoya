open Boundary_t

let roe_path ~roe_0 ~cost_of_equity ~lambda ~projection_years =
  List.init (max 0 projection_years) (fun i ->
      let t = float_of_int (i + 1) in
      cost_of_equity +. ((roe_0 -. cost_of_equity) *. exp (-.lambda *. t)))

type schedule = {
  book_value_path : float list;
  excess_return_path : float list;
  pv_excess_returns : float;
  ending_book : float;
}

let schedule ~book_equity ~cost_of_equity ~retention ~roe_path =
  let discount i = (1. +. cost_of_equity) ** float_of_int i in
  let rec go i book pv books excesses = function
    | [] ->
        {
          book_value_path = List.rev books;
          excess_return_path = List.rev excesses;
          pv_excess_returns = pv;
          ending_book = book;
        }
    | roe :: rest ->
        let excess = (roe -. cost_of_equity) *. book in
        go (i + 1)
          (book *. (1. +. (roe *. retention)))
          (pv +. (excess /. discount i))
          (book :: books) (excess :: excesses) rest
  in
  go 1 book_equity 0. [] [] roe_path

let mean_ratio rows ~min_periods =
  let usable =
    List.filter_map
      (fun (period_end, num, den) -> if den > 0. then Some (period_end, num /. den) else None)
      rows
    |> List.sort (fun (a, _) (b, _) -> compare b a)
  in
  if List.length usable < min_periods then None
  else
    let n = float_of_int (List.length usable) in
    Some (List.fold_left (fun acc (_, r) -> acc +. r) 0. usable /. n, List.map fst usable)

let absent name opt = if Option.is_none opt then Some name else None

let value ?(book = fun (p : fiscal_period) -> p.book_equity) (a : Dcf.assumptions) ~country
    (fin : financials) =
  let ( let* ) = Result.bind in
  let* p =
    match Period.latest fin with
    | None -> Error "no fiscal periods in statements"
    | Some p -> Ok p
  in
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
      [ absent "book_equity" (book p); absent "net_income" p.net_income ]
  in
  let part label = function
    | [] -> None
    | names -> Some (label ^ ": " ^ String.concat ", " names)
  in
  let missing =
    String.concat "; "
      (List.filter_map Fun.id
         [
           part "missing market data" market;
           part
             (Printf.sprintf "missing statement fields for fiscal period ending %s"
                p.period_end)
             statement;
         ])
  in
  match (fin.currency, fin.price, fin.market_cap, book p, p.net_income) with
  | Some _currency, Some price, Some market_cap, Some book_equity, Some net_income ->
      if price <= 0. || market_cap <= 0. then
        Error (Printf.sprintf "price %g and market cap %g must be positive" price market_cap)
      else if book_equity <= 0. then
        Error (Printf.sprintf "book equity %g is not positive" book_equity)
      else
        (* ROE_0: net income over book, averaged. *)
        let roe_rows =
          List.filter_map
            (fun (q : fiscal_period) ->
              match (q.net_income, book q) with
              | Some ni, Some be -> Some (q.period_end, ni, be)
              | _ -> None)
            fin.periods
        in
        let* roe_0, roe_periods =
          match mean_ratio roe_rows ~min_periods:2 with
          | Some r -> Ok r
          | None ->
              Error
                (Printf.sprintf
                   "roe not derivable: need 2 fiscal periods with net income and positive \
                    book equity, have %d"
                   (List.length (List.filter (fun (_, _, be) -> be > 0.) roe_rows)))
        in
        (* Payout: dividends over net income where net income is positive, clamped. *)
        let payout_rows =
          List.filter_map
            (fun (q : fiscal_period) ->
              match (q.dividends_paid, q.net_income) with
              | Some d, Some ni when ni > 0. -> Some (q.period_end, Float.min d ni, ni)
              | _ -> None)
            fin.periods
        in
        let* payout_ratio, payout_periods =
          match mean_ratio payout_rows ~min_periods:2 with
          | Some (r, periods) -> Ok (Float.max 0. (Float.min 1. r), periods)
          | None ->
              Error
                (Printf.sprintf
                   "payout not derivable: need 2 fiscal periods with positive net income \
                    and dividends paid, have %d"
                   (List.length payout_rows))
        in
        let retention = 1. -. payout_ratio in
        let cost_of_equity =
          let domestic =
            a.risk_free_rate.value +. (a.beta.value *. a.equity_risk_premium.value)
          in
          match a.country_risk_premium with
          | None -> domestic
          | Some crp -> domestic +. crp.value
        in
        if a.projection_years.value < 0 then
          Error
            (Printf.sprintf "projection horizon %d years is negative" a.projection_years.value)
        else
          let projection_years = a.projection_years.value in
          let roe_path =
            roe_path ~roe_0 ~cost_of_equity ~lambda:a.mean_reversion_lambda.value
              ~projection_years
          in
          let s = schedule ~book_equity ~cost_of_equity ~retention ~roe_path in
          (* No terminal: ROE has reverted to the cost of equity, and growth at the cost of
             equity is value neutral. *)
          let equity_value = book_equity +. s.pv_excess_returns in
          let shares = market_cap /. price in
          let fair_value = equity_value /. shares in
          let ratio num den =
            match (num, den) with
            | Some n, Some d when d > 0. -> Some (n /. d)
            | _ -> None
          in
          if not (Float.is_finite fair_value) then
            Error
              (Printf.sprintf "fair value is not finite (equity value %g, shares %g)"
                 equity_value shares)
          else
            Ok
              ( {
                  fiscal_period_end = p.period_end;
                  country;
                  industry = fin.industry;
                  price;
                  market_cap;
                  shares;
                  book_equity;
                  book_value_per_share = book_equity /. shares;
                  net_income;
                  roe_0;
                  roe_periods;
                  payout_ratio;
                  retention;
                  payout_periods;
                  dividends_paid = p.dividends_paid;
                  dividends_paid_row = p.dividends_paid_row;
                  risk_free_rate = a.risk_free_rate;
                  equity_risk_premium = a.equity_risk_premium;
                  country_risk_premium = a.country_risk_premium;
                  beta = a.beta;
                  beta_source = a.beta_source;
                  cost_of_equity;
                  conversion = None;
                  mean_reversion_lambda = a.mean_reversion_lambda;
                  projection_years = a.projection_years;
                  roe_path;
                  book_value_path = s.book_value_path;
                  excess_return_path = s.excess_return_path;
                  pv_excess_returns = s.pv_excess_returns;
                  equity_value;
                  justified_price_to_book = equity_value /. book_equity;
                  net_interest_income = p.net_interest_income;
                  provision_for_credit_losses = p.provision_for_credit_losses;
                  provision_for_credit_losses_row = p.provision_for_credit_losses_row;
                  provision_to_net_interest_income =
                    ratio p.provision_for_credit_losses p.net_interest_income;
                  net_loans = p.net_loans;
                  net_loans_row = p.net_loans_row;
                  provision_to_net_loans = ratio p.provision_for_credit_losses p.net_loans;
                },
                fair_value )
  | _ -> Error missing

open Boundary_t

(* (58) The reversion target is a parameter. It defaults to the cost of equity at every
   call site, which is brief 15's anchor and leaves every number where it was; it is a
   parameter so the belief on this path has something to be about, the long-run return on
   equity, and so the implied solver has something to sweep. The discounting and the
   excess return are still measured against the cost of equity: only the level the path
   reverts to moves. *)
let roe_path ~roe_0 ~roe_target ~lambda ~projection_years =
  List.init (max 0 projection_years) (fun i ->
      let t = float_of_int (i + 1) in
      roe_target +. ((roe_0 -. roe_target) *. exp (-.lambda *. t)))

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

(* (69) Residual income values COMMON equity, and preferred stock is a claim senior to it.
   Its dividends are not the common holder's income and its carrying value is not the common
   holder's book, so income, book and the payout numerator are all read common-only.

   **Both or neither.** The filing does not always support all three. A filer that pays
   preferred dividends but files no carrying value for it -- Morgan Stanley files none at all,
   and PNC, MetLife and UnitedHealth file a par line of zero beside real preferred -- can give
   a common income but not a common book, and common income over total book is neither
   reading: it understates the return on a book it does not belong to. Where the filing cannot
   support both, every figure stays on the total-equity basis and the record says so. The one
   exception is redeemable preferred, which is mezzanine equity and never sat inside the book
   at all: there the income moves and the book is already common. *)
type basis = {
  income : fiscal_period -> float option;
  book : fiscal_period -> float option;
  dividends : fiscal_period -> float option;
  dividends_row : fiscal_period -> string option;
  name : string;
  why : string;
  preferred_equity : float option;
  preferred_equity_row : string option;
}

let total_basis ~book ~why =
  {
    income = (fun (q : fiscal_period) -> q.net_income);
    book;
    dividends = (fun (q : fiscal_period) -> q.dividends_paid);
    dividends_row = (fun (q : fiscal_period) -> q.dividends_paid_row);
    name = "total";
    why;
    preferred_equity = None;
    preferred_equity_row = None;
  }

let income_to_common (q : fiscal_period) =
  (* the filed figure first: it is the filer's own arithmetic, and it nets out participating
     securities as well as preferred, which a subtraction cannot reproduce *)
  match (q.net_income_to_common, q.net_income, q.preferred_dividends) with
  | Some filed, _, _ -> Some filed
  | None, Some ni, Some pref -> Some (ni -. pref)
  | None, ni, _ -> ni

let common_of ~book (p : fiscal_period) =
  let pays_preferred = Option.is_some p.preferred_dividends in
  let outside = p.preferred_outside_equity = Some true in
  let has_carrying = Option.is_some p.preferred_equity in
  let filed_common = Option.is_some p.net_income_to_common in
  if (not pays_preferred) && not filed_common then
    total_basis ~book ~why:"no preferred dividend and no available-to-common figure filed: common equity is the whole of it"
  else if pays_preferred && (not has_carrying) && not outside then
    total_basis ~book
      ~why:
        "preferred dividends are filed but no preferred carrying value is: income, book and \
         retention all stay on the total-equity basis, because common income over total book \
         is neither reading"
  else
    let deduction (q : fiscal_period) =
      match (book q, q.preferred_equity) with
      | Some b, Some pref -> Some (b -. pref)
      | b, None -> b
      | None, _ -> None
    in
    {
      income = income_to_common;
      book = (if outside then book else deduction);
      dividends =
        (fun (q : fiscal_period) ->
          match q.common_dividends_paid with Some d -> Some d | None -> q.dividends_paid);
      dividends_row =
        (fun (q : fiscal_period) ->
          match q.common_dividends_paid with
          | Some _ -> q.common_dividends_paid_row
          | None -> q.dividends_paid_row);
      name = "common";
      why =
        (if outside then
           "the preferred is redeemable and sits outside stockholders' equity, so the income is \
            the common holder's after the preferred dividend and the book already is"
         else if has_carrying then
           "the available-to-common income, the book less the filed preferred carrying value, and \
            the common dividend"
         else
           "an available-to-common figure is filed and no preferred dividend is: the common side \
            is what the filer reports");
      preferred_equity = p.preferred_equity;
      preferred_equity_row = p.preferred_equity_row;
    }


let value ?roe_target ?(book = fun (p : fiscal_period) -> p.book_equity) (a : Dcf.assumptions) ~country
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
  (* (69) one basis for the whole record, chosen from the latest period and applied to every
     ROE and payout row: a book on one basis against an income on another is not a return *)
  let b = common_of ~book p in
  let statement =
    List.filter_map Fun.id [ absent "book_equity" (b.book p); absent "net_income" (b.income p) ]
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
  match (fin.currency, fin.price, fin.market_cap, b.book p, b.income p) with
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
              match (b.income q, b.book q) with
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
              match (b.dividends q, b.income q) with
              | Some d, Some ni when ni > 0. -> Some (q.period_end, Float.min d ni, ni)
              | _ -> None)
            fin.periods
        in
        (* (65) A filer that has never distributed anything has no ratio to take a mean of,
           and an absent dividend tag cannot say so on its own. Where the filing carries the
           cash-flow statement's financing subtotal and no dividend element of any kind, it
           has said it paid none, and retention is 1 on the periods that say it. *)
        let filed_none =
          List.filter
            (fun (q : fiscal_period) ->
              match (b.income q, q.no_distributions_filed) with
              | Some ni, Some true when ni > 0. -> true
              | _ -> false)
            fin.periods
        in
        let* payout_ratio, payout_periods, payout_source =
          match mean_ratio payout_rows ~min_periods:2 with
          | Some (r, periods) -> Ok (Float.max 0. (Float.min 1. r), periods, "")
          | None when List.length filed_none >= 2 ->
              Ok
                ( 0.,
                  List.map (fun (q : fiscal_period) -> q.period_end) filed_none,
                  "no dividend element filed alongside a filed financing section; taken as no distributions" )
          | None ->
              Error
                (Printf.sprintf
                   "payout not derivable: need 2 fiscal periods with positive net income \
                    and dividends paid, have %d"
                   (List.length payout_rows))
        in
        let retention = 1. -. payout_ratio in
        let cost_of_equity = Dcf.cost_of_equity a in
        if a.projection_years.value < 0 then
          Error
            (Printf.sprintf "projection horizon %d years is negative" a.projection_years.value)
        else
          let projection_years = a.projection_years.value in
          let roe_target = Option.value roe_target ~default:cost_of_equity in
          let roe_path =
            roe_path ~roe_0 ~roe_target ~lambda:a.mean_reversion_lambda.value
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
                  payout_source;
                  retention;
                  payout_periods;
                  dividends_paid = b.dividends p;
                  dividends_paid_row = b.dividends_row p;
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
                  common_basis = b.name;
                  common_basis_why = b.why;
                  preferred_equity = b.preferred_equity;
                  preferred_equity_row = b.preferred_equity_row;
                  (* recorded whether or not the basis moved: a reader is owed the figure that
                     decided it, not only the decision *)
                  preferred_dividends = p.preferred_dividends;
                  preferred_dividends_row = p.preferred_dividends_row;
                },
                fair_value )
  | _ -> Error missing

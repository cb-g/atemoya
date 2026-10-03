open Boundary_t

let scope_limits =
  [ "nine yes-or-no signals carry no magnitudes: a margin a hair higher counts as much as one transformed";
    "assets are each year's own year-end figure, where the original reads the opening balance; leverage reads the record's financial debt, where the original reads long-term debt";
    "a share count that rose by more than a quarter is left null: a split and an issue cannot be told apart from the two counts";
    "a bank or an insurer files no current assets and no gross profit, so three signals are null there and the score is not formed";
    "independent of every valuation here: no fair value, margin of safety or signal reads it" ]

let ratio a b = match (a, b) with Some x, Some y when y <> 0. -> Some (x /. y) | _ -> None

let signal name ~current ~prior passed : quality_signal = { name; passed; current; prior }

(* A level signal: one figure against zero. *)
let positive name x = signal name ~current:x ~prior:None (Option.map (fun v -> v > 0.) x)

(* A change signal: this year's figure against last year's. *)
let compare_years name ~better cur prior =
  signal name ~current:cur ~prior
    (match (cur, prior) with Some c, Some p -> Some (better c p) | _ -> None)

let of_financials (fin : financials) =
  let reason r = (None, Some r) in
  let sorted = List.sort (fun (p : fiscal_period) (q : fiscal_period) -> compare q.period_end p.period_end) fin.periods in
  match (fin.quality_lines, fin.quality_lines_reason, sorted) with
  | [], Some why, _ -> reason why
  | [], None, _ -> reason "the record carries no quality lines: fetched before the block existed"
  | _, _, ([] | [ _ ]) -> reason "fewer than two fiscal periods in the statements"
  | lines, _, t :: p :: _ -> (
      match Date.days_between ~from:p.period_end ~until:t.period_end with
      | Ok d when d >= 350 && d <= 380 ->
          let line_of (q : fiscal_period) = List.find_opt (fun (l : quality_lines) -> l.period_end = q.period_end) lines in
          let get f (q : fiscal_period) = Option.bind (line_of q) f in
          let assets = get (fun l -> l.total_assets) in
          let gross (q : fiscal_period) =
            match get (fun l -> l.gross_profit) q with
            | Some g -> Some g
            | None -> (
                match (q.total_revenue, get (fun l -> l.cost_of_revenue) q) with Some r, Some c -> Some (r -. c) | _ -> None)
          in
          let roa (q : fiscal_period) = ratio q.net_income (assets q) in
          let leverage (q : fiscal_period) = ratio q.total_debt (assets q) in
          let current_ratio (q : fiscal_period) = ratio (get (fun l -> l.current_assets) q) (get (fun l -> l.current_liabilities) q) in
          let margin (q : fiscal_period) = ratio (gross q) q.total_revenue in
          let turnover (q : fiscal_period) = ratio q.total_revenue (assets q) in
          let shares =
            match (t.weighted_shares, p.weighted_shares) with
            | Some c, Some b when b > 0. && c /. b > 1.25 -> signal "no_more_shares" ~current:(Some c) ~prior:(Some b) None
            | c, b -> compare_years "no_more_shares" ~better:(fun c b -> c <= b) c b
          in
          let signals =
            [ positive "return_on_assets_positive" (roa t);
              positive "operating_cash_flow_positive" t.operating_cash_flow;
              compare_years "return_on_assets_higher" ~better:( > ) (roa t) (roa p);
              signal "cash_flow_above_net_income" ~current:t.operating_cash_flow ~prior:t.net_income
                (match (t.operating_cash_flow, t.net_income) with Some c, Some n -> Some (c > n) | _ -> None);
              compare_years "leverage_lower" ~better:(fun c b -> c < b || (c = 0. && b = 0.)) (leverage t) (leverage p);
              compare_years "current_ratio_higher" ~better:( > ) (current_ratio t) (current_ratio p);
              shares;
              compare_years "gross_margin_higher" ~better:( > ) (margin t) (margin p);
              compare_years "asset_turnover_higher" ~better:( > ) (turnover t) (turnover p) ]
          in
          let available = List.filter (fun (s : quality_signal) -> Option.is_some s.passed) signals in
          let passed = List.length (List.filter (fun (s : quality_signal) -> s.passed = Some true) available) in
          let average_assets =
            match (assets t, assets p) with Some a, Some b -> Some ((a +. b) /. 2.) | _ -> None
          in
          let accruals =
            match (t.net_income, t.operating_cash_flow) with Some n, Some c -> ratio (Some (n -. c)) average_assets | _ -> None
          in
          ( Some
              {
                period_end = t.period_end;
                prior_period_end = p.period_end;
                signals;
                signals_available = List.length available;
                f_score = (if List.length available = 9 then Some passed else None);
                signals_passed = passed;
                accruals_ratio = accruals;
                gross_profitability = ratio (gross t) (assets t);
                scope_limits;
              },
            None )
      | Ok d -> reason (Printf.sprintf "the latest two fiscal periods, %s and %s, are %d days apart and not consecutive years" p.period_end t.period_end d)
      | Error e -> reason e)

let latest (fin : Boundary_t.financials) =
  (* ISO dates order lexicographically. *)
  match
    List.sort
      (fun (a : Boundary_t.fiscal_period) (b : Boundary_t.fiscal_period) ->
        compare b.period_end a.period_end)
      fin.periods
  with
  | [] -> None
  | p :: _ -> Some p

let value (p : Boundary_t.fiscal_period) = function
  | "ebit" -> p.ebit
  | "net_income" -> p.net_income
  | "interest_expense" -> p.interest_expense
  | "depreciation_amortization" -> p.depreciation_amortization
  | "capex" -> p.capex
  | "delta_nwc" -> p.delta_nwc
  | "cash" -> p.cash
  | "total_debt" -> p.total_debt
  | "book_equity" -> p.book_equity
  | "pretax_income" -> p.pretax_income
  | "tax_provision" -> p.tax_provision
  | "total_revenue" -> p.total_revenue
  | "dividends_paid" -> p.dividends_paid
  | "ffo" -> p.ffo
  | "aoci" -> p.aoci
  | "premiums_earned" -> p.premiums_earned
  | name -> invalid_arg ("Period.value: no field named " ^ name)

let missing p names = List.filter (fun n -> Option.is_none (value p n)) names

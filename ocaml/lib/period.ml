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

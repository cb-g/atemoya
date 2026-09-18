type estimate = {
  nopat : float;
  invested_capital : float;
  roic : float option;
  reinvestment : float;
  reinvestment_rate : float option;
  g_fundamental : float option;
  g_historical : float option;
  revenue_periods : string list;
}

let cagr revenues =
  let usable =
    List.filter (fun (_, r) -> r > 0.) revenues
    |> List.sort (fun (a, _) (b, _) -> compare a b)
  in
  let periods = List.rev_map fst usable in
  match usable with
  | (first_end, first) :: _ when List.length usable >= 3 -> (
      let last_end, last = List.nth usable (List.length usable - 1) in
      match Date.days_between ~from:first_end ~until:last_end with
      | Ok days when days > 0 ->
          let years = float_of_int days /. 365.25 in
          (Some (((last /. first) ** (1. /. years)) -. 1.), periods)
      | _ -> (None, periods))
  | _ -> (None, periods)

let estimate ~ebit ~tax_rate ~book_equity ~total_debt ~capex ~delta_nwc
    ~depreciation_amortization ~revenues =
  let nopat = ebit *. (1. -. tax_rate) in
  let invested_capital = book_equity +. total_debt in
  let roic =
    if invested_capital > 0. then Some (nopat /. invested_capital) else None
  in
  let reinvestment = capex +. delta_nwc -. depreciation_amortization in
  let reinvestment_rate =
    if nopat > 0. then Some (reinvestment /. nopat) else None
  in
  let g_fundamental =
    match (roic, reinvestment_rate) with
    | Some r, Some rr -> Some (r *. rr)
    | _ -> None
  in
  let g_historical, revenue_periods = cagr revenues in
  {
    nopat;
    invested_capital;
    roic;
    reinvestment;
    reinvestment_rate;
    g_fundamental;
    g_historical;
    revenue_periods;
  }

let select e =
  match (e.g_fundamental, e.reinvestment_rate) with
  | Some g, Some rr when e.nopat > 0. && rr > 0. -> Ok (g, `Fundamental)
  | _ -> (
      match e.g_historical with
      | None ->
          Error
            (Printf.sprintf
               "growth not derivable: fundamental growth needs nopat > 0 and \
                net reinvestment > 0 (nopat %g, reinvestment %g, invested \
                capital %g); historical growth needs at least 3 fiscal \
                periods with revenue (have %d)"
               e.nopat e.reinvestment e.invested_capital
               (List.length e.revenue_periods))
      | Some g -> (
          match e.roic with
          | Some roic when g > roic -> Ok (roic, `Historical_capped_at_roic)
          | _ -> Ok (g, `Historical)))

let clamp ~lower ~upper g =
  if g < lower then (lower, true)
  else if g > upper then (upper, true)
  else (g, false)

let path ~g0 ~terminal_growth_rate ~lambda ~projection_years =
  List.init (max 0 projection_years) (fun i ->
      let t = float_of_int (i + 1) in
      terminal_growth_rate
      +. ((g0 -. terminal_growth_rate) *. exp (-.lambda *. t)))

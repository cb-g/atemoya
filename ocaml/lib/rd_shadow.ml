open Boundary_t

type schedule = {
  rd_latest : float;
  rd_tag : string;
  rd_years : string list;
  research_asset : float;
  amortization : float;
}

(* Consecutive fiscal years end about a year apart; a 52/53-week calendar moves the end by
   a few days and a changed year end by months, which is a gap. *)
let year_apart ~earlier ~later =
  match Date.days_between ~from:earlier ~until:later with Ok d -> d >= 350 && d <= 380 | Error _ -> false

let schedule ~life ~latest (history : rd_year list) =
  if life < 1 then Error (Printf.sprintf "the declared amortisation life %d is not a positive number of years" life)
  else
    let sorted = List.sort (fun (a : rd_year) (b : rd_year) -> compare b.period_end a.period_end) history in
    match List.filter (fun (y : rd_year) -> y.period_end <= latest) sorted with
    | [] -> Error "no research and development expense is filed for this name"
    | first :: _ when first.period_end <> latest ->
        Error (Printf.sprintf "no research and development expense is filed for the fiscal period ending %s; the newest is %s" latest first.period_end)
    | first :: rest ->
        (* the latest year, then exactly [life] more, each a year before the one after it *)
        let rec take acc (previous : rd_year) n = function
          | _ when n = 0 -> Ok (List.rev acc)
          | [] ->
              Error
                (Printf.sprintf "%d consecutive fiscal years of research and development are filed up to %s; a %d-year life needs %d"
                   (List.length acc) latest life (life + 1))
          | (y : rd_year) :: tail ->
              if year_apart ~earlier:y.period_end ~later:previous.period_end then take (y :: acc) y (n - 1) tail
              else
                Error
                  (Printf.sprintf "the filed research and development years are not consecutive: %s is followed by %s; %d of the %d years a %d-year life needs"
                     y.period_end previous.period_end (List.length acc) (life + 1) life)
        in
        Result.map
          (fun (years : rd_year list) ->
            let n = float_of_int life in
            let research_asset, amortization, _ =
              List.fold_left
                (fun (asset, amort, k) (y : rd_year) ->
                  let k_f = float_of_int k in
                  ( (if k < life then asset +. (y.value *. (n -. k_f) /. n) else asset),
                    (if k >= 1 then amort +. (y.value /. n) else amort),
                    k + 1 ))
                (0., 0., 0) years
            in
            {
              rd_latest = first.value;
              rd_tag = first.tag;
              rd_years = List.map (fun (y : rd_year) -> y.period_end) years;
              research_asset;
              amortization;
            })
          (take [ first ] first life rest)

let restate ~tax_rate (s : schedule) (p : fiscal_period) =
  match (p.ebit, p.capex, p.depreciation_amortization, p.book_equity) with
  | Some ebit, Some capex, Some da, Some book_equity when tax_rate < 1. ->
      Some
        {
          p with
          ebit = Some (ebit +. ((s.rd_latest -. s.amortization) /. (1. -. tax_rate)));
          capex = Some (capex +. s.rd_latest);
          depreciation_amortization = Some (da +. s.amortization);
          book_equity = Some (book_equity +. s.research_asset);
        }
  | _ -> None

let scope_limits =
  [ "one straight-line life for every industry: a drug's research earns for longer than software's, and the declared life does not yet tell them apart";
    "every dollar of research and development is capitalised as if it becomes an earning asset; failed research is not written off";
    "selling and marketing spend that builds customers or a brand is not capitalised, only the filed research and development line";
    "a shadow: the record's fair value, margin of safety and signal are the headline's and are not moved by this block" ]

let of_dcf ?declared ~(life : Reference_t.int_scalar option) (a : Dcf.assumptions) ~country (fin : financials)
    ~headline:((headline : inputs), headline_fair_value) =
  let reason r = (None, Some r) in
  match life with
  | None -> reason "the reference directory declares no rd_amortization_years"
  | Some life -> (
      match (fin.rd_history, fin.rd_history_reason, Period.latest fin) with
      | [], Some why, _ -> reason why
      | [], None, _ -> reason "the record carries no research and development history: fetched before the shadow existed"
      | _, _, None -> reason "no fiscal periods in statements"
      | history, _, Some p -> (
          match schedule ~life:life.value ~latest:p.period_end history with
          | Error why -> reason why
          | Ok s -> (
              match restate ~tax_rate:headline.tax_rate s p with
              | None -> reason "the latest period lacks a line the restatement needs"
              | Some restated -> (
                  let periods =
                    List.map (fun (q : fiscal_period) -> if q.period_end = p.period_end then restated else q) fin.periods
                  in
                  match Dcf.value ?declared a ~country { fin with periods } with
                  | Error why -> reason ("the DCF on the restated statements: " ^ why)
                  | Ok (shadow, fair_value) ->
                      if fair_value <= 0. then
                        reason (Printf.sprintf "non-positive shadow fair value %g" fair_value)
                      else
                        ( Some
                            {
                              amortization_years = life.value;
                              amortization_years_source = life.source;
                              rd_latest = s.rd_latest;
                              rd_years = s.rd_years;
                              rd_tag = s.rd_tag;
                              research_asset = s.research_asset;
                              amortization = s.amortization;
                              nopat = headline.nopat;
                              nopat_adjusted = shadow.nopat;
                              invested_capital = headline.invested_capital;
                              invested_capital_adjusted = shadow.invested_capital;
                              roic = headline.roic;
                              roic_adjusted = shadow.roic;
                              reinvestment_rate = headline.reinvestment_rate;
                              reinvestment_rate_adjusted = shadow.reinvestment_rate;
                              growth_source = headline.growth_source;
                              growth_source_adjusted = shadow.growth_source;
                              g0 = headline.g0;
                              g0_adjusted = shadow.g0;
                              fcff = shadow.fcff;
                              headline_fair_value;
                              fair_value;
                              margin_of_safety = (fair_value -. shadow.price) /. shadow.price;
                              scope_limits;
                            },
                          None )))))

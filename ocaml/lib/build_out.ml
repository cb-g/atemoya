open Boundary_t

(* (60) A readout, not a model. Every number here answers one question — what must the new
   capital earn, and how soon, for today's price to be right — and the record it sits on
   stays Failed with its own reason. *)

let observation_guard = "mid-cycle normalisation needs at least"
let free_cash_flow_guard = "non-positive free cash flow"
let tranche_years = 3
let lags = [ 0; 1; 2; 3; 4; 5; 6 ]
let span = 0.15
let step = 0.01

let returns_axis declared =
  (* Thirty-one steps of a point, the declared return exactly in the middle. *)
  List.init 31 (fun i -> declared -. span +. (float_of_int i *. step))

let growth_capex ~capex ~depreciation_amortization =
  Float.max 0. (capex -. depreciation_amortization)

let maintenance_note =
  "growth capex in a year is capex less depreciation where positive, and maintenance is \
   depreciation: no filer discloses the split, so depreciation is the proxy"

(* (63) A declaration belongs in the units its holder reasons in. Every filing and every
   reader states a return on capital after depreciation, so that is what is declared; the
   readout needs the cash yield before the maintenance it charges, and converting between
   them is the tool's job, not the declarer's. The ratio it adds is the same one it charges
   as maintenance, so the two are consistent by construction and a tranche's free cash flow
   is exactly the declared return on its cost. *)
let cash_return ~accounting_return ~depreciation_to_capital =
  accounting_return +. depreciation_to_capital

let conversion_note =
  "the return is declared after depreciation, as a filing states it; the readout adds the \
   depreciation-to-capital ratio to reach the cash yield it then charges that same ratio \
   against, so the tranche's free cash flow is the declared return on its cost"

let scope_limits_of_readout =
  [ "the maintenance split is a proxy: depreciation stands in for maintenance capex, which no filer discloses";
    "the standing business is held flat, which understates a growing one and overstates a fading one";
    "every dollar of growth capex is valued as if it becomes earning capital, which no build-out achieves";
    "a map of what the price requires, not a value: no fair value, no margin of safety and no signal follow from it" ]

let gate ~entity_class ~failed_reason ~periods =
  let contains needle haystack =
    let n = String.length needle and h = String.length haystack in
    let rec at i = i + n <= h && (String.sub haystack i n = needle || at (i + 1)) in
    n = 0 || at 0
  in
  match entity_class with
  | Some (`Cyclical | `OperatingCompany) -> (
      (* Out of scope, not a finding: the record failed for some other reason and says
         nothing about a build-out. Neither field appears on it. *)
      if
        not
          (contains observation_guard failed_reason
          || contains free_cash_flow_guard failed_reason)
      then None
      else
        Some
          (match periods with
        | [] -> Error "no fiscal period"
        | latest :: _ -> (
            match (latest.capex, latest.depreciation_amortization, latest.ebit) with
            | None, _, _ -> Error "the latest fiscal period carries no capex"
            | _, None, _ -> Error "the latest fiscal period carries no depreciation"
            | _, _, None -> Error "the latest fiscal period carries no operating income"
            | Some capex, Some depreciation, Some ebit ->
                if ebit <= 0. then
                  Error
                    (Printf.sprintf
                       "the latest operating income (%.4g) is not positive: what a build-out earns is not this name's question"
                       ebit)
                else if capex <= depreciation then
                  Error
                    (Printf.sprintf
                       "the latest capex (%.4g) does not exceed depreciation (%.4g): there is no build-out to read"
                       capex depreciation)
                else Ok ())))
  | _ -> None

(* A flat perpetuity of [flow] starting [start] years from now, discounted at [wacc]: the
   first payment arrives at the end of year [start + 1], so the perpetuity's value at year
   [start] is discounted [start] times. *)
let perpetuity ~flow ~wacc ~start =
  if wacc <= 0. then 0. else flow /. wacc /. ((1. +. wacc) ** float_of_int start)

let value_per_share ~standing ~tranches ~depreciation_to_capital ~wacc ~net_debt ~shares
    ~build_out_return ~lag_years =
  (* [build_out_return] is the accounting return, as declared (63). *)
  let cash = cash_return ~accounting_return:build_out_return ~depreciation_to_capital in
  let build_out =
    List.fold_left
      (fun acc (t : build_out_tranche) ->
        (* The tranche starts earning [lag_years] after the year it was spent; a year that
           has already passed is not discounted again, never negatively. *)
        let start = max 0 (lag_years - t.years_before_latest) in
        let flow = (cash -. depreciation_to_capital) *. t.growth_capex in
        acc +. perpetuity ~flow ~wacc ~start)
      0. tranches
  in
  (standing +. build_out -. net_debt) /. shares

(* The return at which the surface crosses the price at one lag, by bisection on the same
   arithmetic the grid draws, over the declared range. Monotone in the return, because every
   tranche's flow rises with it and nothing else moves. *)
let contour ~value_at ~price ~returns ~lag_years =
  match (returns, List.rev returns) with
  | [], _ | _, [] -> { lag_years; return_required = None; contour_reason = Some "no return axis" }
  | low :: _, high :: _ ->
      let at r = value_at ~build_out_return:r ~lag_years in
      let vlow = at low and vhigh = at high in
      if vhigh < price then
        {
          lag_years;
          return_required = None;
          contour_reason =
            Some
              (Printf.sprintf
                 "no return in the declared range reaches the price: at %.1f%% and a %d-year lag the map is %.4g against %.4g"
                 (high *. 100.) lag_years vhigh price);
        }
      else if vlow > price then
        {
          lag_years;
          return_required = None;
          contour_reason =
            Some
              (Printf.sprintf
                 "the price is below the map's whole range: at %.1f%% and a %d-year lag the map is already %.4g against %.4g"
                 (low *. 100.) lag_years vlow price);
        }
      else
        let rec bisect lo hi n =
          if n = 0 then 0.5 *. (lo +. hi)
          else
            let mid = 0.5 *. (lo +. hi) in
            if at mid < price then bisect mid hi (n - 1) else bisect lo mid (n - 1)
        in
        { lag_years; return_required = Some (bisect low high 60); contour_reason = None }

let of_record ~(declared_return : Reference_t.declared_build_out)
    ~(declared_lag_years : Reference_t.declared_build_out) ~periods ~price ~market_cap ~cash
    ~total_debt ~book_equity ~wacc ~tax_rate ~terminal_growth_rate ~scope_limits =
  match periods with
  | [] -> Error "no fiscal period"
  | latest :: _ -> (
      match (latest.ebit, latest.depreciation_amortization, latest.capex, latest.delta_nwc) with
      | Some ebit, Some depreciation, Some _, Some delta_nwc ->
          if wacc <= terminal_growth_rate then
            Error
              (Printf.sprintf "wacc %.4f does not exceed terminal growth %.4f" wacc
                 terminal_growth_rate)
          else if price <= 0. || market_cap <= 0. then
            Error (Printf.sprintf "price %g and market cap %g must be positive" price market_cap)
          else
            let invested_capital = total_debt +. book_equity -. cash in
            if invested_capital <= 0. then
              Error
                (Printf.sprintf "invested capital %.4g is not positive: the tranche's own maintenance has no ratio" invested_capital)
            else
              let tranches =
                List.filteri (fun i _ -> i < tranche_years) periods
                |> List.mapi (fun i (p : fiscal_period) ->
                       match (p.capex, p.depreciation_amortization) with
                       | Some capex, Some dep ->
                           Some
                             {
                               period_end = p.period_end;
                               years_before_latest = i;
                               capex;
                               depreciation_amortization = dep;
                               growth_capex = growth_capex ~capex ~depreciation_amortization:dep;
                             }
                       | _ -> None)
                |> List.filter_map Fun.id
                |> List.filter (fun (t : build_out_tranche) -> t.growth_capex > 0.)
              in
              if tranches = [] then
                Error "no year in the last three carries capex above depreciation"
              else
                let shares = market_cap /. price in
                let net_debt = total_debt -. cash in
                (* The standing business: the same free cash flow the DCF computes, with
                   maintenance capex in place of the capex actually spent, held flat and
                   discounted as a perpetuity at the settled terminal growth. *)
                let standing_flow =
                  Dcf.fcff ~ebit ~tax_rate ~depreciation_amortization:depreciation
                    ~capex:depreciation ~delta_nwc
                in
                let standing = standing_flow /. (wacc -. terminal_growth_rate) in
                let depreciation_to_capital = depreciation /. invested_capital in
                let returns = returns_axis declared_return.value in
                let value_at ~build_out_return ~lag_years =
                  value_per_share ~standing ~tranches ~depreciation_to_capital ~wacc ~net_debt
                    ~shares ~build_out_return ~lag_years
                in
                let surface =
                  List.map
                    (fun lag_years ->
                      {
                        lag_years;
                        value_per_share =
                          List.map (fun r -> value_at ~build_out_return:r ~lag_years) returns;
                      })
                    lags
                in
                let price_contour =
                  List.map (fun lag_years -> contour ~value_at ~price ~returns ~lag_years) lags
                in
                Ok
                  {
                    declared_return =
                      {
                        value = declared_return.value;
                        why = declared_return.why;
                        as_of = declared_return.as_of;
                      };
                    declared_lag_years =
                      {
                        value = declared_lag_years.value;
                        why = declared_lag_years.why;
                        as_of = declared_lag_years.as_of;
                      };
                    cash_return =
                      cash_return ~accounting_return:declared_return.value ~depreciation_to_capital;
                    conversion_note;
                    maintenance_note;
                    tranches;
                    standing_business_per_share = (standing -. net_debt) /. shares;
                    net_debt;
                    shares;
                    wacc;
                    tax_rate;
                    terminal_growth_rate;
                    depreciation_to_capital;
                    returns;
                    surface;
                    price_contour;
                    scope_limits = scope_limits @ scope_limits_of_readout;
                  }
      | None, _, _, _ -> Error "the latest fiscal period carries no operating income"
      | _, None, _, _ -> Error "the latest fiscal period carries no depreciation"
      | _, _, None, _ -> Error "the latest fiscal period carries no capex"
      | _, _, _, None -> Error "the latest fiscal period carries no change in working capital")

open Boundary_t

(* Two readouts from the statements on what the capital is doing (decided 2026-10-18,
   docs/run.md, capital intensity and goodwill): the latest period's spending against its
   depreciation, on every record that carries both, and the generic DCF's return on capital
   with and without acquired goodwill. Both describe; neither moves a value, a growth or a
   signal, and neither declares a build-out, which is the universe entry's judgment. *)

let intensity_limits =
  [ "capex less depreciation is growth capital spending and depreciation is maintenance, the build-out readout's own split rule, because no filer discloses the split; a filer whose depreciation runs behind its asset base understates maintenance here and the growth figure overstates";
    "describes the latest fiscal period's spending against its depreciation; whether the capital is a build-out, and what it will earn, is a judgment declared on the universe entry (build_out, build_out_return, build_out_lag_years) and this block makes none";
    "fcff_maintenance, on a generic DCF record, is the headline's free cash flow with maintenance capex in place of the capex spent: what the standing business throws off if the growth spending stopped, not a value and not the headline's base";
    Measured.capital_intensity ]

let intensity (p : fiscal_period option) ~fcff =
  match p with
  | None -> Error "no fiscal period"
  | Some p -> (
      match (p.capex, p.depreciation_amortization) with
      | Some capex, Some da when da > 0. ->
          let growth_capex = Float.max 0. (capex -. da) in
          Ok
            {
              period_end = p.period_end;
              capex;
              depreciation_amortization = da;
              capex_over_depreciation = capex /. da;
              growth_capex;
              fcff_maintenance = Option.map (fun f -> f +. growth_capex) fcff;
              scope_limits = intensity_limits;
            }
      | Some _, Some da -> Error (Printf.sprintf "depreciation %.4g is not positive" da)
      | None, _ -> Error "the latest fiscal period carries no capex"
      | _, None -> Error "the latest fiscal period carries no depreciation")

let goodwill_limits =
  [ "goodwill is the filer's balance as tagged under the Goodwill element, acquired goodwill after impairments; other acquired intangibles stay in invested capital on both sides";
    "the return without goodwill reads what the operations earn on the capital they use, the return with it what the shareholders paid for them; neither is the right one for every question, and the headline keeps the one with goodwill, so an acquirer's fundamental growth estimate leans low";
    "a share of goodwill near one leaves a thin capital base and a return without goodwill that moves with every small change in it";
    Measured.goodwill ]

let goodwill (p : fiscal_period option) (i : inputs) =
  match p with
  | None -> Error "no fiscal period"
  | Some p -> (
      match p.goodwill with
      | None -> Error "goodwill not filed for the latest fiscal period: the filer tags none under the Goodwill element"
      | Some g ->
          let ex = i.invested_capital -. g in
          Ok
            {
              period_end = p.period_end;
              goodwill = g;
              goodwill_row = p.goodwill_row;
              invested_capital = i.invested_capital;
              invested_capital_ex_goodwill = ex;
              goodwill_share = (if i.invested_capital > 0. then Some (g /. i.invested_capital) else None);
              roic = i.roic;
              roic_ex_goodwill = (if ex > 0. then Some (i.nopat /. ex) else None);
              scope_limits = goodwill_limits;
            })

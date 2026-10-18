open Boundary_t

(* The four-quarter shadow (decided 2026-10-18, docs/run.md): the generic DCF run once more
   with the statements' trailing period, the last four filed quarters as one period, as the
   base, the annual periods behind it as history. Beside the headline, never the headline. *)

let rule =
  "the generic DCF on the last four filed quarters as one period, the annual periods behind it as history; everything but the base period is the headline's own"

let no_trailing = "no trailing period in the statements"

let scope_limits =
  [ "a shadow: the record's fair value, margin of safety and signal are the headline's, on the annual base, and are not moved by this block";
    "the base is the last four filed quarters read as one period: each line the fiscal year-to-date figure plus the prior year's annual figure less the prior year's year-to-date figure, the balance sheet at the quarter end; the quarters are reviewed and not audited, and a quarter's one-off lands in the base in full";
    "the working-capital change is the mean over the trailing period and the annual periods behind it, which overlap by up to three quarters, and the revenue history mixes the trailing period with annual ones; the growth estimates are read from the trailing base as the headline reads them from the annual";
    "a base on the latest quarters moves when the quarters move, as the price already has; on a surging or collapsing name it capitalises the latest run-rate, which the annual base does not, so the two values bracket what a year of lag is worth and neither is the other's correction (docs/run.md, the four-quarter shadow)";
    "a line the quarterly filings cannot carry whole is null on the trailing period rather than a partial sum (the basis notes name the row), and a null working-capital change there leaves the mean to the annual periods, which the shadow's delta_nwc_periods show";
    "only a filer of quarterly reports has one; a 20-F filer and a name on vendor statements carry the reason instead";
    Measured.four_quarter_shadow ]

let value ?(declared = "") a ~country (fin : financials) ~fair_value =
  match fin.trailing_period with
  | None -> Error (Option.value fin.trailing_period_reason ~default:no_trailing)
  | Some t -> (
      match t.ebit_recipe with
      | Some recipe when recipe <> "operating_income" ->
          (* the headline's policy on a derived ebit is a cross-check against the vendor's
             annual figure; no vendor figure checks a trailing period, so the shadow stops *)
          Error
            (Printf.sprintf
               "the trailing period's ebit is derived (%s) and no vendor figure checks a trailing period"
               recipe)
      | _ -> (
          let annual = Period.latest fin in
          let shadowed = { fin with periods = t :: fin.periods } in
          match Dcf.value ~declared a ~country shadowed with
          | Error reason -> Error ("the trailing period: " ^ reason)
          | Ok (inputs, shadow_value) ->
              let revenue_over_annual =
                match (t.total_revenue, Option.bind annual (fun (p : fiscal_period) -> p.total_revenue)) with
                | Some tr, Some ar when ar > 0. -> Some ((tr /. ar) -. 1.)
                | _ -> None
              in
              Ok
                {
                  rule;
                  period_end = t.period_end;
                  annual_base_end = (match annual with Some p -> p.period_end | None -> "");
                  quarters_in_year_to_date =
                    (match fin.trailing_basis with Some b -> b.quarters_in_year_to_date | None -> 0);
                  headline_fair_value = fair_value;
                  fair_value = shadow_value;
                  margin_of_safety = (shadow_value -. inputs.price) /. inputs.price;
                  revenue_over_annual;
                  inputs;
                  scope_limits;
                }))

(* What the annual base costs the fair value, on the record beside it (the A+ sentence of
   the same decision): which period the models read, how far the filed quarters have moved
   on from it on revenue, which way the fair value leans for it, and whether a four-quarter
   shadow stands beside it. One sentence; empty without a recency block. *)
let base_limits ~(recency : recency option) ~generic ~(shadow : (four_quarter_shadow, string) result option) =
  match recency with
  | None -> []
  | Some r ->
      let quarters =
        Printf.sprintf "%d quarter%s filed since" r.quarters_since_base (if r.quarters_since_base = 1 then " has been" else "s have been")
      in
      let beside =
        match (generic, shadow) with
        | true, Some (Ok _) -> "the four-quarter shadow beside it values the same model on the last four quarters"
        | true, Some (Error reason) -> "there is no four-quarter shadow: " ^ reason
        | true, None -> "there is no four-quarter shadow: " ^ no_trailing
        | false, _ -> "no model here reads the quarters, the mid-cycle, residual-income, REIT and NAV paths reading annual periods"
      in
      let head = Printf.sprintf "the base the models read is the annual period ending %s; %s" r.annual_base_end quarters in
      let body =
        match r.trailing_over_annual with
        | None ->
            Printf.sprintf " and the quarters do not chain (%s), so how far the base is behind is not measured"
              (Option.value r.trailing_reason ~default:"no trailing figure")
        | Some x when Float.abs x <= 0.01 ->
            " and the last four quarters' revenue runs within a per cent of it, so the base is current"
        | Some x ->
            let pct = Float.abs x *. 100. in
            let within =
              match r.divergence with
              | Some d when Float.abs x > d -> Printf.sprintf "beyond the declared divergence of %.0f per cent" (d *. 100.)
              | Some d -> Printf.sprintf "within the declared divergence of %.0f per cent" (d *. 100.)
              | None -> "with no divergence declared"
            in
            Printf.sprintf
              " and the last four quarters' revenue runs %.1f per cent %s it, %s, so if margins held the fair value is projected from a business about that much %s than the one now filed and leans %s by about that step until the next annual report lands"
              pct
              (if x > 0. then "above" else "below")
              within
              (if x > 0. then "smaller" else "larger")
              (if x > 0. then "low" else "high")
      in
      [ head ^ body ^ "; " ^ beside ]

(** Raw trading-basis fundamentals -> oriented factor values.

    Every factor is a unitless ratio oriented so HIGHER = BETTER (cheaper for value,
    higher-quality for quality). Value factors are expressed as YIELDS (metric/EV or
    metric/marketcap), never price-multiples — yields stay finite and correctly
    ordered through zero (a loss-maker gets a negative yield = genuinely worse,
    whereas EV/EBIT would explode and rank-poison the sector).

    Inputs are already FX-converted to trading basis and sign-normalized by the
    Python fetcher (revenue, ebit, ebitda, gross_profit, net_income,
    operating_cash_flow, free_cash_flow, total_assets, total_equity, total_debt,
    total_cash, shareholder_payout, tax_provision, pretax_income, market_cap), so
    every ratio here is currency-neutral. Missing inputs -> the factor is omitted. *)

open Types

let field (row : panel_row) k = List.assoc_opt k row.fields

let safe_div a b = if Float.abs b < 1e-12 then None else Some (a /. b)
let ratio name a b = match safe_div a b with Some v -> Some (name, v) | None -> None

(* EV = market cap + total debt - cash (net-debt basis). Requires market cap. *)
let ev row =
  match field row "market_cap" with
  | Some mc ->
    Some (mc
          +. Option.value (field row "total_debt") ~default:0.
          -. Option.value (field row "total_cash") ~default:0.)
  | None -> None

(** Value factors (yields; higher = cheaper). EV-based factors are dropped when
    EV <= 0 (net-cash names) so a sign flip can't manufacture a top rank.
    book_price KEEPS its sign (negative equity = genuinely worse -> ranks low). *)
let value_factors row : (string * float) list =
  let g = field row in
  let evv = match ev row with Some e when e > 0. -> Some e | _ -> None in
  let mc = g "market_cap" in
  List.filter_map (fun x -> x)
    [ (match g "ebit", evv with Some a, Some b -> ratio "ebit_ev" a b | _ -> None);
      (match g "ebitda", evv with Some a, Some b -> ratio "ebitda_ev" a b | _ -> None);
      (match g "free_cash_flow", evv with Some a, Some b -> ratio "fcf_ev" a b | _ -> None);
      (match g "revenue", evv with Some a, Some b -> ratio "sales_ev" a b | _ -> None);
      (match g "net_income", mc with Some a, Some b -> ratio "earnings_yield" a b | _ -> None);
      (match g "total_equity", mc with Some a, Some b -> ratio "book_price" a b | _ -> None);
      (match g "shareholder_payout", mc with Some a, Some b -> ratio "shareholder_yield" a b | _ -> None) ]

(** Quality factors (higher = better). ROIC uses an effective tax rate clamped to
    [0, 0.35] (0.21 default when pretax <= 0). accruals and leverage are negated so
    LOW accruals / LOW leverage rank high. Leverage guards EBITDA > 0. *)
let quality_factors row : (string * float) list =
  let g = field row in
  let tax =
    match g "tax_provision", g "pretax_income" with
    | Some tp, Some pre when pre > 0. -> Float.max 0. (Float.min 0.35 (tp /. pre))
    | _ -> 0.21
  in
  List.filter_map (fun x -> x)
    [ (match g "ebit", g "total_equity" with
       | Some ebit, Some eq ->
         let invested = Option.value (g "total_debt") ~default:0. +. eq in
         if invested > 0. then Some ("roic", ebit *. (1. -. tax) /. invested) else None
       | _ -> None);
      (match g "gross_profit", g "total_assets" with Some a, Some b -> ratio "gp_assets" a b | _ -> None);
      (match g "gross_profit", g "revenue" with Some a, Some b -> ratio "gross_margin" a b | _ -> None);
      (match g "net_income", g "total_equity" with
       | Some a, Some b when b > 0. -> ratio "roe" a b | _ -> None);
      (match g "net_income", g "operating_cash_flow", g "total_assets" with
       | Some ni, Some ocf, Some a when a > 0. -> Some ("accruals_neg", -.((ni -. ocf) /. a))
       | _ -> None);
      (match g "total_debt", g "ebitda" with
       | Some td, Some ebitda when ebitda > 0. ->
         let nd = td -. Option.value (g "total_cash") ~default:0. in
         Some ("leverage_neg", -.(nd /. ebitda))
       | _ -> None) ]

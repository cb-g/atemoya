(** Cost and Liquidity Analysis *)

open Types

(** Classify expense ratio tier *)
let classify_cost_tier (expense_ratio : float) : cost_tier =
  (* Thresholds are in decimal form: 0.0005 = 0.05% *)
  if expense_ratio < 0.0005 then UltraLowCost      (* < 0.05% *)
  else if expense_ratio < 0.001 then LowCost       (* < 0.10% *)
  else if expense_ratio < 0.002 then ModerateCost  (* < 0.20% *)
  else if expense_ratio < 0.005 then HighCost      (* < 0.50% *)
  else VeryHighCost

(** Get string representation of cost tier *)
let cost_tier_to_string (tier : cost_tier) : string =
  match tier with
  | UltraLowCost -> "Ultra-Low Cost (<0.05%)"
  | LowCost -> "Low Cost (<0.10%)"
  | ModerateCost -> "Moderate Cost (<0.20%)"
  | HighCost -> "High Cost (<0.50%)"
  | VeryHighCost -> "Very High Cost (>=0.50%)"

(** Score expense ratio (0-25) *)
let score_expense_ratio (expense_ratio : float) : float =
  if expense_ratio < 0.0005 then 25.0      (* < 0.05% *)
  else if expense_ratio < 0.001 then 20.0  (* < 0.10% *)
  else if expense_ratio < 0.002 then 15.0  (* < 0.20% *)
  else if expense_ratio < 0.005 then 10.0  (* < 0.50% *)
  else 5.0

(** Classify liquidity tier based on spread and volume *)
let classify_liquidity_tier (spread_pct : float) (daily_dollar_volume : float) : liquidity_tier =
  (* Daily dollar volume thresholds *)
  let high_volume = daily_dollar_volume > 1_000_000_000.0 in    (* $1B+ *)
  let med_volume = daily_dollar_volume > 100_000_000.0 in       (* $100M+ *)
  let low_volume = daily_dollar_volume > 10_000_000.0 in        (* $10M+ *)

  if spread_pct < 0.02 && high_volume then HighlyLiquid
  else if spread_pct < 0.05 && med_volume then Liquid
  else if spread_pct < 0.10 && low_volume then ModeratelyLiquid
  else Illiquid

(** Get string representation of liquidity tier *)
let liquidity_tier_to_string (tier : liquidity_tier) : string =
  match tier with
  | HighlyLiquid -> "Highly Liquid"
  | Liquid -> "Liquid"
  | ModeratelyLiquid -> "Moderately Liquid"
  | Illiquid -> "Illiquid"

(** Score liquidity (0-25) *)
let score_liquidity (spread_pct : float) (avg_volume : float) (price : float) : float =
  let daily_dollar_volume = avg_volume *. price in
  let spread_score =
    if spread_pct < 0.02 then 12.5
    else if spread_pct < 0.05 then 10.0
    else if spread_pct < 0.10 then 7.5
    else if spread_pct < 0.25 then 5.0
    else 2.5
  in
  let volume_score =
    if daily_dollar_volume > 1_000_000_000.0 then 12.5
    else if daily_dollar_volume > 100_000_000.0 then 10.0
    else if daily_dollar_volume > 10_000_000.0 then 7.5
    else if daily_dollar_volume > 1_000_000.0 then 5.0
    else 2.5
  in
  spread_score +. volume_score

(** Classify size tier based on AUM *)
let classify_size_tier (aum : float) : size_tier =
  if aum > 100_000_000_000.0 then Mega        (* > $100B *)
  else if aum > 10_000_000_000.0 then Large   (* > $10B *)
  else if aum > 1_000_000_000.0 then Medium   (* > $1B *)
  else if aum > 100_000_000.0 then Small      (* > $100M *)
  else Micro

(** Get string representation of size tier *)
let size_tier_to_string (tier : size_tier) : string =
  match tier with
  | Mega -> "Mega (>$100B)"
  | Large -> "Large (>$10B)"
  | Medium -> "Medium (>$1B)"
  | Small -> "Small (>$100M)"
  | Micro -> "Micro (≤$100M)"

(** Score AUM/size (0-25) *)
let score_size (aum : float) : float =
  if aum > 10_000_000_000.0 then 25.0        (* > $10B *)
  else if aum > 1_000_000_000.0 then 20.0    (* > $1B *)
  else if aum > 100_000_000.0 then 15.0      (* > $100M *)
  else if aum > 10_000_000.0 then 10.0       (* > $10M *)
  else 5.0

(** Calculate total cost of ownership estimate (annual) *)
let calculate_tco (expense_ratio : float) (spread_pct : float) (holding_years : float) : float =
  (* TCO = ER + (spread impact / holding period) *)
  (* Spread paid on entry and exit, so divide by holding period *)
  let spread_cost_annual = (spread_pct *. 2.0) /. holding_years in
  (expense_ratio *. 100.0) +. spread_cost_annual

(** Calculate breakeven holding period *)
let calculate_breakeven_holding (etf1_er : float) (etf1_spread : float)
    (etf2_er : float) (etf2_spread : float) : float option =
  (* At what holding period does the lower-ER ETF become cheaper? *)
  let er_diff = etf1_er -. etf2_er in
  let spread_diff = etf2_spread -. etf1_spread in  (* Reversed: lower spread is better *)

  if er_diff <= 0.0 then
    (* ETF1 already has lower ER *)
    Some 0.0
  else if spread_diff <= 0.0 then
    (* ETF2 has both higher ER and higher spread - never breaks even *)
    None
  else
    (* Solve: er_diff * years = spread_diff * 2 *)
    Some ((spread_diff *. 2.0 *. 100.0) /. (er_diff *. 100.0))

(** Generate cost-related recommendations *)
let generate_cost_recommendations (data : etf_data) : string list =
  let recs = ref [] in

  (* Expense ratio recommendations *)
  if data.expense_ratio > 0.005 then
    recs := Printf.sprintf "High expense ratio (%.2f%%) - check for lower-cost alternatives" (data.expense_ratio *. 100.0) :: !recs
  else if data.expense_ratio < 0.0005 then
    recs := "Ultra-low cost - excellent for long-term holding" :: !recs;

  (* Spread recommendations *)
  if data.bid_ask_spread_pct > 0.25 then
    recs := Printf.sprintf "Wide bid-ask spread (%.2f%%) - use limit orders" data.bid_ask_spread_pct :: !recs
  else if data.bid_ask_spread_pct > 0.10 then
    recs := "Moderate spread - consider timing trades during market hours" :: !recs;

  (* Size/closure risk *)
  if data.aum < 50_000_000.0 then
    recs := "Low AUM (<$50M) - fund closure risk" :: !recs
  else if data.aum < 100_000_000.0 then
    recs := "Small AUM - monitor for potential closure" :: !recs;

  List.rev !recs

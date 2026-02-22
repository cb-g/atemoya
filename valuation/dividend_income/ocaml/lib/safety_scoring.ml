(** Dividend safety scoring *)

open Types

(** Score payout ratio (0-25 points)
    Lower payout = more room for growth and safety *)
let score_payout_ratio (payout : float) : float =
  if payout <= 0.0 then 0.0  (* No dividend or invalid *)
  else if payout < 0.40 then 25.0
  else if payout < 0.50 then 22.0
  else if payout < 0.60 then 18.0
  else if payout < 0.70 then 14.0
  else if payout < 0.80 then 10.0
  else if payout < 0.90 then 5.0
  else 0.0

(** Score FCF coverage (0-25 points)
    Higher coverage = more sustainable dividend *)
let score_fcf_coverage (coverage : float) : float =
  if coverage <= 0.0 then 0.0
  else if coverage >= 3.0 then 25.0
  else if coverage >= 2.5 then 22.0
  else if coverage >= 2.0 then 18.0
  else if coverage >= 1.5 then 14.0
  else if coverage >= 1.2 then 10.0
  else if coverage >= 1.0 then 5.0
  else 0.0

(** Score dividend track record (0-25 points)
    Longer streak = more reliable dividend *)
let score_dividend_streak (consecutive_years : int) : float =
  if consecutive_years >= 50 then 25.0      (* King *)
  else if consecutive_years >= 25 then 23.0 (* Aristocrat *)
  else if consecutive_years >= 20 then 20.0
  else if consecutive_years >= 15 then 17.0
  else if consecutive_years >= 10 then 15.0 (* Achiever *)
  else if consecutive_years >= 5 then 12.0  (* Contender *)
  else if consecutive_years >= 3 then 8.0
  else if consecutive_years >= 1 then 5.0   (* Challenger *)
  else 0.0

(** Score balance sheet strength (0-15 points)
    Lower debt = more ability to maintain dividend in downturns *)
let score_balance_sheet (debt_to_equity : float) (current_ratio : float) : float =
  let debt_score =
    if debt_to_equity < 0.3 then 10.0
    else if debt_to_equity < 0.5 then 8.0
    else if debt_to_equity < 0.75 then 6.0
    else if debt_to_equity < 1.0 then 4.0
    else if debt_to_equity < 1.5 then 2.0
    else 0.0
  in
  let liquidity_score =
    if current_ratio >= 2.0 then 5.0
    else if current_ratio >= 1.5 then 4.0
    else if current_ratio >= 1.0 then 2.0
    else 0.0
  in
  debt_score +. liquidity_score

(** Score earnings/profitability stability (0-10 points)
    Higher ROE and margins = more reliable earnings to pay dividends *)
let score_stability (roe : float) (profit_margin : float) : float =
  let roe_score =
    if roe >= 0.20 then 5.0
    else if roe >= 0.15 then 4.0
    else if roe >= 0.10 then 3.0
    else if roe >= 0.05 then 2.0
    else 0.0
  in
  let margin_score =
    if profit_margin >= 0.20 then 5.0
    else if profit_margin >= 0.15 then 4.0
    else if profit_margin >= 0.10 then 3.0
    else if profit_margin >= 0.05 then 2.0
    else 0.0
  in
  roe_score +. margin_score

(** Convert score to letter grade *)
let score_to_grade (score : float) : string =
  if score >= 85.0 then "A"
  else if score >= 75.0 then "A-"
  else if score >= 65.0 then "B+"
  else if score >= 55.0 then "B"
  else if score >= 45.0 then "C+"
  else if score >= 35.0 then "C"
  else if score >= 25.0 then "D"
  else "F"

(** Calculate complete dividend safety score *)
let calculate_safety_score (data : dividend_data) : safety_score =
  (* Use the better of EPS or FCF payout ratio for scoring *)
  (* This handles cases where one metric is anomalous (e.g., special charges) *)
  let payout_score_eps = score_payout_ratio data.payout_ratio_eps in
  let payout_score_fcf = score_payout_ratio data.payout_ratio_fcf in
  let payout_score = max payout_score_eps payout_score_fcf in

  (* Similarly, use the better coverage metric *)
  let coverage_score_eps =
    if data.eps_coverage > 0.0 then score_fcf_coverage data.eps_coverage
    else 0.0
  in
  let coverage_score_fcf = score_fcf_coverage data.fcf_coverage in
  let coverage_score = max coverage_score_eps coverage_score_fcf in
  let streak_score = score_dividend_streak data.consecutive_increases in
  let balance_sheet_score = score_balance_sheet data.debt_to_equity data.current_ratio in
  let stability_score = score_stability data.roe data.profit_margin in

  let total = payout_score +. coverage_score +. streak_score +. balance_sheet_score +. stability_score in

  {
    total_score = total;
    grade = score_to_grade total;
    payout_score;
    coverage_score;
    streak_score;
    balance_sheet_score;
    stability_score;
  }

(** Downgrade signal one level *)
let downgrade_signal = function
  | StrongBuyIncome -> BuyIncome
  | BuyIncome -> HoldIncome
  | HoldIncome -> CautionIncome
  | s -> s

(** Upgrade signal one level *)
let upgrade_signal = function
  | BuyIncome -> StrongBuyIncome
  | HoldIncome -> BuyIncome
  | CautionIncome -> HoldIncome
  | s -> s

(** Adjust signal based on DDM valuation *)
let adjust_signal_for_valuation (base : income_signal) (ddm : ddm_valuation) : income_signal =
  match base with
  | NotIncomeStock | AvoidIncome -> base
  | _ ->
    (match ddm.upside_downside_pct with
     | None -> base
     | Some upside ->
       if upside < -25.0 then downgrade_signal base
       else if upside >= 15.0 then upgrade_signal base
       else base)

(** Determine income signal based on safety score, yield, and DDM valuation *)
let determine_signal (data : dividend_data) (safety : safety_score) (ddm : ddm_valuation) : income_signal =
  let yield_pct = data.dividend_yield *. 100.0 in

  let base =
    (* No meaningful dividend *)
    if yield_pct < 0.5 || data.dividend_rate <= 0.0 then NotIncomeStock

    (* Check for obvious problems *)
    else if data.payout_ratio_eps > 1.0 || data.trailing_eps < 0.0 then AvoidIncome

    (* Score-based signals *)
    else if safety.total_score >= 80.0 && yield_pct >= 2.0 then StrongBuyIncome
    else if safety.total_score >= 65.0 then BuyIncome
    else if safety.total_score >= 45.0 then HoldIncome
    else if safety.total_score >= 25.0 then CautionIncome
    else AvoidIncome
  in

  adjust_signal_for_valuation base ddm

(** Generate recommendation text based on analysis *)
let generate_recommendation (data : dividend_data) (_safety : safety_score) (signal : income_signal) : string list =
  let positives = ref [] in
  let negatives = ref [] in

  (* Analyze strengths *)
  if data.consecutive_increases >= 25 then
    positives := "Dividend Aristocrat status (25+ years)" :: !positives
  else if data.consecutive_increases >= 10 then
    positives := Printf.sprintf "%d consecutive years of increases" data.consecutive_increases :: !positives;

  if data.payout_ratio_eps < 0.5 && data.payout_ratio_eps > 0.0 then
    positives := Printf.sprintf "Conservative %.0f%% payout ratio" (data.payout_ratio_eps *. 100.0) :: !positives;

  if data.fcf_coverage >= 1.5 then
    positives := Printf.sprintf "Strong FCF coverage (%.1fx)" data.fcf_coverage :: !positives;

  if data.dgr_5y >= 0.05 then
    positives := Printf.sprintf "Solid dividend growth (%.1f%% 5Y CAGR)" (data.dgr_5y *. 100.0) :: !positives;

  if data.debt_to_equity < 0.5 then
    positives := "Low debt levels" :: !positives;

  (* Analyze weaknesses *)
  if data.dividend_yield *. 100.0 > 6.0 then
    negatives := "Very high yield may signal risk" :: !negatives;

  if data.payout_ratio_eps > 0.8 then
    negatives := "High payout ratio limits growth" :: !negatives;

  if data.fcf_coverage < 1.2 && data.fcf_coverage > 0.0 then
    negatives := "Thin FCF coverage" :: !negatives;

  if data.dgr_5y < 0.0 then
    negatives := "Declining dividend" :: !negatives;

  if data.consecutive_increases < 5 then
    negatives := "Limited dividend growth track record" :: !negatives;

  let signal_text =
    match signal with
    | StrongBuyIncome -> "Strong Buy for Income"
    | BuyIncome -> "Buy for Income"
    | HoldIncome -> "Hold - Monitor"
    | CautionIncome -> "Caution - High Risk"
    | AvoidIncome -> "Avoid for Income"
    | NotIncomeStock -> "Not an Income Stock"
  in

  [signal_text] @
  (if List.length !positives > 0 then ["Positives:"] @ List.map (fun s -> "  + " ^ s) !positives else []) @
  (if List.length !negatives > 0 then ["Risks:"] @ List.map (fun s -> "  - " ^ s) !negatives else [])

(** Types for dividend income analysis *)

(** Raw dividend data from Python fetcher *)
type dividend_data = {
  ticker : string;
  company_name : string;
  sector : string;
  industry : string;
  current_price : float;
  market_cap : float;
  beta : float;
  dividend_rate : float;
  dividend_yield : float;
  ex_dividend_date : string option;
  payout_ratio_eps : float;
  payout_ratio_fcf : float;
  eps_coverage : float;
  fcf_coverage : float;
  trailing_eps : float;
  forward_eps : float;
  fcf_per_share : float;
  dgr_1y : float;
  dgr_3y : float;
  dgr_5y : float;
  dgr_10y : float;
  consecutive_increases : int;
  dividend_status : string;
  chowder_number : float;
  debt_to_equity : float;
  current_ratio : float;
  roe : float;
  roa : float;
  profit_margin : float;
  history_years : int;
}

(** Dividend payment record *)
type dividend_payment = {
  date : string;
  amount : float;
}

(** Dividend yield classification *)
type yield_tier =
  | VeryHighYield  (** > 6% - caution, may be unsustainable *)
  | HighYield      (** 4-6% - attractive for income *)
  | AboveAverage   (** 3-4% *)
  | Average        (** 2-3% *)
  | BelowAverage   (** 1-2% *)
  | LowYield       (** < 1% - growth focused *)

(** Dividend growth status *)
type dividend_status =
  | DividendKing       (** 50+ years of increases *)
  | DividendAristocrat (** 25+ years of increases *)
  | DividendAchiever   (** 10-24 years of increases *)
  | DividendContender  (** 5-9 years of increases *)
  | DividendChallenger (** 1-4 years of increases *)
  | NoStreak           (** No consecutive increases *)

(** Payout ratio assessment *)
type payout_assessment =
  | VerySafe         (** < 50% *)
  | Safe             (** 50-60% *)
  | Moderate         (** 60-75% *)
  | Elevated         (** 75-90% *)
  | Unsustainable    (** > 90% *)
  | PayingFromReserves (** > 100% *)

(** Calculated dividend metrics *)
type dividend_metrics = {
  yield_pct : float;
  yield_tier : yield_tier;
  annual_dividend : float;
  payout_ratio_eps : float;
  payout_ratio_fcf : float;
  payout_assessment : payout_assessment;
  eps_coverage : float;
  fcf_coverage : float;
  coverage_quality : string;
}

(** Dividend growth metrics *)
type growth_metrics = {
  dgr_1y : float;
  dgr_3y : float;
  dgr_5y : float;
  dgr_10y : float;
  consecutive_increases : int;
  dividend_status : dividend_status;
  chowder_number : float;
  chowder_assessment : string;
}

(** DDM valuation results *)
type ddm_valuation = {
  gordon_growth_value : float option;
  two_stage_value : float option;
  h_model_value : float option;
  yield_based_value : float option;
  average_fair_value : float option;
  upside_downside_pct : float option;
}

(** DDM parameters *)
type ddm_params = {
  required_return : float;       (** Investor's required return (e.g., 0.08 for 8%) *)
  terminal_growth : float;       (** Long-term sustainable growth (e.g., 0.03 for 3%) *)
  high_growth_years : int;       (** Years of above-normal growth *)
  historical_yield : float option; (** Historical average yield for yield-based valuation *)
}

(** Dividend safety score breakdown *)
type safety_score = {
  total_score : float;        (** 0-100 *)
  grade : string;             (** A, B, C, D, F *)
  payout_score : float;       (** 0-25 *)
  coverage_score : float;     (** 0-25 *)
  streak_score : float;       (** 0-25 *)
  balance_sheet_score : float; (** 0-15 *)
  stability_score : float;    (** 0-10 *)
}

(** Income signal *)
type income_signal =
  | StrongBuyIncome   (** Excellent for income investors *)
  | BuyIncome         (** Good dividend stock *)
  | HoldIncome        (** Adequate but not compelling *)
  | CautionIncome     (** Dividend at risk *)
  | AvoidIncome       (** High risk of cut *)
  | NotIncomeStock    (** No meaningful dividend *)

(** Complete dividend analysis result *)
type dividend_result = {
  ticker : string;
  company_name : string;
  sector : string;
  current_price : float;
  dividend_metrics : dividend_metrics;
  growth_metrics : growth_metrics;
  ddm_valuation : ddm_valuation;
  safety_score : safety_score;
  signal : income_signal;
}

(** Convert dividend_status string to type *)
let dividend_status_of_string s =
  match s with
  | "Dividend King" -> DividendKing
  | "Dividend Aristocrat" -> DividendAristocrat
  | "Dividend Achiever" -> DividendAchiever
  | "Dividend Contender" -> DividendContender
  | "Dividend Challenger" -> DividendChallenger
  | _ -> NoStreak

(** Convert dividend_status type to string *)
let string_of_dividend_status = function
  | DividendKing -> "Dividend King"
  | DividendAristocrat -> "Dividend Aristocrat"
  | DividendAchiever -> "Dividend Achiever"
  | DividendContender -> "Dividend Contender"
  | DividendChallenger -> "Dividend Challenger"
  | NoStreak -> "No Streak"

(** Convert yield_tier to string *)
let string_of_yield_tier = function
  | VeryHighYield -> "Very High (>6%)"
  | HighYield -> "High (4-6%)"
  | AboveAverage -> "Above Average (3-4%)"
  | Average -> "Average (2-3%)"
  | BelowAverage -> "Below Average (1-2%)"
  | LowYield -> "Low (<1%)"

(** Convert payout_assessment to string *)
let string_of_payout_assessment = function
  | VerySafe -> "Very Safe"
  | Safe -> "Safe"
  | Moderate -> "Moderate"
  | Elevated -> "Elevated"
  | Unsustainable -> "Unsustainable"
  | PayingFromReserves -> "Paying From Reserves"

(** Convert income_signal to string *)
let string_of_income_signal = function
  | StrongBuyIncome -> "Strong Buy for Income"
  | BuyIncome -> "Buy for Income"
  | HoldIncome -> "Hold"
  | CautionIncome -> "Caution"
  | AvoidIncome -> "Avoid"
  | NotIncomeStock -> "Not an Income Stock"

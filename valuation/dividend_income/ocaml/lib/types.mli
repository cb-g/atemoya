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

type dividend_payment = {
  date : string;
  amount : float;
}

type yield_tier =
  | VeryHighYield
  | HighYield
  | AboveAverage
  | Average
  | BelowAverage
  | LowYield

type dividend_status =
  | DividendKing
  | DividendAristocrat
  | DividendAchiever
  | DividendContender
  | DividendChallenger
  | NoStreak

type payout_assessment =
  | VerySafe
  | Safe
  | Moderate
  | Elevated
  | Unsustainable
  | PayingFromReserves

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

type ddm_valuation = {
  gordon_growth_value : float option;
  two_stage_value : float option;
  h_model_value : float option;
  yield_based_value : float option;
  average_fair_value : float option;
  upside_downside_pct : float option;
}

type ddm_params = {
  required_return : float;
  terminal_growth : float;
  high_growth_years : int;
  historical_yield : float option;
}

type safety_score = {
  total_score : float;
  grade : string;
  payout_score : float;
  coverage_score : float;
  streak_score : float;
  balance_sheet_score : float;
  stability_score : float;
}

type income_signal =
  | StrongBuyIncome
  | BuyIncome
  | HoldIncome
  | CautionIncome
  | AvoidIncome
  | NotIncomeStock

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

val dividend_status_of_string : string -> dividend_status
val string_of_dividend_status : dividend_status -> string
val string_of_yield_tier : yield_tier -> string
val string_of_payout_assessment : payout_assessment -> string
val string_of_income_signal : income_signal -> string

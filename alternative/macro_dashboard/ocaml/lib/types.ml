(** Macro Dashboard Types *)

(** Economic cycle phase *)
type cycle_phase =
  | EarlyCycle      (** Recovery: Rising growth, low inflation, easy policy *)
  | MidCycle        (** Expansion: Strong growth, rising inflation, neutral policy *)
  | LateCycle       (** Peak: Slowing growth, high inflation, tight policy *)
  | Recession       (** Contraction: Negative growth, falling inflation, easing policy *)

(** Yield curve state *)
type yield_curve_state =
  | Normal          (** Upward sloping: short < long *)
  | Flat            (** Minimal slope *)
  | Inverted        (** Downward sloping: short > long *)
  | DeeplyInverted  (** Severely inverted *)

(** Inflation regime *)
type inflation_regime =
  | Deflation       (** < 0% *)
  | LowInflation    (** 0-1.5% *)
  | TargetInflation (** 1.5-2.5% *)
  | HighInflation   (** 2.5-4% *)
  | VeryHigh        (** > 4% *)

(** Labor market state *)
type labor_state =
  | VeryTight       (** Unemployment < 3.5% *)
  | Tight           (** 3.5-4% *)
  | Healthy         (** 4-5% *)
  | Softening       (** 5-6% *)
  | Weak            (** > 6% *)

(** Risk sentiment *)
type risk_sentiment =
  | RiskOn          (** Low VIX, tight spreads, complacency *)
  | Neutral         (** Normal conditions *)
  | Cautious        (** Elevated uncertainty *)
  | RiskOff         (** High fear, wide spreads *)

(** Fed policy stance *)
type fed_stance =
  | VeryDovish      (** Aggressive easing *)
  | Dovish          (** Easing bias *)
  | NeutralFed      (** On hold *)
  | Hawkish         (** Tightening bias *)
  | VeryHawkish     (** Aggressive tightening *)

(** Interest rate data *)
type rate_data = {
  fed_funds: float option;
  treasury_3m: float option;
  treasury_2y: float option;
  treasury_10y: float option;
  spread_10y2y: float option;
  spread_10y3m: float option;
}

(** Inflation data *)
type inflation_data = {
  cpi_yoy: float option;
  core_cpi_yoy: float option;
  pce_yoy: float option;
  core_pce_yoy: float option;
  ppi_yoy: float option;
}

(** Employment data *)
type employment_data = {
  unemployment_rate: float option;
  nfp_change: float option;
  initial_claims: float option;
  continued_claims: float option;
  job_openings: float option;
}

(** Growth data *)
type growth_data = {
  gdp_growth: float option;
  industrial_production_yoy: float option;
  retail_sales_yoy: float option;
}

(** Market data *)
type market_data = {
  vix: float option;
  move_index: float option;
  dollar_index: float option;
  gold: float option;
  oil: float option;
  copper: float option;
  sp500_ytd: float option;
}

(** Consumer data *)
type consumer_data = {
  retail_sales_yoy: float option;
}

(** Housing data *)
type housing_data = {
  housing_starts: float option;
  building_permits: float option;
  existing_home_sales: float option;
  mortgage_rate: float option;
}

(** Complete macro snapshot *)
type macro_snapshot = {
  timestamp: string;
  rates: rate_data;
  inflation: inflation_data;
  employment: employment_data;
  growth: growth_data;
  market: market_data;
  consumer: consumer_data;
  housing: housing_data;
}

(** Classified macro environment *)
type macro_environment = {
  cycle_phase: cycle_phase;
  yield_curve: yield_curve_state;
  inflation_regime: inflation_regime;
  labor_state: labor_state;
  risk_sentiment: risk_sentiment;
  fed_stance: fed_stance;
  recession_probability: float;  (* 0-1 *)
  confidence: float;             (* 0-1 *)
}

(** Investment implications *)
type investment_implications = {
  equity_outlook: string;
  bond_outlook: string;
  sector_tilts: string list;
  risk_level: string;
  key_risks: string list;
}

let string_of_cycle_phase = function
  | EarlyCycle -> "Early Cycle (Recovery)"
  | MidCycle -> "Mid Cycle (Expansion)"
  | LateCycle -> "Late Cycle (Peak)"
  | Recession -> "Recession (Contraction)"

let string_of_yield_curve = function
  | Normal -> "Normal (Upward Sloping)"
  | Flat -> "Flat"
  | Inverted -> "Inverted"
  | DeeplyInverted -> "Deeply Inverted"

let string_of_inflation_regime = function
  | Deflation -> "Deflation"
  | LowInflation -> "Low Inflation"
  | TargetInflation -> "At Target"
  | HighInflation -> "Elevated"
  | VeryHigh -> "Very High"

let string_of_labor_state = function
  | VeryTight -> "Very Tight"
  | Tight -> "Tight"
  | Healthy -> "Healthy"
  | Softening -> "Softening"
  | Weak -> "Weak"

let string_of_risk_sentiment = function
  | RiskOn -> "Risk-On"
  | Neutral -> "Neutral"
  | Cautious -> "Cautious"
  | RiskOff -> "Risk-Off"

let string_of_fed_stance = function
  | VeryDovish -> "Very Dovish"
  | Dovish -> "Dovish"
  | NeutralFed -> "Neutral"
  | Hawkish -> "Hawkish"
  | VeryHawkish -> "Very Hawkish"

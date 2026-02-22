(** Macro Dashboard Types *)

type cycle_phase =
  | EarlyCycle
  | MidCycle
  | LateCycle
  | Recession

type yield_curve_state =
  | Normal
  | Flat
  | Inverted
  | DeeplyInverted

type inflation_regime =
  | Deflation
  | LowInflation
  | TargetInflation
  | HighInflation
  | VeryHigh

type labor_state =
  | VeryTight
  | Tight
  | Healthy
  | Softening
  | Weak

type risk_sentiment =
  | RiskOn
  | Neutral
  | Cautious
  | RiskOff

type fed_stance =
  | VeryDovish
  | Dovish
  | NeutralFed
  | Hawkish
  | VeryHawkish

type rate_data = {
  fed_funds: float option;
  treasury_3m: float option;
  treasury_2y: float option;
  treasury_10y: float option;
  spread_10y2y: float option;
  spread_10y3m: float option;
}

type inflation_data = {
  cpi_yoy: float option;
  core_cpi_yoy: float option;
  pce_yoy: float option;
  core_pce_yoy: float option;
  ppi_yoy: float option;
}

type employment_data = {
  unemployment_rate: float option;
  nfp_change: float option;
  initial_claims: float option;
  continued_claims: float option;
  job_openings: float option;
}

type growth_data = {
  gdp_growth: float option;
  industrial_production_yoy: float option;
  retail_sales_yoy: float option;
}

type market_data = {
  vix: float option;
  move_index: float option;
  dollar_index: float option;
  gold: float option;
  oil: float option;
  copper: float option;
  sp500_ytd: float option;
}

type consumer_data = {
  retail_sales_yoy: float option;
}

type housing_data = {
  housing_starts: float option;
  building_permits: float option;
  existing_home_sales: float option;
  mortgage_rate: float option;
}

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

type macro_environment = {
  cycle_phase: cycle_phase;
  yield_curve: yield_curve_state;
  inflation_regime: inflation_regime;
  labor_state: labor_state;
  risk_sentiment: risk_sentiment;
  fed_stance: fed_stance;
  recession_probability: float;
  confidence: float;
}

type investment_implications = {
  equity_outlook: string;
  bond_outlook: string;
  sector_tilts: string list;
  risk_level: string;
  key_risks: string list;
}

val string_of_cycle_phase : cycle_phase -> string
val string_of_yield_curve : yield_curve_state -> string
val string_of_inflation_regime : inflation_regime -> string
val string_of_labor_state : labor_state -> string
val string_of_risk_sentiment : risk_sentiment -> string
val string_of_fed_stance : fed_stance -> string

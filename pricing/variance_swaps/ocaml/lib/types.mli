(* Interface for variance swaps types *)

type option_type = Call | Put [@@deriving show]

type variance_swap = {
  ticker : string;
  notional : float;
  strike_var : float;
  expiry : float;
  vega_notional : float;
  entry_date : float;
  entry_spot : float;
} [@@deriving show]

type volatility_swap = {
  ticker : string;
  notional : float;
  strike_vol : float;
  expiry : float;
  entry_date : float;
  entry_spot : float;
  convexity_adjustment : float;
} [@@deriving show]

type vrp_observation = {
  timestamp : float;
  ticker : string;
  horizon_days : int;
  implied_var : float;
  forecast_realized_var : float;
  vrp : float;
  vrp_percent : float;
} [@@deriving show]

type replication_leg = {
  option_type : option_type;
  strike : float;
  expiry : float;
  weight : float;
  price : float;
  delta : float;
  vega : float;
} [@@deriving show]

type replication_portfolio = {
  ticker : string;
  target_variance_notional : float;
  legs : replication_leg array;
  total_cost : float;
  total_vega : float;
  total_delta : float;
} [@@deriving show]

type vrp_signal_type =
  | ShortVariance of {
      reason : string;
      implied_var : float;
      forecast_var : float;
      vrp_pct : float;
    }
  | LongVariance of {
      reason : string;
      implied_var : float;
      forecast_var : float;
      vrp_pct : float;
    }
  | Neutral of { reason : string }
  [@@deriving show]

type vrp_trading_signal = {
  timestamp : float;
  ticker : string;
  signal_type : vrp_signal_type;
  confidence : float;
  position_size : float;
  expected_sharpe : float option;
} [@@deriving show]

type variance_strategy_pnl = {
  timestamp : float;
  position : variance_swap option;
  realized_var_to_date : float;
  mark_to_market_pnl : float;
  cumulative_pnl : float;
  sharpe_ratio : float option;
} [@@deriving show]

type greeks = {
  delta : float;
  gamma : float;
  vega : float;
  theta : float;
  rho : float;
} [@@deriving show]

type svi_params = {
  expiry : float;
  a : float;
  b : float;
  rho : float;
  m : float;
  sigma : float;
} [@@deriving show]

type vol_surface = SVI of svi_params array [@@deriving show]

type underlying_data = {
  ticker : string;
  spot_price : float;
  dividend_yield : float;
} [@@deriving show]

type variance_swap_config = {
  min_vrp_threshold : float;
  max_vrp_threshold : float;
  target_vega_notional : float;
  max_convexity_risk : float;
  replication_num_strikes : int;
  replication_strike_spacing : float;
  transaction_cost_bps : float;
  roll_days_before_expiry : int;
} [@@deriving show]

val default_config : variance_swap_config

(* Core types for variance/volatility swaps and variance risk premium *)

(* Option types - reused from previous models *)
type option_type = Call | Put [@@deriving show]

(* Variance swap specification *)
type variance_swap = {
  ticker : string;
  notional : float;              (* Variance notional *)
  strike_var : float;            (* Variance strike K_var *)
  expiry : float;                (* Time to maturity (years) *)
  vega_notional : float;         (* Vega notional = Notional / (2√K_var) *)
  entry_date : float;
  entry_spot : float;
} [@@deriving show]

(* Volatility swap specification *)
type volatility_swap = {
  ticker : string;
  notional : float;              (* Vol notional *)
  strike_vol : float;            (* Volatility strike K_vol *)
  expiry : float;
  entry_date : float;
  entry_spot : float;
  convexity_adjustment : float;  (* Correction from var swap *)
} [@@deriving show]

(* Variance risk premium observation *)
type vrp_observation = {
  timestamp : float;
  ticker : string;
  horizon_days : int;            (* 30d, 60d, 90d *)
  implied_var : float;           (* From options *)
  forecast_realized_var : float; (* From model *)
  vrp : float;                   (* IV - FRV *)
  vrp_percent : float;           (* VRP / IV * 100 *)
} [@@deriving show]

(* Replication portfolio leg *)
type replication_leg = {
  option_type : option_type;
  strike : float;
  expiry : float;
  weight : float;                (* Number of contracts *)
  price : float;
  delta : float;
  vega : float;
} [@@deriving show]

(* Replication portfolio *)
type replication_portfolio = {
  ticker : string;
  target_variance_notional : float;
  legs : replication_leg array;
  total_cost : float;
  total_vega : float;
  total_delta : float;
} [@@deriving show]

(* VRP trading signal types *)
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

(* VRP trading signal *)
type vrp_trading_signal = {
  timestamp : float;
  ticker : string;
  signal_type : vrp_signal_type;
  confidence : float;            (* 0-1 *)
  position_size : float;         (* Recommended notional *)
  expected_sharpe : float option;
} [@@deriving show]

(* Strategy performance *)
type variance_strategy_pnl = {
  timestamp : float;
  position : variance_swap option;
  realized_var_to_date : float;
  mark_to_market_pnl : float;
  cumulative_pnl : float;
  sharpe_ratio : float option;
} [@@deriving show]

(* Greeks - reused structure *)
type greeks = {
  delta : float;
  gamma : float;
  vega : float;
  theta : float;
  rho : float;
} [@@deriving show]

(* Vol surface types - simplified from options_hedging *)
type svi_params = {
  expiry : float;
  a : float;
  b : float;
  rho : float;
  m : float;
  sigma : float;
} [@@deriving show]

type vol_surface = SVI of svi_params array [@@deriving show]

(* Underlying data *)
type underlying_data = {
  ticker : string;
  spot_price : float;
  dividend_yield : float;
} [@@deriving show]

(* Configuration *)
type variance_swap_config = {
  min_vrp_threshold : float;     (* Min VRP to trigger short variance *)
  max_vrp_threshold : float;     (* Max VRP for mean reversion (go long) *)
  target_vega_notional : float;  (* Target vega exposure *)
  max_convexity_risk : float;    (* Max gamma-of-variance *)
  replication_num_strikes : int; (* Number of strikes in replication *)
  replication_strike_spacing : float;  (* Log-moneyness spacing *)
  transaction_cost_bps : float;  (* Transaction costs *)
  roll_days_before_expiry : int; (* When to roll positions *)
} [@@deriving show]

(* Default configuration *)
let default_config = {
  min_vrp_threshold = 2.0;       (* 2% VRP to go short *)
  max_vrp_threshold = -1.0;      (* -1% VRP to go long *)
  target_vega_notional = 100000.0;
  max_convexity_risk = 0.5;
  replication_num_strikes = 20;
  replication_strike_spacing = 0.05;  (* 5% log-moneyness *)
  transaction_cost_bps = 2.0;
  roll_days_before_expiry = 5;
}

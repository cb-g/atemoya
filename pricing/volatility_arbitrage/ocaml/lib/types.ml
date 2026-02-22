(* Core types for volatility arbitrage model *)

(* Option types - reused from options_hedging concept *)
type option_type = Call | Put [@@deriving show]

type exercise_style = European | American [@@deriving show]

(* Realized volatility estimators *)
type rv_estimator =
  | CloseToClose
  | Parkinson        (* High-low range *)
  | GarmanKlass      (* OHLC-based *)
  | RogersSatchell   (* Drift-independent *)
  | YangZhang        (* Combines all *)
  [@@deriving show]

(* OHLC bar *)
type ohlc_bar = {
  timestamp : float;      (* Unix time *)
  open_ : float;
  high : float;
  low : float;
  close : float;
  volume : float;
} [@@deriving show]

(* Realized volatility estimate *)
type realized_vol = {
  timestamp : float;
  estimator : rv_estimator;
  volatility : float;      (* Annualized *)
  window_days : int;
} [@@deriving show]

(* GARCH parameters *)
type garch_params = {
  omega : float;    (* Long-run variance *)
  alpha : float;    (* ARCH term coefficient *)
  beta : float;     (* GARCH term coefficient *)
} [@@deriving show]

(* Volatility forecast types *)
type vol_forecast_type =
  | GARCH of garch_params
  | EWMA of { lambda : float }
  | HAR of { beta_d : float; beta_w : float; beta_m : float }
  | Historical of { window : int }
  [@@deriving show]

(* Volatility forecast *)
type vol_forecast = {
  timestamp : float;
  forecast_type : vol_forecast_type;
  forecast_vol : float;
  confidence_interval : (float * float) option;  (* 95% CI *)
  horizon_days : int;
} [@@deriving show]

(* Implied volatility observation *)
type iv_observation = {
  timestamp : float;
  ticker : string;
  strike : float;
  expiry : float;
  option_type : option_type;
  implied_vol : float;
  bid : float;
  ask : float;
  mid_price : float;
} [@@deriving show]

(* ATM implied volatility *)
type atm_iv = {
  timestamp : float;
  ticker : string;
  expiry : float;
  atm_strike : float;
  atm_iv : float;
} [@@deriving show]

(* Arbitrage opportunity types *)
type arbitrage_type =
  | ButterflyViolation of {
      lower_strike : float;
      middle_strike : float;
      upper_strike : float;
      violation_amount : float;
    }
  | CalendarViolation of {
      strike : float;
      near_expiry : float;
      far_expiry : float;
      violation_amount : float;
    }
  | PutCallParity of {
      strike : float;
      expiry : float;
      violation_amount : float;
    }
  | VerticalSpread of {
      lower_strike : float;
      upper_strike : float;
      expiry : float;
      violation_amount : float;
    }
  [@@deriving show]

(* Arbitrage signal *)
type arbitrage_signal = {
  timestamp : float;
  ticker : string;
  arb_type : arbitrage_type;
  confidence : float;         (* 0-1 *)
  expected_profit : float;    (* After costs *)
} [@@deriving show]

(* Delta-neutral strategy types *)
type vol_strategy_type =
  | Straddle of {
      strike : float;
      direction : [ `Long | `Short ];
    }
  | Strangle of {
      put_strike : float;
      call_strike : float;
      direction : [ `Long | `Short ];
    }
  | Butterfly of {
      lower_strike : float;
      middle_strike : float;
      upper_strike : float;
      direction : [ `Long | `Short ];
    }
  | CalendarSpread of {
      strike : float;
      near_expiry : float;
      far_expiry : float;
      direction : [ `Long | `Short ];
    }
  | RatioSpread of {
      long_strike : float;
      short_strike : float;
      ratio : int;  (* e.g., 1:2 *)
      expiry : float;
    }
  [@@deriving show]

(* Greeks - matching options_hedging structure *)
type greeks = {
  delta : float;
  gamma : float;
  vega : float;
  theta : float;
  rho : float;
} [@@deriving show]

(* Volatility strategy *)
type vol_strategy = {
  strategy_type : vol_strategy_type;
  entry_date : float;
  expiry : float;
  spot_at_entry : float;
  implied_vol_at_entry : float;
  forecast_realized_vol : float;
  net_cost : float;
  target_vega : float;
  initial_delta : float;
  initial_greeks : greeks;
} [@@deriving show]

(* P&L attribution components *)
type pnl_attribution = {
  total_pnl : float;
  delta_pnl : float;
  gamma_pnl : float;
  vega_pnl : float;
  theta_pnl : float;
  transaction_costs : float;
} [@@deriving show]

(* Gamma scalping result *)
type gamma_scalping_result = {
  strategy : vol_strategy;
  paths : int;
  rebalance_frequency_minutes : int;
  pnl : pnl_attribution;
  avg_hedge_size : float;
  num_rebalances : int;
  sharpe_ratio : float option;
  win_rate : float;  (* Fraction of profitable paths *)
} [@@deriving show]

(* Dispersion trade *)
type dispersion_trade = {
  index_ticker : string;
  component_tickers : string array;
  index_weight : float;        (* Net index vega *)
  component_weights : float array;  (* Net component vegas *)
  implied_correlation : float;
  expected_pnl : float;
  confidence : float;
  timestamp : float;
} [@@deriving show]

(* Variance swap *)
type variance_swap = {
  ticker : string;
  notional : float;
  strike_var : float;          (* Variance strike *)
  expiry : float;
  vega_notional : float;       (* Vega per vol point *)
  entry_cost : float;
  entry_date : float;
} [@@deriving show]

(* Trading signal types *)
type signal_type =
  | ArbitrageSignal of arbitrage_signal
  | VolMispricingSignal of {
      ticker : string;
      implied_vol : float;
      forecast_vol : float;
      mispricing_pct : float;
      recommended_strategy : vol_strategy;
    }
  | DispersionSignal of dispersion_trade
  | VarianceSignal of variance_swap
  [@@deriving show]

(* Trading signal *)
type trading_signal = {
  timestamp : float;
  signal_type : signal_type;
  confidence : float;
  expected_sharpe : float option;
  max_position_size : float;
} [@@deriving show]

(* Underlying data - reused from options_hedging concept *)
type underlying_data = {
  ticker : string;
  spot_price : float;
  dividend_yield : float;
} [@@deriving show]

(* Vol surface - simplified for this module *)
type svi_params = {
  expiry : float;
  a : float;
  b : float;
  rho : float;
  m : float;
  sigma : float;
} [@@deriving show]

type sabr_params = {
  expiry : float;
  alpha : float;
  beta : float;
  rho : float;
  nu : float;
} [@@deriving show]

type vol_surface =
  | SVI of svi_params array
  | SABR of sabr_params array
  [@@deriving show]

(* Option specification *)
type option_spec = {
  ticker : string;
  option_type : option_type;
  strike : float;
  expiry : float;
  exercise_style : exercise_style;
} [@@deriving show]

(* Configuration for vol arbitrage model *)
type vol_arb_config = {
  min_arbitrage_profit : float;      (* Minimum profit to trigger signal *)
  min_vol_mispricing_pct : float;    (* Minimum IV-RV spread to trade *)
  max_transaction_cost_bps : float;  (* Max cost basis points *)
  target_sharpe_ratio : float;       (* Target Sharpe for strategies *)
  rebalance_threshold_delta : float; (* Delta threshold for rehedging *)
  garch_window_days : int;           (* GARCH estimation window *)
  rv_window_days : int;              (* Realized vol window *)
  mc_paths : int;                    (* Monte Carlo paths for gamma scalping *)
  mc_steps_per_day : int;            (* Intraday steps for MC *)
} [@@deriving show]

(* Default configuration *)
let default_config = {
  min_arbitrage_profit = 0.10;        (* $0.10 per contract *)
  min_vol_mispricing_pct = 5.0;       (* 5% IV-RV spread *)
  max_transaction_cost_bps = 5.0;     (* 5 bps *)
  target_sharpe_ratio = 1.0;          (* Sharpe >= 1.0 *)
  rebalance_threshold_delta = 0.10;   (* Rehedge when |delta| > 0.10 *)
  garch_window_days = 252;            (* 1 year *)
  rv_window_days = 21;                (* 21 trading days *)
  mc_paths = 1000;
  mc_steps_per_day = 78;              (* 5-minute bars in 6.5 hour trading day *)
}

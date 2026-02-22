(* Interface for volatility arbitrage types *)

type option_type = Call | Put [@@deriving show]

type exercise_style = European | American [@@deriving show]

type rv_estimator =
  | CloseToClose
  | Parkinson
  | GarmanKlass
  | RogersSatchell
  | YangZhang
  [@@deriving show]

type ohlc_bar = {
  timestamp : float;
  open_ : float;
  high : float;
  low : float;
  close : float;
  volume : float;
} [@@deriving show]

type realized_vol = {
  timestamp : float;
  estimator : rv_estimator;
  volatility : float;
  window_days : int;
} [@@deriving show]

type garch_params = {
  omega : float;
  alpha : float;
  beta : float;
} [@@deriving show]

type vol_forecast_type =
  | GARCH of garch_params
  | EWMA of { lambda : float }
  | HAR of { beta_d : float; beta_w : float; beta_m : float }
  | Historical of { window : int }
  [@@deriving show]

type vol_forecast = {
  timestamp : float;
  forecast_type : vol_forecast_type;
  forecast_vol : float;
  confidence_interval : (float * float) option;
  horizon_days : int;
} [@@deriving show]

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

type atm_iv = {
  timestamp : float;
  ticker : string;
  expiry : float;
  atm_strike : float;
  atm_iv : float;
} [@@deriving show]

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

type arbitrage_signal = {
  timestamp : float;
  ticker : string;
  arb_type : arbitrage_type;
  confidence : float;
  expected_profit : float;
} [@@deriving show]

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
      ratio : int;
      expiry : float;
    }
  [@@deriving show]

type greeks = {
  delta : float;
  gamma : float;
  vega : float;
  theta : float;
  rho : float;
} [@@deriving show]

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

type pnl_attribution = {
  total_pnl : float;
  delta_pnl : float;
  gamma_pnl : float;
  vega_pnl : float;
  theta_pnl : float;
  transaction_costs : float;
} [@@deriving show]

type gamma_scalping_result = {
  strategy : vol_strategy;
  paths : int;
  rebalance_frequency_minutes : int;
  pnl : pnl_attribution;
  avg_hedge_size : float;
  num_rebalances : int;
  sharpe_ratio : float option;
  win_rate : float;
} [@@deriving show]

type dispersion_trade = {
  index_ticker : string;
  component_tickers : string array;
  index_weight : float;
  component_weights : float array;
  implied_correlation : float;
  expected_pnl : float;
  confidence : float;
  timestamp : float;
} [@@deriving show]

type variance_swap = {
  ticker : string;
  notional : float;
  strike_var : float;
  expiry : float;
  vega_notional : float;
  entry_cost : float;
  entry_date : float;
} [@@deriving show]

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

type trading_signal = {
  timestamp : float;
  signal_type : signal_type;
  confidence : float;
  expected_sharpe : float option;
  max_position_size : float;
} [@@deriving show]

type underlying_data = {
  ticker : string;
  spot_price : float;
  dividend_yield : float;
} [@@deriving show]

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

type option_spec = {
  ticker : string;
  option_type : option_type;
  strike : float;
  expiry : float;
  exercise_style : exercise_style;
} [@@deriving show]

type vol_arb_config = {
  min_arbitrage_profit : float;
  min_vol_mispricing_pct : float;
  max_transaction_cost_bps : float;
  target_sharpe_ratio : float;
  rebalance_threshold_delta : float;
  garch_window_days : int;
  rv_window_days : int;
  mc_paths : int;
  mc_steps_per_day : int;
} [@@deriving show]

val default_config : vol_arb_config

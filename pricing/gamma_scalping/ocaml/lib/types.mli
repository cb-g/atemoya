(* Interface for gamma scalping types *)

type option_type =
  | Call
  | Put

type position_type =
  | Straddle of { strike : float }
  | Strangle of { call_strike : float; put_strike : float }
  | SingleOption of { option_type : option_type; strike : float }

type greeks = {
  delta : float;
  gamma : float;
  theta : float;
  vega : float;
  rho : float;
}

type hedging_strategy =
  | DeltaThreshold of { threshold : float }
  | TimeBased of { interval_minutes : int }
  | Hybrid of { threshold : float; interval_minutes : int }
  | VolAdaptive of { low_threshold : float; high_threshold : float }

type hedge_event = {
  timestamp : float;
  spot_price : float;
  delta_before : float;
  hedge_quantity : float;
  hedge_cost : float;
}

type pnl_snapshot = {
  timestamp : float;
  spot_price : float;
  option_value : float;
  option_pnl : float;
  gamma_pnl : float;
  theta_pnl : float;
  vega_pnl : float;
  hedge_pnl : float;
  transaction_costs : float;
  total_pnl : float;
  cumulative_pnl : float;
}

type simulation_config = {
  transaction_cost_bps : float;
  rate : float;
  dividend : float;
  contracts : int;
}

type simulation_result = {
  position : position_type;
  entry_premium : float;
  entry_iv : float;
  expiry : float;
  final_pnl : float;
  gamma_pnl_total : float;
  theta_pnl_total : float;
  vega_pnl_total : float;
  hedge_pnl_total : float;
  num_hedges : int;
  total_transaction_costs : float;
  sharpe_ratio : float option;
  max_drawdown : float;
  win_rate : float;
  avg_hedge_interval_minutes : float;
  hedge_log : hedge_event array;
  pnl_timeseries : pnl_snapshot array;
}

val default_config : simulation_config

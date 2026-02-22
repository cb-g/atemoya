(* Core types for gamma scalping *)

(* Option type *)
type option_type =
  | Call
  | Put

(* Position types for gamma scalping *)
type position_type =
  | Straddle of { strike : float }
  | Strangle of { call_strike : float; put_strike : float }
  | SingleOption of { option_type : option_type; strike : float }

(* Greeks *)
type greeks = {
  delta : float;
  gamma : float;
  theta : float;
  vega : float;
  rho : float;
}

(* Hedging strategies *)
type hedging_strategy =
  | DeltaThreshold of { threshold : float }
  | TimeBased of { interval_minutes : int }
  | Hybrid of { threshold : float; interval_minutes : int }
  | VolAdaptive of { low_threshold : float; high_threshold : float }

(* Individual hedge event *)
type hedge_event = {
  timestamp : float;
  spot_price : float;
  delta_before : float;
  hedge_quantity : float;        (* Negative = sell stock, Positive = buy stock *)
  hedge_cost : float;            (* Transaction cost *)
}

(* P&L snapshot at a point in time *)
type pnl_snapshot = {
  timestamp : float;
  spot_price : float;
  option_value : float;
  option_pnl : float;            (* Current option value - entry premium *)
  gamma_pnl : float;             (* Cumulative gamma P&L *)
  theta_pnl : float;             (* Cumulative theta decay *)
  vega_pnl : float;              (* Cumulative vega P&L *)
  hedge_pnl : float;             (* P&L from hedge trades *)
  transaction_costs : float;     (* Cumulative transaction costs *)
  total_pnl : float;             (* Net P&L *)
  cumulative_pnl : float;        (* Running total *)
}

(* Simulation configuration *)
type simulation_config = {
  transaction_cost_bps : float;  (* Transaction cost in basis points *)
  rate : float;                  (* Risk-free rate *)
  dividend : float;              (* Dividend yield *)
  contracts : int;               (* Number of option contracts *)
}

(* Simulation result *)
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
  win_rate : float;              (* % of profitable timesteps *)
  avg_hedge_interval_minutes : float;
  hedge_log : hedge_event array;
  pnl_timeseries : pnl_snapshot array;
}

(* Default configuration *)
let default_config = {
  transaction_cost_bps = 5.0;   (* 5 bps = 0.05% *)
  rate = 0.05;                  (* 5% risk-free rate *)
  dividend = 0.0;
  contracts = 1;
}

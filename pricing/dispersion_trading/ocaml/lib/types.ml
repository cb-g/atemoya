(* Types for dispersion trading *)

(* Option type *)
type option_type =
  | Call
  | Put

(* Option contract *)
type option_contract = {
  ticker: string;
  option_type: option_type;
  strike: float;
  expiry: float;  (* Days to expiry *)
  spot: float;
  implied_vol: float;
  price: float;
  delta: float;
  gamma: float;
  vega: float;
  theta: float;
}

(* Single-name position *)
type single_name = {
  ticker: string;
  weight: float;  (* Portfolio weight *)
  spot: float;
  option: option_contract;
  notional: float;
}

(* Index position *)
type index_position = {
  ticker: string;  (* e.g., "SPY" *)
  spot: float;
  option: option_contract;
  notional: float;
}

(* Dispersion position *)
type dispersion_type =
  | LongDispersion   (* Buy single-names, sell index *)
  | ShortDispersion  (* Sell single-names, buy index *)

type dispersion_position = {
  position_type: dispersion_type;
  index: index_position;
  single_names: single_name array;
  entry_date: float;
  expiry_date: float;
}

(* Correlation metrics *)
type correlation_metrics = {
  implied_correlation: float;  (* From vol surface *)
  realized_correlation: float; (* From price history *)
  avg_pairwise_correlation: float;
  correlation_matrix: float array array;
}

(* Dispersion metrics *)
type dispersion_metrics = {
  index_iv: float;
  weighted_avg_iv: float;
  dispersion_level: float;  (* weighted_avg_iv - index_iv *)
  dispersion_zscore: float;
  implied_corr: float;
  signal: string;  (* "LONG", "SHORT", "NEUTRAL" *)
}

(* P&L attribution *)
type pnl_attribution = {
  total_pnl: float;
  vol_pnl: float;       (* Vega * Δσ *)
  gamma_pnl: float;     (* 0.5 * Γ * ΔS² *)
  theta_pnl: float;     (* θ * Δt *)
  correlation_pnl: float; (* Residual *)
}

(* Backtest snapshot *)
type backtest_snapshot = {
  timestamp: float;
  index_spot: float;
  index_iv: float;
  weighted_avg_iv: float;
  dispersion_level: float;
  implied_corr: float;
  realized_corr: float;
  position_pnl: float;
  cumulative_pnl: float;
  delta: float;
  gamma: float;
  vega: float;
}

(* Backtest result *)
type backtest_result = {
  total_pnl: float;
  num_trades: int;
  win_rate: float;
  sharpe_ratio: float option;
  max_drawdown: float;
  avg_dispersion: float;
  avg_implied_corr: float;
  avg_realized_corr: float;
  attribution: pnl_attribution;
}

(* Helper functions *)

let option_type_to_string = function
  | Call -> "Call"
  | Put -> "Put"

let option_type_of_string = function
  | "Call" | "call" | "C" -> Call
  | "Put" | "put" | "P" -> Put
  | s -> failwith (Printf.sprintf "Unknown option type: %s" s)

let dispersion_type_to_string = function
  | LongDispersion -> "Long"
  | ShortDispersion -> "Short"

(* Types for pairs trading *)

(* Trading pair *)
type pair = {
  ticker1: string;
  ticker2: string;
  prices1: float array;
  prices2: float array;
}

(* Cointegration test result *)
type cointegration_result = {
  is_cointegrated: bool;
  hedge_ratio: float;        (* β from regression Y = α + βX + ε *)
  alpha: float;              (* Intercept *)
  adf_statistic: float;      (* ADF statistic for Engle-Granger, trace statistic for Johansen *)
  critical_value: float;     (* 5% critical value *)
  p_value: float option;     (* P-value if available *)
  method_name: string;       (* "Engle-Granger (OLS)", "Engle-Granger (TLS)", "Johansen" *)
}

(* Half-life monitor *)
type half_life_monitor = {
  baseline_half_life: float;  (* Full-sample half-life *)
  current_half_life: float;   (* Rolling window half-life *)
  ratio: float;               (* current / baseline, >2.0 is warning *)
  is_expanding: bool;         (* ratio > 2.0: mean reversion weakening *)
}

(* Spread statistics *)
type spread_stats = {
  mean: float;
  std: float;
  half_life: float;          (* Mean reversion half-life in days *)
  current_zscore: float;
}

(* Trading signal *)
type signal_type =
  | Long    (* Long spread: buy Y, sell X *)
  | Short   (* Short spread: sell Y, buy X *)
  | Neutral
  | Exit

type trading_signal = {
  timestamp: float;
  signal: signal_type;
  zscore: float;
  spread_value: float;
}

(* Position *)
type position = {
  entry_time: float;
  entry_zscore: float;
  entry_spread: float;
  position_type: signal_type;  (* Long or Short *)
  shares_y: float;             (* Shares of Y *)
  shares_x: float;             (* Shares of X (negative for short) *)
}

(* Trade *)
type trade = {
  entry_time: float;
  exit_time: float;
  entry_zscore: float;
  exit_zscore: float;
  pnl: float;
  pnl_pct: float;
  holding_period: float;       (* Days *)
  trade_type: signal_type;
}

(* Backtest snapshot *)
type backtest_snapshot = {
  timestamp: float;
  price1: float;
  price2: float;
  spread: float;
  zscore: float;
  position: position option;
  cumulative_pnl: float;
  signal: signal_type;
}

(* Backtest result *)
type backtest_result = {
  total_pnl: float;
  num_trades: int;
  num_winners: int;
  num_losers: int;
  win_rate: float;
  avg_pnl: float;
  avg_winner: float;
  avg_loser: float;
  sharpe_ratio: float option;
  max_drawdown: float;
  profit_factor: float;       (* Gross profit / Gross loss *)
  trades: trade array;
}

(* Helper functions *)

let signal_to_string = function
  | Long -> "LONG"
  | Short -> "SHORT"
  | Neutral -> "NEUTRAL"
  | Exit -> "EXIT"

let signal_of_string = function
  | "LONG" | "Long" | "long" -> Long
  | "SHORT" | "Short" | "short" -> Short
  | "EXIT" | "Exit" | "exit" -> Exit
  | _ -> Neutral

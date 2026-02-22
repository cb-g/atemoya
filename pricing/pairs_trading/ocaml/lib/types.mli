(* Interface for pairs trading types *)

type pair = {
  ticker1: string;
  ticker2: string;
  prices1: float array;
  prices2: float array;
}

type cointegration_result = {
  is_cointegrated: bool;
  hedge_ratio: float;
  alpha: float;
  adf_statistic: float;
  critical_value: float;
  p_value: float option;
  method_name: string;
}

type half_life_monitor = {
  baseline_half_life: float;
  current_half_life: float;
  ratio: float;
  is_expanding: bool;
}

type spread_stats = {
  mean: float;
  std: float;
  half_life: float;
  current_zscore: float;
}

type signal_type =
  | Long
  | Short
  | Neutral
  | Exit

type trading_signal = {
  timestamp: float;
  signal: signal_type;
  zscore: float;
  spread_value: float;
}

type position = {
  entry_time: float;
  entry_zscore: float;
  entry_spread: float;
  position_type: signal_type;
  shares_y: float;
  shares_x: float;
}

type trade = {
  entry_time: float;
  exit_time: float;
  entry_zscore: float;
  exit_zscore: float;
  pnl: float;
  pnl_pct: float;
  holding_period: float;
  trade_type: signal_type;
}

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
  profit_factor: float;
  trades: trade array;
}

val signal_to_string : signal_type -> string
val signal_of_string : string -> signal_type

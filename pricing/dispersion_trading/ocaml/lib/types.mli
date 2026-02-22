(* Interface for dispersion trading types *)

type option_type =
  | Call
  | Put

type option_contract = {
  ticker: string;
  option_type: option_type;
  strike: float;
  expiry: float;
  spot: float;
  implied_vol: float;
  price: float;
  delta: float;
  gamma: float;
  vega: float;
  theta: float;
}

type single_name = {
  ticker: string;
  weight: float;
  spot: float;
  option: option_contract;
  notional: float;
}

type index_position = {
  ticker: string;
  spot: float;
  option: option_contract;
  notional: float;
}

type dispersion_type =
  | LongDispersion
  | ShortDispersion

type dispersion_position = {
  position_type: dispersion_type;
  index: index_position;
  single_names: single_name array;
  entry_date: float;
  expiry_date: float;
}

type correlation_metrics = {
  implied_correlation: float;
  realized_correlation: float;
  avg_pairwise_correlation: float;
  correlation_matrix: float array array;
}

type dispersion_metrics = {
  index_iv: float;
  weighted_avg_iv: float;
  dispersion_level: float;
  dispersion_zscore: float;
  implied_corr: float;
  signal: string;
}

type pnl_attribution = {
  total_pnl: float;
  vol_pnl: float;
  gamma_pnl: float;
  theta_pnl: float;
  correlation_pnl: float;
}

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

val option_type_to_string : option_type -> string
val option_type_of_string : string -> option_type
val dispersion_type_to_string : dispersion_type -> string

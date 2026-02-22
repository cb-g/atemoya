(** Types for liquidity analysis *)

type ohlcv = {
  dates : string array;
  open_prices : float array;
  high : float array;
  low : float array;
  close : float array;
  volume : float array;
}

type ticker_data = {
  ticker : string;
  shares_outstanding : float;
  market_cap : float;
  ohlcv : ohlcv;
}

type liquidity_metrics = {
  amihud_ratio : float;
  turnover_ratio : float;
  relative_volume : float;
  volume_volatility : float;
  spread_proxy : float;
  liquidity_score : float;
  liquidity_tier : string;
}

type signal_metrics = {
  obv_strength : float;
  obv_signal : string;
  volume_surge : bool;
  surge_magnitude : float;
  volume_trend : string;
  volume_trend_slope : float;
  vp_correlation : float;
  vp_confirmation : string;
  smart_money_flow : float;
  smart_money_signal : string;
  signal_score : float;
  composite_signal : string;
}

type analysis_result = {
  ticker : string;
  price : float;
  market_cap : float;
  avg_volume : float;
  avg_dollar_volume : float;
  liquidity : liquidity_metrics;
  signals : signal_metrics;
}

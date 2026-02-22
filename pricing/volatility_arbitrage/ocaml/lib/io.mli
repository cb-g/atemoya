(* I/O interface for volatility arbitrage *)

open Types

(** Read OHLC data from CSV *)
val read_ohlc_csv :
  filename:string ->
  ohlc_bar array

(** Read implied volatility observations from CSV *)
val read_iv_observations :
  filename:string ->
  iv_observation array

(** Read underlying data from CSV *)
val read_underlying_data :
  filename:string ->
  underlying_data

(** Read volatility surface from JSON *)
val read_vol_surface :
  filename:string ->
  vol_surface

(** Read realized volatility from CSV *)
val read_realized_vol_csv :
  filename:string ->
  realized_vol array

(** Write realized volatility to CSV *)
val write_realized_vol_csv :
  filename:string ->
  realized_vols:realized_vol array ->
  unit

(** Write arbitrage signals to CSV *)
val write_arbitrage_signals_csv :
  filename:string ->
  signals:arbitrage_signal array ->
  unit

(** Write trading signals to CSV *)
val write_trading_signals_csv :
  filename:string ->
  signals:trading_signal array ->
  unit

(** Write vol forecast to JSON *)
val write_vol_forecast_json :
  filename:string ->
  forecast:vol_forecast ->
  unit

(** Write configuration to JSON *)
val write_config_json :
  filename:string ->
  config:vol_arb_config ->
  unit

(** Read configuration from JSON *)
val read_config_json :
  filename:string ->
  vol_arb_config

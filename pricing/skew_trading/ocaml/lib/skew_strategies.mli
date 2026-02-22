(* Interface for skew trading strategies *)

open Types

(** Build risk reversal position
    Long call + Short put (or vice versa)

    Direction:
    - `Long: Long skew (buy call, sell put) - profit if skew normalizes upward
    - `Short: Short skew (sell call, buy put) - profit if skew mean-reverts down
*)
val build_risk_reversal :
  vol_surface ->
  underlying_data ->
  rate:float ->
  expiry:float ->
  delta_target:float ->          (* e.g., 0.25 for 25-delta RR *)
  direction:[`Long | `Short] ->
  notional:float ->
  skew_position

(** Build butterfly spread
    Buy OTM put + Sell 2 ATM + Buy OTM call
    Profits from volatility smile flattening
*)
val build_butterfly :
  vol_surface ->
  underlying_data ->
  rate:float ->
  expiry:float ->
  strikes:(float * float * float) ->  (* (low, mid, high) *)
  notional:float ->
  skew_position

(** Build ratio spread
    Buy N options at one strike, sell M at another
    Exploits relative value between strikes
*)
val build_ratio_spread :
  vol_surface ->
  underlying_data ->
  rate:float ->
  expiry:float ->
  option_type:option_type ->
  strikes:(float * float) ->     (* (long_strike, short_strike) *)
  ratio:int ->                   (* N:M ratio *)
  notional:float ->
  skew_position

(** Build calendar spread on skew
    Long near-term + Short far-term (or vice versa)
*)
val build_calendar_spread :
  vol_surface ->
  underlying_data ->
  rate:float ->
  expiries:(float * float) ->    (* (near, far) *)
  strike:float ->
  option_type:option_type ->
  notional:float ->
  skew_position

(** Compute position Greeks *)
val position_greeks :
  skew_position ->
  current_spot:float ->
  vol_surface:vol_surface ->
  rate:float ->
  greeks

(** Compute mark-to-market P&L *)
val position_pnl :
  skew_position ->
  current_spot:float ->
  current_vol_surface:vol_surface ->
  rate:float ->
  float

(** Delta-hedge a position by adding stock/futures *)
val delta_hedge :
  skew_position ->
  current_spot:float ->
  vol_surface:vol_surface ->
  rate:float ->
  skew_position

(** Check if position breaches risk limits *)
val check_risk_limits :
  skew_position ->
  config:skew_config ->
  bool  (* True if within limits *)

(* Interface for skew trading types *)

type option_type = Call | Put [@@deriving show]

(* Skew metrics *)
type skew_metric =
  | RiskReversal25 of { value : float; timestamp : float }
  | Butterfly25 of { value : float; timestamp : float }
  | SkewSlope of { value : float; timestamp : float }
  | PutCallRatio of { value : float; timestamp : float }
  | SkewIndex of { value : float; components : (string * float) list }
  [@@deriving show]

(* Skew observation (time series point) *)
type skew_observation = {
  timestamp : float;
  ticker : string;
  expiry : float;
  rr25 : float;                 (* Risk reversal *)
  bf25 : float;                 (* Butterfly *)
  skew_slope : float;           (* Linear slope *)
  atm_vol : float;              (* ATM IV *)
  put_25d_vol : float;          (* 25-delta put IV *)
  call_25d_vol : float;         (* 25-delta call IV *)
  put_25d_strike : float;       (* Strike for 25-delta put *)
  call_25d_strike : float;      (* Strike for 25-delta call *)
} [@@deriving show]

(* Skew trading strategy types *)
type strategy_type =
  | RiskReversal of {
      buy_strike : float;       (* Call strike *)
      sell_strike : float;      (* Put strike *)
      ratio : float;            (* Notional ratio *)
    }
  | Butterfly of {
      low_strike : float;
      mid_strike : float;
      high_strike : float;
    }
  | RatioSpread of {
      long_strike : float;
      short_strike : float;
      ratio : int;              (* N:M ratio *)
    }
  | CalendarSpread of {
      near_expiry : float;
      far_expiry : float;
      strike : float;
      option_type : option_type;
    }
  [@@deriving show]

(* Option leg in a strategy *)
type option_leg = {
  option_type : option_type;
  strike : float;
  expiry : float;
  quantity : float;             (* Positive = long, negative = short *)
  entry_price : float;
  delta : float;
  vega : float;
  gamma : float;
} [@@deriving show]

(* Skew trading position *)
type skew_position = {
  ticker : string;
  strategy_type : strategy_type;
  legs : option_leg array;
  entry_date : float;
  entry_spot : float;
  total_cost : float;
  total_delta : float;
  total_vega : float;
  total_gamma : float;
  target_pnl : float option;    (* Profit target *)
  stop_loss : float option;     (* Stop loss level *)
} [@@deriving show]

(* Greeks *)
type greeks = {
  delta : float;
  gamma : float;
  vega : float;
  theta : float;
  rho : float;
} [@@deriving show]

(* Skew trading signal *)
type signal_type =
  | LongSkew of {
      reason : string;
      current_rr25 : float;
      historical_mean : float;
      z_score : float;
    }
  | ShortSkew of {
      reason : string;
      current_rr25 : float;
      historical_mean : float;
      z_score : float;
    }
  | Neutral of { reason : string }
  [@@deriving show]

type skew_signal = {
  timestamp : float;
  ticker : string;
  signal_type : signal_type;
  confidence : float;           (* 0-1 *)
  recommended_strategy : strategy_type option;
  position_size : float;
} [@@deriving show]

(* Strategy P&L *)
type strategy_pnl = {
  timestamp : float;
  position : skew_position option;
  mark_to_market : float;
  realized_pnl : float;
  cumulative_pnl : float;
  sharpe_ratio : float option;
  max_drawdown : float option;
  sortino_ratio : float option;
  return_skewness : float option;
} [@@deriving show]

(* Vol surface types *)
type svi_params = {
  expiry : float;
  a : float;
  b : float;
  rho : float;
  m : float;
  sigma : float;
} [@@deriving show]

type vol_surface = SVI of svi_params array [@@deriving show]

(* Underlying data *)
type underlying_data = {
  ticker : string;
  spot_price : float;
  dividend_yield : float;
} [@@deriving show]

(* Configuration *)
type skew_config = {
  rr25_mean_reversion_threshold : float;  (* Z-score threshold *)
  min_confidence : float;                  (* Min confidence to trade *)
  target_vega_notional : float;            (* Target vega exposure *)
  max_gamma_risk : float;                  (* Max gamma exposure *)
  transaction_cost_bps : float;            (* Transaction costs *)
  delta_hedge : bool;                      (* Delta-hedge positions? *)
  lookback_days : int;                     (* Historical window for stats *)
} [@@deriving show]

val default_config : skew_config

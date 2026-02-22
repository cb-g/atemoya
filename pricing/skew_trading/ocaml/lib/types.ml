(* Core types for skew trading *)

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
  rr25 : float;                 (* Risk reversal: IV(call) - IV(put) *)
  bf25 : float;                 (* Butterfly: (IV(call) + IV(put))/2 - IV(ATM) *)
  skew_slope : float;           (* Linear slope across strikes *)
  atm_vol : float;              (* ATM implied volatility *)
  put_25d_vol : float;          (* 25-delta put IV *)
  call_25d_vol : float;         (* 25-delta call IV *)
  put_25d_strike : float;       (* Strike for 25-delta put *)
  call_25d_strike : float;      (* Strike for 25-delta call *)
} [@@deriving show]

(* Skew trading strategy types *)
type strategy_type =
  | RiskReversal of {
      buy_strike : float;       (* Call strike to buy *)
      sell_strike : float;      (* Put strike to sell *)
      ratio : float;            (* Notional ratio *)
    }
  | Butterfly of {
      low_strike : float;       (* OTM put *)
      mid_strike : float;       (* ATM *)
      high_strike : float;      (* OTM call *)
    }
  | RatioSpread of {
      long_strike : float;      (* Strike to buy *)
      short_strike : float;     (* Strike to sell *)
      ratio : int;              (* N:M ratio (e.g., 2:1) *)
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

(* Vol surface types (reused from variance swaps) *)
type svi_params = {
  expiry : float;
  a : float;              (* Vertical translation *)
  b : float;              (* Slope *)
  rho : float;            (* Rotation [-1, 1] *)
  m : float;              (* Horizontal translation *)
  sigma : float;          (* Curvature *)
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
  rr25_mean_reversion_threshold : float;  (* Z-score threshold for mean reversion *)
  min_confidence : float;                  (* Minimum confidence to trade *)
  target_vega_notional : float;            (* Target vega exposure *)
  max_gamma_risk : float;                  (* Maximum gamma exposure *)
  transaction_cost_bps : float;            (* Transaction costs in bps *)
  delta_hedge : bool;                      (* Whether to delta-hedge positions *)
  lookback_days : int;                     (* Historical window for statistics *)
} [@@deriving show]

(* Default configuration *)
let default_config = {
  rr25_mean_reversion_threshold = 2.0;    (* 2 standard deviations *)
  min_confidence = 0.6;                   (* 60% minimum confidence *)
  target_vega_notional = 50000.0;         (* $50k vega notional *)
  max_gamma_risk = 1000.0;                (* Max gamma *)
  transaction_cost_bps = 5.0;             (* 5 bps transaction costs *)
  delta_hedge = true;                     (* Delta-hedge by default *)
  lookback_days = 252;                    (* 1 year lookback *)
}

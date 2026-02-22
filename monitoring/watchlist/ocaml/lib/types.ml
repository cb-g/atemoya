(** Personal Portfolio Tracker Types *)

(** Position type *)
type position_type =
  | Long
  | Short
  | Watching

(** A weighted thesis argument *)
type thesis_arg = {
  arg : string;
  weight : int;  (* 1-10 scale *)
}

(** Price levels for alerts *)
type price_levels = {
  buy_target : float option;
  sell_target : float option;
  stop_loss : float option;
}

(** Position details *)
type position_info = {
  pos_type : position_type;
  shares : float;
  avg_cost : float;
}

(** A portfolio position with thesis *)
type portfolio_position = {
  ticker : string;
  name : string;
  position : position_info;
  levels : price_levels;
  bull : thesis_arg list;
  bear : thesis_arg list;
  catalysts : string list;
  notes : string;
}

(** Current market data for a position *)
type market_data = {
  current_price : float;
  prev_close : float;
  change_1d_pct : float;
  change_5d_pct : float;
  high_52w : float;
  low_52w : float;
  fetch_time : string;
}

(** Thesis score calculation *)
type thesis_score = {
  bull_score : int;
  bear_score : int;
  net_score : int;
  conviction : string;  (* "strong bull", "slight bull", "neutral", etc. *)
}

(** Price alert types *)
type price_alert =
  | HitBuyTarget of float * float    (* current, target *)
  | HitSellTarget of float * float
  | HitStopLoss of float * float
  | NearBuyTarget of float * float   (* within 5% *)
  | NearStopLoss of float * float
  | AboveCostBasis of float * float * float  (* current, cost, pct gain *)
  | BelowCostBasis of float * float * float  (* current, cost, pct loss *)

(** Alert priority *)
type priority =
  | Urgent    (* Stop loss hit, major move *)
  | High      (* Target hit *)
  | Normal    (* Near levels *)
  | Info      (* Status update *)

(** Triggered alert *)
type triggered_alert = {
  ticker : string;
  alert : price_alert;
  priority : priority;
  message : string;
}

(** Analysis result for a single position *)
type position_analysis = {
  position : portfolio_position;
  market : market_data option;
  thesis : thesis_score;
  pnl_pct : float option;
  pnl_abs : float option;
  alerts : triggered_alert list;
}

(** Complete portfolio analysis *)
type portfolio_analysis = {
  run_time : string;
  positions : position_analysis list;
  total_value : float option;
  total_cost : float option;
  total_pnl_pct : float option;
  all_alerts : triggered_alert list;
}

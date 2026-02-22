(** Forward Factor Strategy Types *)

(** Option expiration data *)
type expiration_data = {
  ticker: string;
  expiration: string;
  dte: int;                    (* Days to expiration *)
  atm_iv: float;               (* ATM implied volatility (annualized) *)
  atm_strike: float;
  atm_call_price: float;
  atm_put_price: float;
  delta_35_call_strike: float;
  delta_35_call_price: float;
  delta_35_put_strike: float;
  delta_35_put_price: float;
}

(** Forward volatility calculation *)
type forward_vol = {
  ticker: string;
  front_exp: string;
  back_exp: string;
  front_dte: int;
  back_dte: int;

  (* Input IVs *)
  front_iv: float;             (* σ1 - front period annualized IV *)
  back_iv: float;              (* σ2 - back period annualized IV *)

  (* Calculated forward metrics *)
  forward_variance: float;     (* Annualized forward variance *)
  forward_vol: float;          (* Annualized forward volatility *)
  forward_factor: float;       (* FF = (Front IV - Forward IV) / Forward IV *)
}

(** Calendar spread structure *)
type calendar_spread = {
  ticker: string;
  spread_type: string;         (* "atm_call" or "double_calendar" *)

  (* Front leg (sell) *)
  front_exp: string;
  front_dte: int;
  front_strikes: float list;   (* ATM for single, [call, put] for double *)
  front_prices: float list;

  (* Back leg (buy) *)
  back_exp: string;
  back_dte: int;
  back_strikes: float list;
  back_prices: float list;

  (* Economics *)
  net_debit: float;            (* Total cost *)
  max_profit: float;           (* Theoretical max profit *)
  max_loss: float;             (* = net_debit *)

  (* Forward metrics *)
  forward_vol: forward_vol;
}

(** Trade recommendation *)
type recommendation = {
  ticker: string;
  timestamp: string;

  (* Calendar spread *)
  spread: calendar_spread;

  (* Signal strength *)
  forward_factor: float;
  passes_filter: bool;         (* FF ≥ 0.20 *)

  (* Sizing *)
  kelly_fraction: float;
  suggested_size: float;       (* As % of portfolio, typically 2-8% *)

  (* Risk info *)
  max_loss: float;
  expected_return: float;      (* From backtest stats by FF bucket *)

  recommendation: string;      (* "Strong Buy", "Buy", "Pass" *)
  notes: string;
}

(** Default thresholds from backtest *)
let default_ff_threshold = 0.20    (* FF ≥ 0.20 for entry *)
let default_position_size = 0.04   (* 4% of portfolio *)
let min_position_size = 0.02       (* 2% min *)
let max_position_size = 0.08       (* 8% max *)

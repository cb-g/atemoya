(* Options Hedging - Core Type Definitions *)

(* Option specification *)
type option_type = Call | Put [@@deriving show]

type exercise_style = European | American [@@deriving show]

type option_spec = {
  ticker : string;
  option_type : option_type;
  strike : float;
  expiry : float;  (* Time to expiry in years *)
  exercise_style : exercise_style;
} [@@deriving show]

(* Market data *)
type underlying_data = {
  ticker : string;
  spot_price : float;
  dividend_yield : float;  (* Continuous dividend yield *)
} [@@deriving show]

(* Volatility surface point *)
type vol_point = {
  strike : float;
  expiry : float;
  implied_vol : float;
  bid : float option;
  ask : float option;
  market_price : float option;
} [@@deriving show]

(* SVI parameters (per expiry) *)
type svi_params = {
  expiry : float;
  a : float;      (* Vertical translation *)
  b : float;      (* Slope *)
  rho : float;    (* Rotation [-1, 1] *)
  m : float;      (* Horizontal translation *)
  sigma : float;  (* Vol of vol *)
} [@@deriving show]

(* SABR parameters (per expiry) *)
type sabr_params = {
  expiry : float;
  alpha : float;  (* Initial vol *)
  beta : float;   (* CEV exponent [0, 1] *)
  rho : float;    (* Correlation *)
  nu : float;     (* Vol of vol *)
} [@@deriving show]

type vol_surface =
  | SVI of svi_params array
  | SABR of sabr_params array
[@@deriving show]

(* Greeks *)
type greeks = {
  delta : float;
  gamma : float;
  vega : float;
  theta : float;
  rho : float;
} [@@deriving show]

(* Hedge strategy *)
type strategy_type =
  | ProtectivePut of { put_strike : float }
  | Collar of { put_strike : float; call_strike : float }
  | VerticalSpread of { long_strike : float; short_strike : float }
  | CoveredCall of { call_strike : float }
[@@deriving show]

type hedge_strategy = {
  strategy_type : strategy_type;
  expiry : float;
  contracts : int;           (* Number of contracts *)
  cost : float;              (* Total cost *)
  greeks : greeks;           (* Portfolio Greeks after hedge *)
  protection_level : float;  (* Min portfolio value in worst case *)
} [@@deriving show]

(* Pareto frontier point *)
type pareto_point = {
  cost : float;
  protection_level : float;
  strategy : hedge_strategy;
} [@@deriving show]

(* Optimization result *)
type optimization_result = {
  pareto_frontier : pareto_point array;
  recommended_strategy : hedge_strategy option;  (* Based on user preference *)
} [@@deriving show]

(* Helper functions for string conversion *)
let option_type_to_string = function
  | Call -> "call"
  | Put -> "put"

let option_type_of_string = function
  | "call" | "Call" | "CALL" -> Call
  | "put" | "Put" | "PUT" -> Put
  | s -> failwith (Printf.sprintf "Invalid option type: %s" s)

let exercise_style_to_string = function
  | European -> "european"
  | American -> "american"

let exercise_style_of_string = function
  | "european" | "European" | "EUROPEAN" -> European
  | "american" | "American" | "AMERICAN" -> American
  | s -> failwith (Printf.sprintf "Invalid exercise style: %s" s)

let strategy_name = function
  | ProtectivePut _ -> "Protective Put"
  | Collar _ -> "Collar"
  | VerticalSpread _ -> "Vertical Spread"
  | CoveredCall _ -> "Covered Call"

(* Zero Greeks *)
let zero_greeks = {
  delta = 0.0;
  gamma = 0.0;
  vega = 0.0;
  theta = 0.0;
  rho = 0.0;
}

(* Add Greeks *)
let add_greeks g1 g2 = {
  delta = g1.delta +. g2.delta;
  gamma = g1.gamma +. g2.gamma;
  vega = g1.vega +. g2.vega;
  theta = g1.theta +. g2.theta;
  rho = g1.rho +. g2.rho;
}

(* Scale Greeks *)
let scale_greeks g scale = {
  delta = g.delta *. scale;
  gamma = g.gamma *. scale;
  vega = g.vega *. scale;
  theta = g.theta *. scale;
  rho = g.rho *. scale;
}

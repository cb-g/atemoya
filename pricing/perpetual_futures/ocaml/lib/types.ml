(** Types for perpetual futures pricing.

    Based on Ackerer, Hugonnier, Jermann (2025) "Perpetual Futures Pricing"
    Mathematical Finance.
*)

(** Contract type for perpetual futures *)
type contract_type =
  | Linear   (** Standard perpetual, margined in quote currency *)
  | Inverse  (** Inverse perpetual, margined in base currency *)
  | Quanto   (** Quanto perpetual, margined in third currency *)

(** Currency pair specification *)
type currency_pair = {
  base : string;      (** Base currency (e.g., BTC) *)
  quote : string;     (** Quote currency (e.g., USD) *)
  terciary : string option;  (** Third currency for quanto (e.g., ETH) *)
}

(** Interest rates for the two (or three) currencies *)
type interest_rates = {
  r_a : float;  (** Interest rate in quote currency *)
  r_b : float;  (** Interest rate in base currency *)
  r_c : float option;  (** Interest rate in terciary currency (quanto only) *)
}

(** Funding parameters *)
type funding_params = {
  kappa : float;  (** Premium rate (anchoring intensity), kappa > 0 *)
  iota : float;   (** Interest factor *)
}

(** Volatility parameters for Black-Scholes models *)
type volatility_params = {
  sigma_x : float;  (** Volatility of b/a exchange rate *)
  sigma_z : float option;  (** Volatility of c/a exchange rate (quanto) *)
  rho_xz : float option;   (** Correlation between x and z (quanto) *)
}

(** Perpetual futures contract specification *)
type perpetual_contract = {
  contract_type : contract_type;
  pair : currency_pair;
  rates : interest_rates;
  funding : funding_params;
  volatility : volatility_params option;
}

(** Pricing result *)
type pricing_result = {
  spot_price : float;           (** Current spot price x_t *)
  futures_price : float;        (** Perpetual futures price f_t *)
  basis : float;                (** f_t - x_t *)
  basis_pct : float;            (** (f_t - x_t) / x_t * 100 *)
  fair_funding_rate : float;    (** Annualized funding rate *)
  perfect_iota : float;         (** Interest factor for f = x *)
}

(** Everlasting option type *)
type option_type = Call | Put

(** Everlasting option specification *)
type everlasting_option = {
  opt_type : option_type;
  strike : float;
  kappa : float;      (** Premium rate *)
  r_a : float;        (** Quote currency rate *)
  r_b : float;        (** Base currency rate *)
  sigma : float;      (** Volatility *)
}

(** Everlasting option pricing result *)
type option_result = {
  option_price : float;
  delta : float;
  underlying : float;
  intrinsic : float;
  time_value : float;
}

(** Market data for a perpetual futures contract *)
type market_data = {
  symbol : string;
  spot : float;
  mark_price : float;
  index_price : float;
  funding_rate : float;         (** Current funding rate (8h or per period) *)
  funding_interval_hours : int; (** Funding interval in hours *)
  open_interest : float option;
  volume_24h : float option;
  timestamp : string;
}

(** Analysis result combining market data with theoretical pricing *)
type analysis_result = {
  market : market_data;
  theoretical : pricing_result;
  mispricing : float;           (** Market price - theoretical price *)
  mispricing_pct : float;
  arbitrage_signal : string;    (** "LONG", "SHORT", or "NEUTRAL" *)
}

(* Helper functions *)

let contract_type_to_string = function
  | Linear -> "Linear"
  | Inverse -> "Inverse"
  | Quanto -> "Quanto"

let option_type_to_string = function
  | Call -> "Call"
  | Put -> "Put"

let string_to_contract_type = function
  | "linear" | "Linear" -> Some Linear
  | "inverse" | "Inverse" -> Some Inverse
  | "quanto" | "Quanto" -> Some Quanto
  | _ -> None

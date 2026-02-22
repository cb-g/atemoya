(** Types for perpetual futures pricing. *)

type contract_type = Linear | Inverse | Quanto

type currency_pair = {
  base : string;
  quote : string;
  terciary : string option;
}

type interest_rates = {
  r_a : float;
  r_b : float;
  r_c : float option;
}

type funding_params = {
  kappa : float;
  iota : float;
}

type volatility_params = {
  sigma_x : float;
  sigma_z : float option;
  rho_xz : float option;
}

type perpetual_contract = {
  contract_type : contract_type;
  pair : currency_pair;
  rates : interest_rates;
  funding : funding_params;
  volatility : volatility_params option;
}

type pricing_result = {
  spot_price : float;
  futures_price : float;
  basis : float;
  basis_pct : float;
  fair_funding_rate : float;
  perfect_iota : float;
}

type option_type = Call | Put

type everlasting_option = {
  opt_type : option_type;
  strike : float;
  kappa : float;
  r_a : float;
  r_b : float;
  sigma : float;
}

type option_result = {
  option_price : float;
  delta : float;
  underlying : float;
  intrinsic : float;
  time_value : float;
}

type market_data = {
  symbol : string;
  spot : float;
  mark_price : float;
  index_price : float;
  funding_rate : float;
  funding_interval_hours : int;
  open_interest : float option;
  volume_24h : float option;
  timestamp : string;
}

type analysis_result = {
  market : market_data;
  theoretical : pricing_result;
  mispricing : float;
  mispricing_pct : float;
  arbitrage_signal : string;
}

val contract_type_to_string : contract_type -> string
val option_type_to_string : option_type -> string
val string_to_contract_type : string -> contract_type option

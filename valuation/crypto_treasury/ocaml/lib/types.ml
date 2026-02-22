(** Crypto Treasury Types *)

(** Type of crypto holdings a company has *)
type holding_type =
  | BTC
  | ETH
  | Mixed

let string_of_holding_type = function
  | BTC -> "BTC"
  | ETH -> "ETH"
  | Mixed -> "Mixed"

let holding_type_of_btc_eth ~btc_holdings ~eth_holdings =
  match btc_holdings > 0, eth_holdings > 0 with
  | true, false -> BTC
  | false, true -> ETH
  | true, true -> Mixed
  | false, false -> BTC (* default *)

(** Investment signal based on mNAV *)
type signal =
  | StrongBuy
  | Buy
  | Hold
  | Caution
  | Overvalued

let string_of_signal = function
  | StrongBuy -> "Strong Buy"
  | Buy -> "Buy"
  | Hold -> "Hold"
  | Caution -> "Caution"
  | Overvalued -> "Overvalued"

let signal_color = function
  | StrongBuy -> "green"
  | Buy -> "green"
  | Hold -> "yellow"
  | Caution -> "yellow"
  | Overvalued -> "red"

let signal_of_mnav mnav =
  if mnav < 0.8 then StrongBuy
  else if mnav < 1.0 then Buy
  else if mnav < 1.2 then Hold
  else if mnav < 1.5 then Caution
  else Overvalued

(** Company market data fetched from external source *)
type company_data = {
  ticker : string;
  name : string;
  price : float;
  market_cap : float;
  shares_outstanding : float;
  industry : string;
  total_debt : float;
  total_cash : float;
}

(** Holdings data loaded from JSON *)
type holdings_entry = {
  h_name : string;
  btc_holdings : int;
  btc_avg_cost : float;
  eth_holdings : int;
  eth_avg_cost : float;
}

(** Full mNAV valuation metrics *)
type mnav_metrics = {
  ticker : string;
  name : string;
  price : float;
  market_cap : float;
  shares_outstanding : float;
  holding_type : holding_type;

  (* BTC metrics *)
  btc_holdings : int;
  btc_price : float;
  btc_value : float;
  btc_per_share : float;
  implied_btc_price : float;
  btc_avg_cost : float;
  btc_unrealized_gain : float;
  btc_unrealized_gain_pct : float;

  (* ETH metrics *)
  eth_holdings : int;
  eth_price : float;
  eth_value : float;
  eth_per_share : float;
  implied_eth_price : float;
  eth_avg_cost : float;
  eth_unrealized_gain : float;
  eth_unrealized_gain_pct : float;

  (* Combined metrics *)
  nav : float;
  nav_per_share : float;
  mnav : float;
  premium_pct : float;
  total_unrealized_gain : float;
  debt_to_nav : float;
  signal : signal;
}

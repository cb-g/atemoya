(** mNAV (multiple of Net Asset Value) calculations *)

open Types

(** Calculate NAV from BTC and ETH holdings *)
let calculate_nav ~btc_holdings ~btc_price ~eth_holdings ~eth_price =
  let btc_value = float_of_int btc_holdings *. btc_price in
  let eth_value = float_of_int eth_holdings *. eth_price in
  btc_value +. eth_value

(** Calculate mNAV = Market Cap / NAV *)
let calculate_mnav ~market_cap ~nav =
  if nav > 0.0 then market_cap /. nav
  else infinity

(** Calculate premium/discount percentage from mNAV *)
let premium_pct_of_mnav mnav =
  (mnav -. 1.0) *. 100.0

(** Calculate per-share metrics *)
let per_share ~holdings ~shares =
  if shares > 0.0 then float_of_int holdings /. shares
  else 0.0

(** Calculate implied crypto price based on market cap and holdings.

    For BTC-only: implied_btc = market_cap / btc_holdings
    For ETH-only: implied_eth = market_cap / eth_holdings
    For mixed: implied = spot * mNAV (proportional allocation)

    NOTE: For mixed holdings, this assumes the mNAV premium/discount
    applies equally to both assets. In reality the market may value
    the BTC and ETH portions differently. *)
let calculate_implied_prices ~btc_holdings ~eth_holdings ~btc_price ~eth_price ~market_cap ~mnav =
  match btc_holdings > 0, eth_holdings > 0 with
  | true, false ->
    (* Pure BTC play *)
    let implied_btc = market_cap /. float_of_int btc_holdings in
    (implied_btc, 0.0)
  | false, true ->
    (* Pure ETH play *)
    let implied_eth = market_cap /. float_of_int eth_holdings in
    (0.0, implied_eth)
  | true, true ->
    (* Mixed: proportional allocation *)
    let implied_btc = btc_price *. mnav in
    let implied_eth = eth_price *. mnav in
    (implied_btc, implied_eth)
  | false, false ->
    (0.0, 0.0)

(** Calculate unrealized gain from cost basis *)
let unrealized_gain ~current_price ~avg_cost ~holdings =
  if avg_cost > 0.0 && holdings > 0 then
    let gain = (current_price -. avg_cost) *. float_of_int holdings in
    let gain_pct = (current_price /. avg_cost -. 1.0) *. 100.0 in
    (gain, gain_pct)
  else
    (0.0, 0.0)

(** Calculate debt-to-NAV ratio *)
let debt_to_nav ~total_debt ~nav =
  if nav > 0.0 then total_debt /. nav
  else 0.0

(** Calculate complete mNAV metrics for a company *)
let calculate_mnav_metrics
    ~(company : company_data)
    ~(btc_holdings : int)
    ~(btc_price : float)
    ~(eth_holdings : int)
    ~(eth_price : float)
    ~(btc_avg_cost : float)
    ~(eth_avg_cost : float)
  : mnav_metrics =
  let market_cap = company.market_cap in
  let shares = company.shares_outstanding in

  (* Core NAV *)
  let btc_value = float_of_int btc_holdings *. btc_price in
  let eth_value = float_of_int eth_holdings *. eth_price in
  let nav = btc_value +. eth_value in
  let nav_per_share = if shares > 0.0 then nav /. shares else 0.0 in

  (* mNAV *)
  let mnav = calculate_mnav ~market_cap ~nav in
  let premium = premium_pct_of_mnav mnav in

  (* Per share *)
  let btc_per_share = per_share ~holdings:btc_holdings ~shares in
  let eth_per_share = per_share ~holdings:eth_holdings ~shares in

  (* Implied prices *)
  let (implied_btc_price, implied_eth_price) =
    calculate_implied_prices
      ~btc_holdings ~eth_holdings
      ~btc_price ~eth_price
      ~market_cap ~mnav
  in

  (* Cost basis *)
  let (btc_unrealized_gain, btc_unrealized_gain_pct) =
    unrealized_gain ~current_price:btc_price ~avg_cost:btc_avg_cost ~holdings:btc_holdings
  in
  let (eth_unrealized_gain, eth_unrealized_gain_pct) =
    unrealized_gain ~current_price:eth_price ~avg_cost:eth_avg_cost ~holdings:eth_holdings
  in

  (* Leverage *)
  let debt_to_nav_ratio = debt_to_nav ~total_debt:company.total_debt ~nav in

  (* Holding type *)
  let ht = holding_type_of_btc_eth ~btc_holdings ~eth_holdings in

  (* Signal *)
  let sig_ = signal_of_mnav mnav in

  {
    ticker = company.ticker;
    name = company.name;
    price = company.price;
    market_cap;
    shares_outstanding = shares;
    holding_type = ht;

    btc_holdings;
    btc_price;
    btc_value;
    btc_per_share;
    implied_btc_price;
    btc_avg_cost;
    btc_unrealized_gain;
    btc_unrealized_gain_pct;

    eth_holdings;
    eth_price;
    eth_value;
    eth_per_share;
    implied_eth_price;
    eth_avg_cost;
    eth_unrealized_gain;
    eth_unrealized_gain_pct;

    nav;
    nav_per_share;
    mnav;
    premium_pct = premium;
    total_unrealized_gain = btc_unrealized_gain +. eth_unrealized_gain;
    debt_to_nav = debt_to_nav_ratio;
    signal = sig_;
  }

(** Format a float value as currency string *)
let format_currency ?(decimals=2) value =
  let abs_val = abs_float value in
  if abs_val >= 1e12 then
    Printf.sprintf "$%.*fT" decimals (value /. 1e12)
  else if abs_val >= 1e9 then
    Printf.sprintf "$%.*fB" decimals (value /. 1e9)
  else if abs_val >= 1e6 then
    Printf.sprintf "$%.*fM" decimals (value /. 1e6)
  else
    Printf.sprintf "$%.*f" decimals value

(** Sort results by mNAV (lowest = most undervalued first) *)
let sort_by_mnav (results : mnav_metrics list) : mnav_metrics list =
  List.sort (fun a b -> compare a.mnav b.mnav) results

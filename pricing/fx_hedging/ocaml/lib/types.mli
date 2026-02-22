(* Interface for FX hedging types *)

type currency =
  | USD
  | EUR
  | GBP
  | JPY
  | CHF
  | AUD
  | CAD
  | CNY
  | BTC
  | ETH
  | SOL

type option_type =
  | Call
  | Put

type fx_pair = {
  base: currency;
  quote: currency;
  spot_rate: float;
}

type forward_contract = {
  pair: fx_pair;
  forward_rate: float;
  domestic_rate: float;
  foreign_rate: float;
  maturity: float;
  notional: float;
}

type futures_contract = {
  underlying: fx_pair;
  contract_code: string;
  contract_month: string;
  futures_price: float;
  contract_size: float;
  tick_size: float;
  tick_value: float;
  initial_margin: float;
  maintenance_margin: float;
  expiry: float;
}

type futures_option = {
  underlying_futures: futures_contract;
  option_type: option_type;
  strike: float;
  expiry: float;
  premium: float;
  volatility: float;
}

type greeks = {
  delta: float;
  gamma: float;
  theta: float;
  vega: float;
  rho: float;
}

type portfolio_position = {
  ticker: string;
  quantity: float;
  price_usd: float;
  market_value_usd: float;
  currency_exposure: (currency * float) list;
}

type fx_exposure = {
  currency: currency;
  net_exposure_usd: float;
  pct_of_portfolio: float;
  positions: portfolio_position list;
}

type hedge_position =
  | FuturesHedge of {
      futures: futures_contract;
      quantity: int;
      entry_price: float;
      entry_date: float;
    }
  | OptionsHedge of {
      option: futures_option;
      quantity: int;
      entry_premium: float;
      entry_date: float;
    }

type hedge_strategy =
  | Static of { hedge_ratio: float }
  | Dynamic of {
      rebalance_threshold: float;
      target_delta: float;
      rebalance_interval_days: int;
    }
  | MinimumVariance of { lookback_days: int }
  | OptimalCost of {
      risk_aversion: float;
      hedge_cost_bps: float;
    }

type margin_account = {
  cash_balance: float;
  initial_margin_required: float;
  maintenance_margin_required: float;
  variation_margin: float;
  excess_margin: float;
}

type hedge_result = {
  unhedged_pnl: float;
  hedged_pnl: float;
  hedge_pnl: float;
  transaction_costs: float;
  num_rebalances: int;
  hedge_effectiveness: float;
  sharpe_unhedged: float option;
  sharpe_hedged: float option;
  max_drawdown_unhedged: float;
  max_drawdown_hedged: float;
}

type simulation_snapshot = {
  timestamp: float;
  spot_rate: float;
  futures_price: float;
  exposure_value: float;
  hedge_value: float;
  net_value: float;
  unhedged_pnl: float;
  hedged_pnl: float;
  margin_balance: float;
  cumulative_costs: float;
  futures_position: float;
}

type roll_event = {
  timestamp: float;
  from_contract: string;
  to_contract: string;
  from_price: float;
  to_price: float;
  roll_cost: float;
  quantity: int;
}

type cme_contract_spec = {
  code: string;
  name: string;
  currency_pair: fx_pair;
  contract_size: float;
  tick_size: float;
  tick_value: float;
  typical_initial_margin: float;
  typical_maintenance_margin: float;
  trading_hours: string;
  contract_months: string list;
}

(* Helper functions *)
val currency_to_string : currency -> string
val currency_of_string : string -> currency
val fx_pair_to_string : fx_pair -> string

val zero_greeks : greeks
val add_greeks : greeks -> greeks -> greeks
val scale_greeks : greeks -> float -> greeks

(* CME contract specifications *)
val cme_eur_usd : cme_contract_spec
val cme_gbp_usd : cme_contract_spec
val cme_jpy_usd : cme_contract_spec
val cme_chf_usd : cme_contract_spec
val cme_aud_usd : cme_contract_spec
val cme_cad_usd : cme_contract_spec
val cme_micro_eur : cme_contract_spec
val cme_micro_gbp : cme_contract_spec
val cme_micro_jpy : cme_contract_spec
val cme_micro_chf : cme_contract_spec
val cme_micro_aud : cme_contract_spec
val cme_micro_cad : cme_contract_spec
val cme_btc_usd : cme_contract_spec
val cme_micro_btc : cme_contract_spec
val cme_eth_usd : cme_contract_spec
val cme_micro_eth : cme_contract_spec
val cme_sol_usd : cme_contract_spec
val cme_micro_sol : cme_contract_spec
val get_cme_spec : string -> cme_contract_spec

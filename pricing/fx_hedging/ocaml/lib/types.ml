(* Core types for FX hedging and futures options *)

(* Currency enumeration *)
type currency =
  | USD  (* US Dollar *)
  | EUR  (* Euro *)
  | GBP  (* British Pound *)
  | JPY  (* Japanese Yen *)
  | CHF  (* Swiss Franc *)
  | AUD  (* Australian Dollar *)
  | CAD  (* Canadian Dollar *)
  | CNY  (* Chinese Yuan *)
  | BTC  (* Bitcoin *)
  | ETH  (* Ethereum *)
  | SOL  (* Solana *)

(* Option type *)
type option_type =
  | Call
  | Put

(* FX pair - quoted as BASE/QUOTE *)
type fx_pair = {
  base: currency;     (* Numerator currency *)
  quote: currency;    (* Denominator currency *)
  spot_rate: float;   (* Current exchange rate *)
}

(* FX forward contract *)
type forward_contract = {
  pair: fx_pair;
  forward_rate: float;
  domestic_rate: float;  (* Interest rate of quote currency *)
  foreign_rate: float;   (* Interest rate of base currency *)
  maturity: float;       (* Years to maturity *)
  notional: float;       (* Notional amount in base currency *)
}

(* Futures contract specification *)
type futures_contract = {
  underlying: fx_pair;
  contract_code: string;        (* e.g., "6E" for EUR/USD *)
  contract_month: string;        (* e.g., "H24" = March 2024 *)
  futures_price: float;
  contract_size: float;          (* Notional per contract (e.g., 125,000 EUR) *)
  tick_size: float;              (* Minimum price movement *)
  tick_value: float;             (* Dollar value per tick *)
  initial_margin: float;         (* Required upfront margin *)
  maintenance_margin: float;     (* Minimum to avoid margin call *)
  expiry: float;                 (* Years to expiry *)
}

(* Futures option *)
type futures_option = {
  underlying_futures: futures_contract;
  option_type: option_type;
  strike: float;
  expiry: float;                 (* Years to expiry *)
  premium: float;                (* Option premium per unit *)
  volatility: float;             (* Implied volatility *)
}

(* Greeks for futures options *)
type greeks = {
  delta: float;    (* ∂V/∂F - sensitivity to futures price *)
  gamma: float;    (* ∂²V/∂F² - delta sensitivity *)
  theta: float;    (* -∂V/∂t - time decay per day *)
  vega: float;     (* ∂V/∂σ - volatility sensitivity per 1% *)
  rho: float;      (* ∂V/∂r - interest rate sensitivity per 1% *)
}

(* Portfolio position with FX exposure *)
type portfolio_position = {
  ticker: string;
  quantity: float;
  price_usd: float;
  market_value_usd: float;                    (* quantity × price *)
  currency_exposure: (currency * float) list; (* [(EUR, 0.70); (JPY, 0.20)] = % of value *)
}

(* Aggregated FX exposure *)
type fx_exposure = {
  currency: currency;
  net_exposure_usd: float;      (* Net exposure in USD *)
  pct_of_portfolio: float;      (* % of total portfolio *)
  positions: portfolio_position list; (* Contributing positions *)
}

(* Hedge position types *)
type hedge_position =
  | FuturesHedge of {
      futures: futures_contract;
      quantity: int;              (* Positive = long, negative = short *)
      entry_price: float;
      entry_date: float;          (* Timestamp *)
    }
  | OptionsHedge of {
      option: futures_option;
      quantity: int;              (* Positive = long, negative = short *)
      entry_premium: float;
      entry_date: float;
    }

(* Hedge strategy types *)
type hedge_strategy =
  | Static of {
      hedge_ratio: float;  (* -1.0 = full hedge, -0.5 = half hedge *)
    }
  | Dynamic of {
      rebalance_threshold: float;  (* Delta threshold for rebalancing *)
      target_delta: float;          (* Target delta after rebalance *)
      rebalance_interval_days: int; (* Max days between rebalances *)
    }
  | MinimumVariance of {
      lookback_days: int;  (* Historical window for variance calculation *)
    }
  | OptimalCost of {
      risk_aversion: float;  (* Risk aversion parameter λ *)
      hedge_cost_bps: float; (* Transaction cost in bps *)
    }

(* Margin account *)
type margin_account = {
  cash_balance: float;
  initial_margin_required: float;
  maintenance_margin_required: float;
  variation_margin: float;       (* Daily settlement P&L *)
  excess_margin: float;          (* Available above maintenance *)
}

(* Hedge result from backtesting *)
type hedge_result = {
  unhedged_pnl: float;
  hedged_pnl: float;
  hedge_pnl: float;              (* P&L from hedge instrument *)
  transaction_costs: float;
  num_rebalances: int;
  hedge_effectiveness: float;    (* % variance reduction *)
  sharpe_unhedged: float option;
  sharpe_hedged: float option;
  max_drawdown_unhedged: float;
  max_drawdown_hedged: float;
}

(* Simulation snapshot *)
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

(* Roll event *)
type roll_event = {
  timestamp: float;
  from_contract: string;    (* e.g., "6EH24" *)
  to_contract: string;      (* e.g., "6EM24" *)
  from_price: float;
  to_price: float;
  roll_cost: float;         (* Cost of rolling *)
  quantity: int;
}

(* CME contract specifications (predefined) *)
type cme_contract_spec = {
  code: string;              (* "6E", "6J", "6B", etc. *)
  name: string;
  currency_pair: fx_pair;
  contract_size: float;
  tick_size: float;
  tick_value: float;
  typical_initial_margin: float;
  typical_maintenance_margin: float;
  trading_hours: string;
  contract_months: string list;  (* ["H", "M", "U", "Z"] = Mar, Jun, Sep, Dec *)
}

(* Helper functions *)

(* String representation of currency *)
let currency_to_string = function
  | USD -> "USD"
  | EUR -> "EUR"
  | GBP -> "GBP"
  | JPY -> "JPY"
  | CHF -> "CHF"
  | AUD -> "AUD"
  | CAD -> "CAD"
  | CNY -> "CNY"
  | BTC -> "BTC"
  | ETH -> "ETH"
  | SOL -> "SOL"

(* Parse currency from string *)
let currency_of_string = function
  | "USD" -> USD
  | "EUR" -> EUR
  | "GBP" -> GBP
  | "JPY" -> JPY
  | "CHF" -> CHF
  | "AUD" -> AUD
  | "CAD" -> CAD
  | "CNY" -> CNY
  | "BTC" -> BTC
  | "ETH" -> ETH
  | "SOL" -> SOL
  | s -> failwith (Printf.sprintf "Unknown currency: %s" s)

(* FX pair to string *)
let fx_pair_to_string pair =
  Printf.sprintf "%s/%s"
    (currency_to_string pair.base)
    (currency_to_string pair.quote)

(* Zero Greeks *)
let zero_greeks = {
  delta = 0.0;
  gamma = 0.0;
  theta = 0.0;
  vega = 0.0;
  rho = 0.0;
}

(* Add two Greeks structures *)
let add_greeks g1 g2 = {
  delta = g1.delta +. g2.delta;
  gamma = g1.gamma +. g2.gamma;
  theta = g1.theta +. g2.theta;
  vega = g1.vega +. g2.vega;
  rho = g1.rho +. g2.rho;
}

(* Scale Greeks by a factor *)
let scale_greeks greeks factor = {
  delta = greeks.delta *. factor;
  gamma = greeks.gamma *. factor;
  theta = greeks.theta *. factor;
  vega = greeks.vega *. factor;
  rho = greeks.rho *. factor;
}

(* CME standard contract specifications *)
let cme_eur_usd = {
  code = "6E";
  name = "Euro FX";
  currency_pair = { base = EUR; quote = USD; spot_rate = 0.0 }; (* Spot updated separately *)
  contract_size = 125000.0;
  tick_size = 0.00005;
  tick_value = 6.25;
  typical_initial_margin = 2500.0;
  typical_maintenance_margin = 2000.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["H"; "M"; "U"; "Z"];  (* Mar, Jun, Sep, Dec *)
}

let cme_jpy_usd = {
  code = "6J";
  name = "Japanese Yen";
  currency_pair = { base = JPY; quote = USD; spot_rate = 0.0 };
  contract_size = 12500000.0;
  tick_size = 0.0000005;
  tick_value = 6.25;
  typical_initial_margin = 2000.0;
  typical_maintenance_margin = 1600.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["H"; "M"; "U"; "Z"];
}

let cme_gbp_usd = {
  code = "6B";
  name = "British Pound";
  currency_pair = { base = GBP; quote = USD; spot_rate = 0.0 };
  contract_size = 62500.0;
  tick_size = 0.0001;
  tick_value = 6.25;
  typical_initial_margin = 2500.0;
  typical_maintenance_margin = 2000.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["H"; "M"; "U"; "Z"];
}

let cme_chf_usd = {
  code = "6S";
  name = "Swiss Franc";
  currency_pair = { base = CHF; quote = USD; spot_rate = 0.0 };
  contract_size = 125000.0;
  tick_size = 0.0001;
  tick_value = 12.50;
  typical_initial_margin = 2000.0;
  typical_maintenance_margin = 1600.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["H"; "M"; "U"; "Z"];
}

(* CME Australian Dollar - 6A *)
let cme_aud_usd = {
  code = "6A";
  name = "Australian Dollar";
  currency_pair = { base = AUD; quote = USD; spot_rate = 0.0 };
  contract_size = 100000.0;
  tick_size = 0.0001;
  tick_value = 10.0;
  typical_initial_margin = 1800.0;
  typical_maintenance_margin = 1620.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["H"; "M"; "U"; "Z"];
}

(* CME Canadian Dollar - 6C *)
let cme_cad_usd = {
  code = "6C";
  name = "Canadian Dollar";
  currency_pair = { base = CAD; quote = USD; spot_rate = 0.0 };
  contract_size = 100000.0;
  tick_size = 0.00005;
  tick_value = 5.0;
  typical_initial_margin = 1800.0;
  typical_maintenance_margin = 1620.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["H"; "M"; "U"; "Z"];
}

(* CME E-micro FX Futures — 1/10th standard contract size *)
let cme_micro_eur = {
  code = "M6E";
  name = "E-micro EUR/USD";
  currency_pair = { base = EUR; quote = USD; spot_rate = 0.0 };
  contract_size = 12500.0;
  tick_size = 0.0001;
  tick_value = 1.25;
  typical_initial_margin = 250.0;
  typical_maintenance_margin = 200.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["H"; "M"; "U"; "Z"];
}

let cme_micro_jpy = {
  code = "M6J";
  name = "E-micro JPY/USD";
  currency_pair = { base = JPY; quote = USD; spot_rate = 0.0 };
  contract_size = 1250000.0;
  tick_size = 0.000001;
  tick_value = 1.25;
  typical_initial_margin = 200.0;
  typical_maintenance_margin = 160.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["H"; "M"; "U"; "Z"];
}

let cme_micro_gbp = {
  code = "M6B";
  name = "E-micro GBP/USD";
  currency_pair = { base = GBP; quote = USD; spot_rate = 0.0 };
  contract_size = 6250.0;
  tick_size = 0.0001;
  tick_value = 0.625;
  typical_initial_margin = 250.0;
  typical_maintenance_margin = 200.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["H"; "M"; "U"; "Z"];
}

let cme_micro_chf = {
  code = "M6S";
  name = "E-micro CHF/USD";
  currency_pair = { base = CHF; quote = USD; spot_rate = 0.0 };
  contract_size = 12500.0;
  tick_size = 0.0001;
  tick_value = 1.25;
  typical_initial_margin = 200.0;
  typical_maintenance_margin = 160.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["H"; "M"; "U"; "Z"];
}

let cme_micro_aud = {
  code = "M6A";
  name = "E-micro AUD/USD";
  currency_pair = { base = AUD; quote = USD; spot_rate = 0.0 };
  contract_size = 10000.0;
  tick_size = 0.0001;
  tick_value = 1.0;
  typical_initial_margin = 180.0;
  typical_maintenance_margin = 162.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["H"; "M"; "U"; "Z"];
}

let cme_micro_cad = {
  code = "M6C";
  name = "E-micro CAD/USD";
  currency_pair = { base = CAD; quote = USD; spot_rate = 0.0 };
  contract_size = 10000.0;
  tick_size = 0.00005;
  tick_value = 0.5;
  typical_initial_margin = 180.0;
  typical_maintenance_margin = 162.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["H"; "M"; "U"; "Z"];
}

(* CME Bitcoin Futures - BTC *)
let cme_btc_usd = {
  code = "BTC";
  name = "Bitcoin";
  currency_pair = { base = BTC; quote = USD; spot_rate = 0.0 };
  contract_size = 5.0;           (* 5 BTC per contract *)
  tick_size = 5.0;               (* $5 per BTC *)
  tick_value = 25.0;             (* $25 per tick (5 BTC × $5) *)
  typical_initial_margin = 80000.0;  (* ~80% of contract value at $100k BTC *)
  typical_maintenance_margin = 72000.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";  (* 23 hours/day, 5 days/week *)
  contract_months = ["F"; "G"; "H"; "J"; "K"; "M"; "N"; "Q"; "U"; "V"; "X"; "Z"];  (* All 12 months *)
}

(* CME Micro Bitcoin Futures - MBT *)
let cme_micro_btc = {
  code = "MBT";
  name = "Micro Bitcoin";
  currency_pair = { base = BTC; quote = USD; spot_rate = 0.0 };
  contract_size = 0.10;          (* 0.1 BTC per contract *)
  tick_size = 5.0;               (* $5 per BTC *)
  tick_value = 0.50;             (* $0.50 per tick (0.1 BTC × $5) *)
  typical_initial_margin = 1600.0;
  typical_maintenance_margin = 1440.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["F"; "G"; "H"; "J"; "K"; "M"; "N"; "Q"; "U"; "V"; "X"; "Z"];
}

(* CME Ethereum Futures - ETH *)
let cme_eth_usd = {
  code = "ETH";
  name = "Ethereum";
  currency_pair = { base = ETH; quote = USD; spot_rate = 0.0 };
  contract_size = 50.0;          (* 50 ETH per contract *)
  tick_size = 0.25;              (* $0.25 per ETH *)
  tick_value = 12.50;            (* $12.50 per tick (50 ETH × $0.25) *)
  typical_initial_margin = 7000.0;
  typical_maintenance_margin = 6300.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["F"; "G"; "H"; "J"; "K"; "M"; "N"; "Q"; "U"; "V"; "X"; "Z"];
}

(* CME Micro Ether Futures - MET *)
let cme_micro_eth = {
  code = "MET";
  name = "Micro Ether";
  currency_pair = { base = ETH; quote = USD; spot_rate = 0.0 };
  contract_size = 0.1;
  tick_size = 0.25;
  tick_value = 0.025;
  typical_initial_margin = 56.0;
  typical_maintenance_margin = 50.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["F"; "G"; "H"; "J"; "K"; "M"; "N"; "Q"; "U"; "V"; "X"; "Z"];
}

(* CME Solana Futures - SOL *)
let cme_sol_usd = {
  code = "SOL";
  name = "Solana";
  currency_pair = { base = SOL; quote = USD; spot_rate = 0.0 };
  contract_size = 500.0;
  tick_size = 0.05;
  tick_value = 25.0;
  typical_initial_margin = 5000.0;
  typical_maintenance_margin = 4500.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["F"; "G"; "H"; "J"; "K"; "M"; "N"; "Q"; "U"; "V"; "X"; "Z"];
}

(* CME Micro Solana Futures - MSOL *)
let cme_micro_sol = {
  code = "MSOL";
  name = "Micro Solana";
  currency_pair = { base = SOL; quote = USD; spot_rate = 0.0 };
  contract_size = 5.0;
  tick_size = 0.05;
  tick_value = 0.25;
  typical_initial_margin = 45.0;
  typical_maintenance_margin = 40.0;
  trading_hours = "Sun 5pm - Fri 4pm CT";
  contract_months = ["F"; "G"; "H"; "J"; "K"; "M"; "N"; "Q"; "U"; "V"; "X"; "Z"];
}

(* Get CME spec by code *)
let get_cme_spec code =
  match code with
  | "6E" -> cme_eur_usd
  | "6B" -> cme_gbp_usd
  | "6J" -> cme_jpy_usd
  | "6S" -> cme_chf_usd
  | "6A" -> cme_aud_usd
  | "6C" -> cme_cad_usd
  | "M6E" -> cme_micro_eur
  | "M6B" -> cme_micro_gbp
  | "M6J" -> cme_micro_jpy
  | "M6S" -> cme_micro_chf
  | "M6A" -> cme_micro_aud
  | "M6C" -> cme_micro_cad
  | "BTC" -> cme_btc_usd
  | "MBT" -> cme_micro_btc
  | "ETH" -> cme_eth_usd
  | "MET" -> cme_micro_eth
  | "SOL" -> cme_sol_usd
  | "MSOL" -> cme_micro_sol
  | _ -> failwith (Printf.sprintf "Unknown CME contract code: %s" code)

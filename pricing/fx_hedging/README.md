# FX Hedging & Futures Options

Capital-efficient currency hedging using forwards, futures, and futures options with Black-76 model, margin calculations, and hedge optimization.

## Overview

This module provides a comprehensive framework for hedging foreign exchange (FX) exposure using:

- **Forward Contracts**: OTC contracts based on covered interest rate parity
- **Futures Contracts**: Exchange-traded contracts with margin requirements (3-5% vs 100% for spot)
- **Futures Options**: Black-76 model for pricing options on futures
- **Portfolio Analysis**: Multi-currency exposure calculation and hedge optimization
- **Backtesting**: Historical simulation of hedge performance with realistic costs

**Key Benefits**:
- **Capital Efficiency**: Futures require only 3-5% margin vs 100% for spot FX
- **Leverage**: 20-40x leverage on currency exposure
- **Flexibility**: Static, dynamic, and optimized hedge strategies
- **Risk Management**: Real-time margin tracking and hedge effectiveness metrics

## Use Case: Hedging USD Portfolio Depreciation

If you have a USD-denominated portfolio and are concerned about USD depreciation against other currencies (EUR, GBP, JPY, CHF), this module helps you:

1. Calculate your net FX exposure across all positions
2. Design capital-efficient hedges using CME futures
3. Optimize hedge ratios to minimize variance
4. Backtest hedge performance with realistic transaction costs
5. Track margin requirements and hedge effectiveness

## Mathematical Foundations

### 1. Covered Interest Rate Parity (CIP)

Forward rate determined by interest rate differential:

```
F = S × e^((r_d - r_f) × T)
```

Where:
- `F` = Forward/Futures price
- `S` = Spot exchange rate
- `r_d` = Domestic interest rate
- `r_f` = Foreign interest rate
- `T` = Time to maturity

### 2. Black-76 Model for Futures Options

Call option price:
```
C = e^(-rT) × [F × N(d1) - K × N(d2)]
```

Put option price:
```
P = e^(-rT) × [K × N(-d2) - F × N(-d1)]
```

Where:
```
d1 = [ln(F/K) + (σ²/2)T] / (σ√T)
d2 = d1 - σ√T
```

**Key difference from Black-Scholes**: Uses futures price `F` instead of spot `S`, no dividend yield.

### 3. Minimum Variance Hedge Ratio

Optimal hedge ratio minimizes portfolio variance:

```
h* = Cov(ΔS, ΔF) / Var(ΔF) = ρ × (σ_S / σ_F)
```

Where:
- `ρ` = Correlation between spot and futures returns
- `σ_S` = Spot volatility
- `σ_F` = Futures volatility

### 4. Margin Requirements

**Initial Margin**: Required to open position (typically $2,500 per contract for 6E)
**Maintenance Margin**: Minimum balance before margin call (typically $2,000)

Daily mark-to-market:
```
Margin_t = Margin_{t-1} + ΔF × Position × Contract_Size - Costs
```

### 5. Hedge Effectiveness

Variance reduction from hedging:
```
Hedge Effectiveness = 1 - (Var(Hedged) / Var(Unhedged))
```

## Quick Start

### 1. Fetch Market Data

Fetch FX spot and futures data from Yahoo Finance:

**Docker:**
```bash
# Fetch EUR/USD data (1 year)
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/fx_hedging/python/fetch/fetch_fx_data.py 6E"

# Fetch JPY/USD data (2 years)
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/fx_hedging/python/fetch/fetch_fx_data.py 6J --days 504"

# Fetch all major currency pairs
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/fx_hedging/python/fetch/fetch_fx_data.py --all"
```

**Native:**
```bash
# Fetch EUR/USD data (1 year)
uv run pricing/fx_hedging/python/fetch/fetch_fx_data.py 6E

# Fetch JPY/USD data (2 years)
uv run pricing/fx_hedging/python/fetch/fetch_fx_data.py 6J --days 504

# Fetch all major currency pairs
uv run pricing/fx_hedging/python/fetch/fetch_fx_data.py --all
```

**Contract Codes**:
- `6E`: EUR/USD (Euro)
- `6J`: JPY/USD (Japanese Yen)
- `6B`: GBP/USD (British Pound)
- `6S`: CHF/USD (Swiss Franc)

### 2. Build and Test

**Docker:**
```bash
# Build the project
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build pricing/fx_hedging"

# Run tests
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec test_fx_hedging"

# Run main CLI
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec fx_hedging"
```

**Native:**
```bash
# Build the project
eval $(opam env) && dune build pricing/fx_hedging

# Run tests
eval $(opam env) && dune exec test_fx_hedging

# Run main CLI
eval $(opam env) && dune exec fx_hedging
```

### 3. Run Backtest

Test hedging a $500,000 EUR exposure using EUR/USD futures:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec fx_hedging -- \
  -operation backtest \
  -exposure 500000 \
  -contract 6E \
  -hedge-ratio -1.0 \
  -margin 10000"
```

**Native:**
```bash
eval $(opam env) && dune exec fx_hedging -- \
  -operation backtest \
  -exposure 500000 \
  -contract 6E \
  -hedge-ratio -1.0 \
  -margin 10000
```

**Parameters**:
- `-operation`: `backtest` | `exposure` | `price`
- `-exposure`: USD exposure amount (default: 500000)
- `-contract`: Futures contract code (default: 6E)
- `-hedge-ratio`: Hedge ratio (default: -1.0 = full hedge)
- `-margin`: Initial margin balance (default: 10000)
- `-cost-bps`: Transaction cost in basis points (default: 5.0)

**Output**:
```
=== Backtest Results ===
Unhedged P&L: $-12,543.25
Hedged P&L: $-1,234.67
Hedge P&L: $11,308.58
Transaction Costs: $328.45

Metrics:
  Hedge Effectiveness: 87.32%
  Max Drawdown (Unhedged): -8.45%
  Max Drawdown (Hedged): -2.13%
  Sharpe Ratio (Unhedged): -0.4523
  Sharpe Ratio (Hedged): 0.1234
```

### 4. Analyze Portfolio Exposure

Calculate net FX exposure across your portfolio:

**Docker:**
```bash
# First, create portfolio.csv with your positions
# See pricing/fx_hedging/data/portfolio_example.csv for format

docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec fx_hedging -- -operation exposure"
```

**Native:**
```bash
eval $(opam env) && dune exec fx_hedging -- -operation exposure
```

**Example Portfolio CSV**:
```csv
ticker,quantity,price_usd,currency
ASML,100,850.00,EUR
LVMH,50,920.00,EUR
TSM,200,105.00,TWD
NESN,150,112.00,CHF
```

**Output**:
```
=== Portfolio FX Exposure ===
Total Portfolio Value: $285,000.00

Currency    Exposure (USD)  % of Portfolio
-----------------------------------------
EUR            170,000.00           59.65%
TWD             21,000.00            7.37%
CHF             16,800.00            5.89%
```

### 5. Price Forwards and Options

Price forward contracts and futures options:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec fx_hedging -- -operation price"
```

**Native:**
```bash
eval $(opam env) && dune exec fx_hedging -- -operation price
```

**Output**:
```
Forward Rate (90d): 1.102234
Futures Price: 1.102234

Futures Options (K=1.0800, F=1.1022, T=90d, σ=12%):
  Call Premium: $0.028456
  Put Premium: $0.006123

Call Option Greeks:
  Delta: 0.7234
  Gamma: 0.000234
  Theta: -0.0012 (per day)
  Vega: 0.0045 (per 1% vol)
  Rho: 0.0023 (per 1% rate)
```

### 6. Visualize Results

Generate comprehensive performance charts:

**Docker:**
```bash
# Plot hedge performance
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/fx_hedging/python/viz/plot_hedge_performance.py 6E"

# Plot with exposure analysis
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/fx_hedging/python/viz/plot_hedge_performance.py 6E --show-exposure"

# Save to file
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/fx_hedging/python/viz/plot_hedge_performance.py 6E --output hedge_report.png"

# Plot exposure breakdown
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/fx_hedging/python/viz/plot_exposure_analysis.py"
```

**Native:**
```bash
# Plot hedge performance
uv run pricing/fx_hedging/python/viz/plot_hedge_performance.py 6E

# Plot with exposure analysis
uv run pricing/fx_hedging/python/viz/plot_hedge_performance.py 6E --show-exposure

# Save to file
uv run pricing/fx_hedging/python/viz/plot_hedge_performance.py 6E --output hedge_report.png

# Plot exposure breakdown
uv run pricing/fx_hedging/python/viz/plot_exposure_analysis.py
```

**Visualization includes**:
- Hedged vs unhedged P&L over time
- Hedge-only P&L and transaction costs
- FX spot vs futures prices
- Rolling drawdowns
- Margin account balance
- Futures position changes
- Summary statistics table
- Portfolio exposure breakdown (if available)

## Hedge Strategies

### 1. Static Hedge

Fixed hedge ratio throughout backtest:

```ocaml
let strategy = Types.Static { hedge_ratio = -1.0 }  (* Full hedge *)
```

**When to use**: Simple, low-cost hedging for stable exposures

### 2. Dynamic Hedge (Time-Based)

Rebalance periodically (e.g., weekly):

```ocaml
let strategy = Types.Dynamic {
  rebalance_frequency = 5;  (* days *)
  target_hedge_ratio = -1.0;
}
```

**When to use**: Adapt to changing market conditions

### 3. Minimum Variance Hedge

Optimize hedge ratio to minimize portfolio variance:

```ocaml
let strategy = Types.MinimumVariance {
  lookback_window = 60;  (* days for correlation estimation *)
}
```

**When to use**: Maximize hedge effectiveness when correlation varies

### 4. Optimal Cost Hedge

Balance hedge effectiveness vs transaction costs:

```ocaml
let strategy = Types.OptimalCost {
  rebalance_threshold = 0.1;  (* 10% drift from target *)
  transaction_cost_bps = 5.0;
}
```

**When to use**: Minimize costs for frequent rebalancing

## Contract Specifications

### EUR/USD (6E)

- **Code**: 6E
- **Size**: EUR 125,000
- **Tick Size**: $0.00005 (5 pips)
- **Tick Value**: $6.25
- **Initial Margin**: ~$2,500
- **Maintenance Margin**: ~$2,000
- **Leverage**: ~50x
- **Trading Hours**: Sun 5pm - Fri 4pm CT

### JPY/USD (6J)

- **Code**: 6J
- **Size**: JPY 12,500,000
- **Tick Size**: $0.000001
- **Tick Value**: $12.50
- **Initial Margin**: ~$2,200
- **Maintenance Margin**: ~$1,800

### GBP/USD (6B)

- **Code**: 6B
- **Size**: GBP 62,500
- **Tick Size**: $0.0001
- **Tick Value**: $6.25
- **Initial Margin**: ~$2,800
- **Maintenance Margin**: ~$2,300

### CHF/USD (6S)

- **Code**: 6S
- **Size**: CHF 125,000
- **Tick Size**: $0.0001
- **Tick Value**: $12.50
- **Initial Margin**: ~$2,400
- **Maintenance Margin**: ~$2,000

## Module Structure

```
pricing/fx_hedging/
├── PLAN.md                    # Mathematical foundations
├── README.md                  # This file
├── ocaml/                     # Core OCaml implementation
│   ├── lib/
│   │   ├── types.ml           # Core types (currencies, contracts, positions)
│   │   ├── forwards.ml        # Forward pricing (CIP)
│   │   ├── futures.ml         # Futures pricing and basis
│   │   ├── futures_options.ml # Black-76 model & Greeks
│   │   ├── margin.ml          # Margin calculations (SPAN)
│   │   ├── exposure_analysis.ml # Portfolio FX exposure
│   │   ├── hedge_strategies.ml  # Static/dynamic hedging
│   │   ├── optimization.ml    # Min variance hedge ratio
│   │   ├── simulation.ml      # Backtesting engine
│   │   └── io.ml              # CSV I/O
│   ├── bin/
│   │   └── main.ml            # CLI interface
│   └── test/
│       └── test_fx_hedging.ml # Unit tests
├── python/
│   ├── fetch/
│   │   └── fetch_fx_data.py   # Download FX data from Yahoo Finance
│   └── viz/
│       ├── plot_hedge_performance.py    # Backtest visualization
│       └── plot_exposure_analysis.py    # Exposure breakdown
├── data/                      # Market data (generated)
│   ├── 6e_spot.csv
│   ├── 6e_futures.csv
│   └── portfolio.csv          # Your portfolio positions
└── output/                    # Results (generated)
    ├── 6E_backtest.csv
    └── exposure_analysis.csv
```

## Examples

### Example 1: Hedge EUR Exposure

You have a portfolio with EUR 500,000 in European stocks. USD is depreciating, and you want to hedge:

**Docker:**
```bash
# 1. Fetch EUR/USD data
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/fx_hedging/python/fetch/fetch_fx_data.py 6E"

# 2. Run backtest with full hedge
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec fx_hedging -- \
  -operation backtest \
  -exposure 500000 \
  -contract 6E \
  -hedge-ratio -1.0"

# 3. Visualize results
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/fx_hedging/python/viz/plot_hedge_performance.py 6E"
```

**Native:**
```bash
# 1. Fetch EUR/USD data
uv run pricing/fx_hedging/python/fetch/fetch_fx_data.py 6E

# 2. Run backtest with full hedge
eval $(opam env) && dune exec fx_hedging -- \
  -operation backtest \
  -exposure 500000 \
  -contract 6E \
  -hedge-ratio -1.0

# 3. Visualize results
uv run pricing/fx_hedging/python/viz/plot_hedge_performance.py 6E
```

**Interpretation**:
- Unhedged P&L shows currency risk
- Hedged P&L shows reduced volatility
- Hedge effectiveness shows variance reduction
- Transaction costs show cost of hedging

### Example 2: Multi-Currency Portfolio

Portfolio with mixed currency exposure:

```bash
# 1. Create portfolio.csv with your positions
cat > pricing/fx_hedging/data/portfolio.csv << EOF
ticker,quantity,price_usd,currency
ASML,100,850.00,EUR
LVMH,50,920.00,EUR
7203.T,500,15.50,JPY
NESN,150,112.00,CHF
EOF

# 2. Calculate exposure (Docker)
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec fx_hedging -- -operation exposure"

# 3. Visualize exposure breakdown (Docker)
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/fx_hedging/python/viz/plot_exposure_analysis.py"
```

**Native:**
```bash
# 2. Calculate exposure
eval $(opam env) && dune exec fx_hedging -- -operation exposure

# 3. Visualize exposure breakdown
uv run pricing/fx_hedging/python/viz/plot_exposure_analysis.py
```

### Example 3: Optimize Hedge Ratio

Find optimal hedge ratio based on historical correlation:

```ocaml
(* In your OCaml code *)
let h_optimal = Optimization.min_variance_hedge_ratio
  ~exposure_returns
  ~futures_returns
in
Printf.printf "Optimal hedge ratio: %.4f\n" h_optimal
```

### Example 4: Price Futures Options

Price a 90-day EUR/USD call option:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec fx_hedging -- -operation price"
```

**Native:**
```bash
eval $(opam env) && dune exec fx_hedging -- -operation price
```

Or programmatically:

```ocaml
let call_price = Futures_options.black_price
  ~option_type:Types.Call
  ~futures_price:1.10
  ~strike:1.08
  ~expiry:(90.0 /. 365.0)
  ~rate:0.05
  ~volatility:0.12
in
Printf.printf "Call premium: $%.6f\n" call_price
```

## Cost Analysis

### Transaction Costs

Typical costs for CME FX futures:
- **Bid-ask spread**: 0.5-1.0 pip (~$6.25 per contract for 6E)
- **Commission**: $2-5 per contract (per side)
- **Total round-trip**: ~$15-20 per contract

Default in backtest: **5 bps** (basis points) of notional

### Margin Requirements

**6E (EUR/USD)** example:
- Contract size: EUR 125,000
- Notional value at 1.10: $137,500
- Initial margin: $2,500 (1.8% of notional)
- Leverage: 55x

**Capital efficiency vs spot**:
- Spot FX: Requires 100% of notional = $137,500
- Futures: Requires 1.8% margin = $2,500
- **Savings: 98.2%** of capital freed for other uses

## Performance Metrics

### Hedge Effectiveness

Measures variance reduction:
```
HE = 1 - (Var(Hedged) / Var(Unhedged))
```

- **100%**: Perfect hedge (no residual risk)
- **90%**: Excellent (typical for high correlation)
- **75%**: Good (acceptable for most use cases)
- **<50%**: Poor (reconsider hedge strategy)

### Sharpe Ratio

Risk-adjusted returns:
```
SR = (Mean Return - Risk-Free Rate) / Std Dev of Returns
```

### Maximum Drawdown

Largest peak-to-trough decline:
```
MDD = (Trough - Peak) / Peak
```

### Basis Risk

Difference between spot and futures:
```
Basis = Futures Price - Spot Price
```

**Contango**: Basis > 0 (futures > spot)
**Backwardation**: Basis < 0 (futures < spot)

## Advanced Topics

### Roll Yield

When rolling futures contracts, you gain/lose based on basis:

```ocaml
let roll_pnl = Futures.calculate_roll_yield
  ~old_futures:{ futures_price = 1.1050; ... }
  ~new_futures:{ futures_price = 1.1020; ... }
  ~contracts_held:10
in
Printf.printf "Roll yield: $%.2f\n" roll_pnl
```

### SPAN Margin Methodology

CME uses Standard Portfolio Analysis of Risk (SPAN) for margin:

```ocaml
let margin = Margin.calculate_initial_margin
  ~spec:Types.cme_eur_usd
  ~position:10
  ~futures_price:1.10
in
Printf.printf "Initial margin required: $%.2f\n" margin
```

### Cross-Hedging

Hedge one currency with another (e.g., hedge NOK with EUR):

```
Optimal Ratio = (ρ_{NOK,EUR} × σ_NOK) / σ_EUR
```

Where correlation and volatilities are estimated from historical data.

## Dependencies

- **OCaml**: >= 4.14
- **Dune**: >= 3.0
- **Python**: >= 3.8
- **Python packages**: pandas, numpy, matplotlib, yfinance

Python dependencies are managed via `uv sync` in the Docker container.

## Testing

Run all tests:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec test_fx_hedging"
```

**Native:**
```bash
eval $(opam env) && dune exec test_fx_hedging
```

**Tests cover**:
- Forward pricing (CIP validation)
- Futures pricing and basis calculations
- Black-76 option pricing and Greeks
- Hedge ratio optimization
- Margin calculations
- Portfolio exposure analysis

## License

MIT

## Contributing

Contributions welcome! Please ensure:
- Tests pass: `docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec test_fx_hedging"` (or natively: `eval $(opam env) && dune exec test_fx_hedging`)
- Code builds: `docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build pricing/fx_hedging"` (or natively: `eval $(opam env) && dune build pricing/fx_hedging`)
- Documentation updated for new features

## Support

For issues or questions:
- Open an issue on GitHub
- Check PLAN.md for mathematical details
- Review test cases for usage examples

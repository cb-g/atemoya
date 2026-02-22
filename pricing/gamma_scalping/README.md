# Gamma Scalping - Volatility Trading Strategy

A complete implementation of gamma scalping strategies with delta-hedging, P&L attribution, and multiple hedging algorithms.

## Overview

**Gamma scalping** is an options trading strategy where you:
1. **Buy options** (long gamma) - typically straddles or strangles
2. **Continuously delta-hedge** by trading the underlying stock
3. **Profit from realized volatility** exceeding the implied volatility you paid
4. **Manage theta decay** - the race between gamma profit and time decay

**Key Equation**:
```
Total P&L = Gamma P&L + Theta P&L + Vega P&L - Transaction Costs

Profitable if: Realized Vol > Implied Vol (paid at entry)
```

## Features

- **Accurate Black-Scholes pricing and Greeks**
- **Three position types**: Straddle, Strangle, Single Option
- **Four hedging strategies**: Delta Threshold, Time-Based, Hybrid, Vol-Adaptive
- **Complete P&L attribution**: Gamma, Theta, Vega breakdown
- **Intraday simulation engine** with minute-level backtesting
- **Rich visualizations**: P&L charts, hedge timing, Greeks evolution
- **Performance metrics**: Sharpe ratio, max drawdown, win rate

## Architecture

```
gamma_scalping/
├── PLAN.md                      # Detailed mathematical specification
├── README.md                    # This file
├── ocaml/                       # Core simulation engine (OCaml)
│   ├── lib/
│   │   ├── types.ml             # Core data structures
│   │   ├── pricing.ml           # Black-Scholes pricing & Greeks
│   │   ├── positions.ml         # Straddle, strangle constructors
│   │   ├── hedging.ml           # 4 hedging strategies
│   │   ├── pnl_attribution.ml   # Gamma/theta/vega breakdown
│   │   ├── simulation.ml        # Intraday simulation engine
│   │   └── io.ml                # CSV I/O
│   ├── bin/
│   │   └── main.ml              # CLI
│   └── test/
│       └── test_gamma_scalping.ml
├── python/
│   ├── fetch/
│   │   └── fetch_intraday.py    # Download minute-level data (IBKR/yfinance)
│   └── viz/
│       └── plot_pnl.py          # P&L visualization
├── data/                         # Input data (price data)
└── output/                       # Simulation results
```

## Quickstart

### Prerequisites

- **OCaml**: OPAM 2.x with Dune
- **Python**: uv package manager
- **Data source**: yfinance (default), IBKR (if available)

### 1. Build the OCaml Simulation Engine

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build pricing/gamma_scalping"
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest pricing/gamma_scalping"
```

**Native:**
```bash
eval $(opam env) && dune build pricing/gamma_scalping
eval $(opam env) && dune runtest pricing/gamma_scalping
```

### 2. Fetch Intraday Price Data

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker SPY"
```

**Native:**
```bash
uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker SPY
```

This downloads 5-minute bars for SPY (last 5 days) and saves to `pricing/gamma_scalping/data/SPY_intraday.csv`.

### 3. Run Gamma Scalping Simulation

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec gamma_scalping -- \
  -ticker SPY \
  -position straddle \
  -strike 0 \
  -expiry 30 \
  -iv 0.18 \
  -strategy threshold \
  -threshold 0.10"
```

**Native:**
```bash
eval $(opam env) && dune exec gamma_scalping -- \
  -ticker SPY \
  -position straddle \
  -strike 0 \
  -expiry 30 \
  -iv 0.18 \
  -strategy threshold \
  -threshold 0.10
```

### 4. Visualize Results

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/gamma_scalping/python/viz/plot_pnl.py --ticker SPY"
```

**Native:**
```bash
uv run pricing/gamma_scalping/python/viz/plot_pnl.py --ticker SPY
```

Generates:
- `output/plots/SPY_pnl_attribution.png` - 4-panel P&L analysis
- `output/plots/SPY_summary_metrics.png` - Performance summary

## Position Types

### 1. Straddle (ATM Call + ATM Put)

**Best for**: High expected realized vol, uncertain direction

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec gamma_scalping -- \
  -ticker SPY -position straddle -strike 500 -expiry 30 -iv 0.18"
```

**Native:**
```bash
eval $(opam env) && dune exec gamma_scalping -- \
  -ticker SPY -position straddle -strike 500 -expiry 30 -iv 0.18
```

**Characteristics**:
- Maximum gamma near ATM
- High theta decay
- Delta-neutral at inception

### 2. Strangle (OTM Call + OTM Put)

**Best for**: Expecting big moves but want lower cost

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec gamma_scalping -- \
  -ticker SPY -position strangle \
  -call-strike 510 -put-strike 490 \
  -expiry 30 -iv 0.18"
```

**Native:**
```bash
eval $(opam env) && dune exec gamma_scalping -- \
  -ticker SPY -position strangle \
  -call-strike 510 -put-strike 490 \
  -expiry 30 -iv 0.18
```

**Characteristics**:
- Lower gamma than straddle
- Lower theta decay (cheaper entry)
- Requires larger moves to profit

### 3. Single Option (Call or Put)

**Best for**: Volatility play with directional opinion

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec gamma_scalping -- \
  -ticker SPY -position call -strike 500 -expiry 30 -iv 0.18"
```

**Native:**
```bash
eval $(opam env) && dune exec gamma_scalping -- \
  -ticker SPY -position call -strike 500 -expiry 30 -iv 0.18
```

## Hedging Strategies

### 1. Delta Threshold Rebalancing

**Rule**: Rehedge when |delta| > threshold

```bash
-strategy threshold -threshold 0.10
```

**Pros**: Adapts to market movement
**Cons**: Can over-trade in choppy markets

### 2. Time-Based Rebalancing

**Rule**: Rehedge at fixed intervals

```bash
-strategy time -interval 240  # every 4 hours
```

**Pros**: Predictable transaction costs
**Cons**: May miss optimal opportunities

### 3. Hybrid (Threshold + Time)

**Rule**: Rehedge if threshold OR time interval

```bash
-strategy hybrid -threshold 0.10 -interval 240
```

**Best practice**: Balanced approach

### 4. Realized Vol-Adaptive

**Rule**: Adjust hedging frequency based on realized vol

```bash
-strategy vol-adaptive
```

**Rationale**: Hedge more when gamma opportunities are ripe

## Expected Performance

Based on academic literature and practitioner experience:

| Metric | Straddle | Strangle | Notes |
|--------|----------|----------|-------|
| **Sharpe Ratio** | 0.8 - 1.2 | 0.6 - 1.0 | Depends on RV - IV edge |
| **Annualized Return** | 8% - 15% | 6% - 12% | Assuming RV > IV |
| **Win Rate** | 45% - 55% | 40% - 50% | Many small wins, few big losses |
| **Max Drawdown** | 20% - 30% | 15% - 25% | Can be severe if IV collapses |

**Critical Success Factors**:
1. Realized vol > Implied vol at entry
2. Low transaction costs (tight spreads)
3. Optimal hedging frequency
4. Avoid gamma scalping when IV is low

## Mathematical Background

### Black-Scholes Greeks

```
Call Price: C = S*e^(-qT)*N(d1) - K*e^(-rT)*N(d2)
Put Price:  P = K*e^(-rT)*N(-d2) - S*e^(-qT)*N(-d1)

Delta:  dV/dS
  call = e^(-qT)*N(d1)
  put  = e^(-qT)*(N(d1) - 1)

Gamma:  d2V/dS2
  = e^(-qT)*n(d1) / (S*sigma*sqrt(T))

Theta:  -dV/dt (per day)
Vega:   dV/dsigma (per 1% vol)
Rho:    dV/dr (per 1% rate)
```

### Gamma P&L

When delta-hedged, profit from stock movement:

```
Gamma P&L = 0.5 * Gamma * (dS)^2
```

**Always positive** when long gamma (long options)

### Break-Even Condition

```
Profitable if: Realized Vol > Implied Vol at entry

Sum(Gamma P&L) > |Sum(Theta P&L)| + Sum(Transaction Costs)
```

## Testing

Run the test suite:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest pricing/gamma_scalping"
```

**Native:**
```bash
eval $(opam env) && dune runtest pricing/gamma_scalping
```

**Tests include**:
- Black-Scholes pricing accuracy
- Put-call parity verification
- Greeks calculation (delta, gamma, theta, vega, rho)
- Straddle construction (delta-neutral check)
- Hedging strategy logic

## Advanced Usage

### Custom Configuration

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec gamma_scalping -- \
  -ticker AAPL \
  -position straddle \
  -strike 180 \
  -expiry 45 \
  -iv 0.25 \
  -strategy hybrid \
  -threshold 0.08 \
  -interval 180 \
  -cost-bps 3.0 \
  -rate 0.05 \
  -contracts 10"
```

**Native:**
```bash
eval $(opam env) && dune exec gamma_scalping -- \
  -ticker AAPL \
  -position straddle \
  -strike 180 \
  -expiry 45 \
  -iv 0.25 \
  -strategy hybrid \
  -threshold 0.08 \
  -interval 180 \
  -cost-bps 3.0 \
  -rate 0.05 \
  -contracts 10
```

### Fetch Different Data Intervals

**Docker:**
```bash
# 1-minute bars (7 days of history)
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker AAPL --interval 1m --days 7"

# 15-minute bars (30 days of history)
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker QQQ --interval 15m --days 30"
```

**Native:**
```bash
# 1-minute bars (7 days of history)
uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker AAPL --interval 1m --days 7

# 15-minute bars (30 days of history)
uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker QQQ --interval 15m --days 30
```

## Files Generated

After running a simulation, the following files are created:

```
output/
├── SPY_simulation.csv          # Summary metrics
├── SPY_pnl_attribution.csv     # Full P&L timeseries
├── SPY_hedge_log.csv           # Each hedge executed
└── plots/
    ├── SPY_pnl_attribution.png # 4-panel P&L analysis
    └── SPY_summary_metrics.png # Performance summary
```

## Troubleshooting

### "No data found for ticker"

Make sure you've run the data fetching script:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker <TICKER>"
```

**Native:**
```bash
uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker <TICKER>
```

### "File not found" errors

Ensure you're running commands from the project root and that all output directories exist.

### Build errors

Make sure the Docker container is running:
```bash
docker compose up -d
```

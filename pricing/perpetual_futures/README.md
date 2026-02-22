# Perpetual Futures - No-Arbitrage Pricing of Perpetual Futures and Everlasting Options

Implements the no-arbitrage pricing framework from Ackerer, Hugonnier, and Jermann (2025) for linear, inverse, and quanto perpetual futures contracts, plus closed-form everlasting option pricing. Compares theoretical prices against live exchange data to identify arbitrage signals.

## Overview

- Closed-form pricing for linear, inverse, and quanto perpetual futures contracts
- Everlasting option pricing (calls and puts) with delta computation via the AHJ ODE solution
- Arbitrage detection: compares theoretical fair value against live market data from Binance, Deribit, and Bybit
- Funding rate analysis: fair funding rate computation and perfect anchoring interest factor (iota)

## Architecture

```
perpetual_futures/
├── ocaml/
│   ├── bin/main.ml              # CLI: futures pricing, option pricing, grid mode
│   ├── lib/
│   │   ├── types.ml             # Contract types, currency pairs, market data
│   │   ├── pricing.ml           # Linear/inverse/quanto futures formulas
│   │   ├── everlasting.ml       # Everlasting call/put pricing and delta
│   │   └── io.ml                # JSON I/O, pricing dashboard, analysis output
│   └── test/
│       └── test_perpetual_futures.ml
├── python/
│   ├── fetch/
│   │   └── fetch_perp_data.py   # Fetch live perp data from Binance/Deribit/Bybit
│   └── viz/
│       └── plot_perpetual.py    # Basis analysis, price comparison, arbitrage signal
├── data/                        # Market data JSON
└── output/                      # Analysis JSON and plots
```

## Quickstart

### 1. Build

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build pricing/perpetual_futures"
```

**Native:**
```bash
eval $(opam env) && dune build pricing/perpetual_futures
```

### 2. Fetch Data

Fetch live perpetual futures market data from an exchange:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/perpetual_futures/python/fetch/fetch_perp_data.py --symbol BTCUSDT --exchange binance"
```

**Native:**
```bash
uv run pricing/perpetual_futures/python/fetch/fetch_perp_data.py --symbol BTCUSDT --exchange binance
```

Supported exchanges: `binance`, `deribit`, `bybit`. Supported symbols: `BTCUSDT`, `ETHUSDT`, etc.

### 3. Run Analysis

**Price a perpetual future from parameters:**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec perpetual_futures -- --spot 50000 --kappa 0.001 --type linear --r_a 0.05 --r_b 0.0"
```

**Native:**
```bash
eval $(opam env) && dune exec perpetual_futures -- --spot 50000 --kappa 0.001 --type linear --r_a 0.05 --r_b 0.0
```

**Analyze against live market data:**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec perpetual_futures -- --data pricing/perpetual_futures/data/market_data.json --kappa 0.001 --output pricing/perpetual_futures/output/analysis.json"
```

**Native:**
```bash
eval $(opam env) && dune exec perpetual_futures -- --data pricing/perpetual_futures/data/market_data.json --kappa 0.001 --output pricing/perpetual_futures/output/analysis.json
```

**Price an everlasting option:**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec perpetual_futures -- --option call --strike 50000 --spot 48000 --sigma 0.8 --kappa 0.001"
```

**Native:**
```bash
eval $(opam env) && dune exec perpetual_futures -- --option call --strike 50000 --spot 48000 --sigma 0.8 --kappa 0.001
```

**Generate an everlasting option price grid:**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec perpetual_futures -- --grid --strike 50000 --spot-min 30000 --spot-max 70000 --n-points 200"
```

**Native:**
```bash
eval $(opam env) && dune exec perpetual_futures -- --grid --strike 50000 --spot-min 30000 --spot-max 70000 --n-points 200
```

CLI options:

| Flag | Description |
|------|-------------|
| `--spot <price>` | Spot price |
| `--kappa <rate>` | Premium rate / anchoring intensity (default: 0.001) |
| `--iota <value>` | Interest factor (default: 0.0) |
| `--r_a <rate>` | Quote currency risk-free rate (default: 0.05) |
| `--r_b <rate>` | Base currency risk-free rate (default: 0.0) |
| `--sigma <vol>` | Volatility (default: 0.8) |
| `--type <type>` | Contract type: `linear`, `inverse`, `quanto` |
| `--data <file>` | Market data JSON file (for arbitrage analysis) |
| `--output <file>` | Output JSON file |
| `--option <call\|put>` | Price an everlasting option |
| `--strike <K>` | Option strike price |
| `--grid` | Generate option price grid over spot range |
| `--spot-min <min>` | Min spot for grid mode |
| `--spot-max <max>` | Max spot for grid mode |
| `--n-points <n>` | Number of grid points (default: 100) |

### 4. Visualize

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/perpetual_futures/python/viz/plot_perpetual.py --input pricing/perpetual_futures/output/analysis.json"
```

**Native:**
```bash
uv run pricing/perpetual_futures/python/viz/plot_perpetual.py --input pricing/perpetual_futures/output/analysis.json
```

## Output

- `output/analysis.json` -- Market vs. theoretical comparison with arbitrage signal
- `output/option_grid.csv` -- Everlasting call/put prices across a spot range
- `output/plots/<SYMBOL>_perpetual_analysis.png` -- 2x2 dashboard: basis analysis, price comparison, arbitrage signal gauge, summary table

## Testing

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest pricing/perpetual_futures"
```

**Native:**
```bash
eval $(opam env) && dune runtest pricing/perpetual_futures
```

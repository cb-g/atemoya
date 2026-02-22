# Liquidity Analysis - Multi-Ticker Liquidity Scoring and Volume Signal Detection

Computes liquidity metrics (Amihud illiquidity ratio, turnover, spread proxy, volume volatility) and predictive volume-based signals (OBV divergence, volume surges, smart money flow) for a set of tickers. Ranks tickers by a composite liquidity score (0--100) and generates a composite predictive signal.

## Overview

- Amihud illiquidity ratio, turnover ratio, relative volume, volume volatility, and bid-ask spread proxy
- On-Balance Volume (OBV) with divergence detection, volume surge detection, and smart money flow estimation
- Composite liquidity score (0--100) with tier classification (Excellent/Good/Fair/Poor/Very Poor)
- Composite signal score combining OBV, surge magnitude, volume trend, volume-price correlation, and smart money flow

## Architecture

```
liquidity/
├── ocaml/
│   ├── bin/main.ml              # CLI entry point
│   ├── lib/
│   │   ├── types.ml             # OHLCV, liquidity_metrics, signal_metrics types
│   │   ├── scoring.ml           # Amihud, turnover, spread proxy, liquidity score
│   │   ├── signals.ml           # OBV, volume surge, smart money, composite signal
│   │   ├── analysis.ml          # Orchestration: analyze all tickers, sort, print
│   │   └── io.ml                # JSON I/O (Yojson)
│   └── test/
│       └── test_liquidity.ml    # Unit tests (Alcotest)
├── python/
│   ├── fetch/
│   │   └── fetch_liquidity_data.py  # Fetch OHLCV + shares outstanding via yfinance
│   └── viz/
│       └── plot_liquidity.py        # Dashboard and single-ticker detail plots
├── data/                        # Input market data JSON
└── output/                      # Results JSON and plots
```

## Quickstart

### 1. Build

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build pricing/liquidity"
```

**Native:**
```bash
eval $(opam env) && dune build pricing/liquidity
```

### 2. Fetch Data

Fetch OHLCV data for one or more tickers:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/liquidity/python/fetch/fetch_liquidity_data.py --tickers NVDA,SPY,TAC,GME"
```

**Native:**
```bash
uv run pricing/liquidity/python/fetch/fetch_liquidity_data.py --tickers NVDA,SPY,TAC,GME
```

Or fetch a single ticker:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/liquidity/python/fetch/fetch_liquidity_data.py --ticker NVDA --period 6mo"
```

**Native:**
```bash
uv run pricing/liquidity/python/fetch/fetch_liquidity_data.py --ticker NVDA --period 6mo
```

### 3. Run Analysis

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec liquidity_exe -- --data pricing/liquidity/data/market_data.json --output pricing/liquidity/output/liquidity_results.json --window 20"
```

**Native:**
```bash
eval $(opam env) && dune exec liquidity_exe -- --data pricing/liquidity/data/market_data.json --output pricing/liquidity/output/liquidity_results.json --window 20
```

CLI options:

| Flag | Description |
|------|-------------|
| `--data <file>` | Input market data JSON file (required) |
| `--output <file>` | Save results to JSON file |
| `--window <n>` | Analysis window in days (default: 20) |
| `--json` | Output JSON only, suppress console output |

### 4. Visualize

Plot the multi-ticker liquidity dashboard:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/liquidity/python/viz/plot_liquidity.py --output-dir pricing/liquidity/output"
```

**Native:**
```bash
uv run pricing/liquidity/python/viz/plot_liquidity.py --output-dir pricing/liquidity/output
```

Plot a detailed single-ticker chart (price, volume, OBV, accumulation/distribution):

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/liquidity/python/viz/plot_liquidity.py --ticker NVDA --output-dir pricing/liquidity/output"
```

**Native:**
```bash
uv run pricing/liquidity/python/viz/plot_liquidity.py --ticker NVDA --output-dir pricing/liquidity/output
```

## Output

- `output/liquidity_results.json` -- Per-ticker liquidity scores, metrics, and signals
- `output/liquidity_dashboard.png` -- 2x2 dashboard: liquidity ranking, relative volume, signal strength, summary table
- `output/<TICKER>_liquidity_detail.png` -- Single-ticker chart: price, volume with surge markers, OBV, accumulation/distribution

## Testing

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest pricing/liquidity"
```

**Native:**
```bash
eval $(opam env) && dune runtest pricing/liquidity
```

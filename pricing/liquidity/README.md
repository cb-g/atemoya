# Liquidity Analysis - Multi-Ticker Liquidity Scoring and Volume Signal Detection

Computes liquidity metrics (Amihud illiquidity ratio, turnover, spread proxy, volume volatility) and predictive volume-based signals (OBV divergence, volume surges, smart money flow) for a set of tickers. Ranks tickers by a composite liquidity score (0--100) and generates a composite predictive signal.

## Overview

- Amihud illiquidity ratio, turnover ratio, relative volume, volume volatility, and bid-ask spread proxy
- On-Balance Volume (OBV) with divergence detection, volume surge detection, and smart money flow estimation
- Composite liquidity score (0--100) with tier classification (Excellent/Good/Fair/Poor/Very Poor)
- Composite signal score combining OBV, surge magnitude, volume trend, volume-price correlation, and smart money flow

## Optionable Screening Pipeline

Discovers and filters the full CBOE optionable universe down to tickers suitable for daily options chain collection by Skew Trading, Variance Swaps, and Pre-Earnings Straddle modules.

```
CBOE optionable list (5297 tickers)
  │
  ▼  Gate 1: filter_liquid_tickers.py (stock liquidity score >= 75)
liquid_tickers.txt (~612 tickers)
  │
  ▼  Gate 2: filter_liquid_options.py (>= 3 expiries, >= 5 OTM strikes)
liquid_options.txt (subset with SVI-calibratable chains)
  │
  ▼  subset_by_price.py --segments
liquid_options_1_to_10_USD.txt, ..., liquid_options_above_200_USD.txt
```

Both gates are resumable (kill and rerun to continue) and save progress after each batch. Gate 2 thresholds match the SVI calibrator requirements in the skew trading module.

Downstream collectors accept tickers via `--tickers all_liquid` (reads `liquid_options.txt`) or `--tickers path/to/segment.txt`.

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
│   │   ├── fetch_liquidity_data.py     # Fetch OHLCV + shares outstanding via yfinance
│   │   ├── fetch_optionable_tickers.py # Fetch CBOE optionable list
│   │   ├── filter_liquid_tickers.py    # Gate 1: stock liquidity filter
│   │   ├── filter_liquid_options.py    # Gate 2: option chain coverage filter
│   │   └── subset_by_price.py          # Segment tickers by underlying price
│   └── viz/
│       └── plot_liquidity.py           # Dashboard and single-ticker detail plots
├── data/                        # Input market data, ticker lists, segments
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

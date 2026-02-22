# Analyst Upside - Price Target Scanner

Scans analyst consensus price targets across stock universes to identify the largest upside opportunities. Ranks stocks by upside percentage, filters by analyst coverage, and maps conviction via dispersion analysis.

## Overview

- Scans predefined universes (S&P 500 top 50, NASDAQ 30, Dow 30, sector/thematic baskets, market-cap tiers)
- Filters by minimum analyst count and minimum upside threshold
- Computes analyst dispersion (disagreement) and 52-week range positioning
- Produces a conviction map (dispersion vs upside scatter) for identifying high-conviction picks

## Architecture

```
analyst_upside/
├── python/
│   ├── fetch_targets.py      # Fetch + scan (combined)
│   └── viz/
│       └── plot_upside.py     # Visualization
├── data/
│   └── targets.json           # Cached scan results
└── output/
    ├── targets.json           # Filtered results
    ├── analyst_upside.png     # Upside bars + conviction map
    └── analyst_upside.svg
```

## Quickstart

This is a Python-only module (no OCaml build step).

### 1. Scan a Universe

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/analyst_upside/python/fetch_targets.py --universe sp50 --min-analysts 10 --output valuation/analyst_upside/output/targets.json"
```

**Native:**
```bash
uv run valuation/analyst_upside/python/fetch_targets.py --universe sp50 --min-analysts 10 --output valuation/analyst_upside/output/targets.json
```

### 2. Scan Custom Tickers

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/analyst_upside/python/fetch_targets.py --tickers AAPL,NVDA,MSFT,GOOGL --output valuation/analyst_upside/output/targets.json"
```

**Native:**
```bash
uv run valuation/analyst_upside/python/fetch_targets.py --tickers AAPL,NVDA,MSFT,GOOGL --output valuation/analyst_upside/output/targets.json
```

### 3. Visualize

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/analyst_upside/python/viz/plot_upside.py --input valuation/analyst_upside/output/targets.json --output-dir valuation/analyst_upside/output"
```

**Native:**
```bash
uv run valuation/analyst_upside/python/viz/plot_upside.py --input valuation/analyst_upside/output/targets.json --output-dir valuation/analyst_upside/output
```

## CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--tickers`, `-t` | Comma-separated list of tickers | -- |
| `--universe`, `-u` | Predefined universe (sp50, nasdaq30, dow30, tech, healthcare, industrials, consumer, financials, energy, ai, clean_energy, div_aristocrats, income, midcap, smallcap) | Combined S&P 50 + NASDAQ 30 |
| `--min-analysts` | Minimum number of analysts | 5 |
| `--min-upside` | Minimum upside % to display | 0 |
| `--top` | Show top N results | 50 |
| `--output`, `-o` | Output JSON file | -- |

## Output

- `output/targets.json` -- Scan results with upside, dispersion, and analyst counts
- `output/analyst_upside.png` -- Two-panel figure: upside bars by recommendation + conviction scatter
- `output/analyst_upside.svg` -- Vector version of the above

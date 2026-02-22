# Macro Dashboard - Macroeconomic Regime Classifier and Investment Dashboard

Classifies the current macroeconomic environment using FRED and market data, then generates investment positioning recommendations. The OCaml engine scores economic cycle phase, yield curve state, inflation regime, labor market conditions, risk sentiment, and Fed policy stance to produce actionable sector tilts and risk assessments.

## Overview

- Fetches 30+ economic indicators from FRED (interest rates, inflation, employment, growth, housing, leading indicators) and 12 market tickers via yfinance
- Rule-based classifier determines cycle phase (Early/Mid/Late/Recession), yield curve state, inflation regime, labor market health, risk sentiment, and Fed stance
- Estimates recession probability using yield curve inversion, labor deterioration, GDP weakness, and VIX signals
- Generates investment implications: equity/bond outlook, sector tilts by cycle phase, risk level, and key risks
- Produces a 4-panel visual dashboard with regime indicators, interest rates, market metrics, and positioning

## Architecture

```
macro_dashboard/
├── ocaml/
│   ├── bin/main.ml              # CLI: loads data, classifies, prints dashboard
│   ├── lib/
│   │   ├── types.ml             # Macro snapshot, environment, and implication types
│   │   ├── classifier.ml        # Yield curve, inflation, labor, risk, Fed, cycle classifiers
│   │   └── io.ml                # JSON parsing (FRED series + market tickers) and output
│   └── test/
│       └── test_macro_dashboard.ml
├── python/
│   ├── fetch/
│   │   └── fetch_macro.py       # Fetches FRED series and yfinance market data
│   └── viz/
│       └── plot_dashboard.py    # 4-panel regime/rates/market/positioning dashboard
├── data/
│   └── macro_data.json          # Fetched FRED + market data
└── output/
    ├── environment.json         # Classified environment from OCaml engine
    ├── macro_dashboard.png      # Dashboard visualization
    └── macro_dashboard.svg
```

## Quickstart

### 1. Build

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build alternative/macro_dashboard"
```

**Native:**
```bash
eval $(opam env) && dune build alternative/macro_dashboard
```

### 2. Fetch Data

Requires a FRED API key (free at https://fred.stlouisfed.org/docs/api/api_key.html). Set `FRED_API_KEY` in `.env` or pass via `--api-key`.

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/macro_dashboard/python/fetch/fetch_macro.py"
```

**Native:**
```bash
uv run alternative/macro_dashboard/python/fetch/fetch_macro.py
```

### 3. Run Classifier

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec macro_dashboard -- alternative/macro_dashboard/data/macro_data.json --output alternative/macro_dashboard/output/environment.json"
```

**Native:**
```bash
eval $(opam env) && dune exec macro_dashboard -- alternative/macro_dashboard/data/macro_data.json --output alternative/macro_dashboard/output/environment.json
```

### 4. Visualize

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/macro_dashboard/python/viz/plot_dashboard.py"
```

**Native:**
```bash
uv run alternative/macro_dashboard/python/viz/plot_dashboard.py
```

## Output

- `output/environment.json` -- classified regime, rates, inflation, employment, market metrics, and investment implications
- `output/macro_dashboard.png` -- 4-panel dashboard: economic regime, investment positioning, interest rates, market indicators
- `output/macro_dashboard.svg` -- vector version of the dashboard

## Data Sources

This product uses the FRED API but is not endorsed or certified by the Federal Reserve Bank of St. Louis. Data sources include the Federal Reserve Board, BLS, BEA, and U.S. Census Bureau, via FRED. No FRED data is stored, cached, or redistributed. Market data via yfinance.

## Testing

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest alternative/macro_dashboard"
```

**Native:**
```bash
eval $(opam env) && dune runtest alternative/macro_dashboard
```

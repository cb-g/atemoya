# Tail Risk Forecast - HAR-RV Volatility Forecasting with Jump Detection and VaR/ES

Forecasts next-day tail risk using the Heterogeneous Autoregressive Realized Variance (HAR-RV) model estimated on intraday data. Detects variance jumps via threshold-based z-score detection and produces jump-adjusted VaR and Expected Shortfall at the 95% and 99% confidence levels under a Student-t distribution.

## Overview

- Realized variance computation from 5-minute intraday log returns
- HAR-RV model: daily, weekly, and monthly RV components estimated via OLS
- Jump detection: rolling z-score threshold with configurable sensitivity
- VaR and Expected Shortfall under Student-t(6) distribution with jump premium adjustment

## Architecture

```
tail_risk_forecast/
├── ocaml/
│   ├── bin/main.ml              # CLI entry point
│   ├── lib/
│   │   ├── types.ml             # Intraday returns, daily RV, HAR coefficients, forecast
│   │   ├── realized_variance.ml # RV computation from intraday bars
│   │   ├── har_rv.ml            # HAR-RV model estimation and forecasting (OLS)
│   │   ├── jump_detection.ml    # Threshold-based variance jump detection
│   │   ├── var_forecast.ml      # VaR/ES under Normal and Student-t distributions
│   │   └── io.ml                # JSON I/O and console output formatting
│   └── test/
│       └── test_tail_risk_forecast.ml
├── python/
│   ├── fetch/
│   │   └── fetch_intraday.py    # Fetch 5m intraday data (IBKR/yfinance)
│   └── viz/
│       └── plot_forecast.py     # Risk gauge, volatility forecast, HAR coefficients dashboard
├── data/                        # Intraday data JSON
└── output/                      # Forecast JSON and plots
```

## Quickstart

### 1. Build

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build pricing/tail_risk_forecast"
```

**Native:**
```bash
eval $(opam env) && dune build pricing/tail_risk_forecast
```

### 2. Fetch Data

Fetch intraday data for a ticker (5-minute bars, up to 60 days via yfinance or 252 via IBKR):

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/tail_risk_forecast/python/fetch/fetch_intraday.py --ticker SPY --days 60"
```

**Native:**
```bash
uv run pricing/tail_risk_forecast/python/fetch/fetch_intraday.py --ticker SPY --days 60
```

Options: `--interval 5m`, `--provider ibkr` or `--provider yfinance`, `--days <n>`.

### 3. Run Analysis

Console output with full forecast:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec tail_risk_forecast -- --ticker SPY"
```

**Native:**
```bash
eval $(opam env) && dune exec tail_risk_forecast -- --ticker SPY
```

Save as JSON:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec tail_risk_forecast -- --ticker SPY --json"
```

**Native:**
```bash
eval $(opam env) && dune exec tail_risk_forecast -- --ticker SPY --json
```

CLI options:

| Flag | Description |
|------|-------------|
| `--ticker <SYMBOL>` | Ticker symbol (looks for `data/intraday_<SYMBOL>.json`) |
| `--data <file>` | Explicit path to intraday data JSON |
| `--json` | Write results to `output/forecast_<TICKER>.json` |
| `--jump-threshold <n>` | Jump detection threshold in std devs (default: 2.5) |

### 4. Visualize

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/tail_risk_forecast/python/viz/plot_forecast.py --input pricing/tail_risk_forecast/output/forecast_SPY.json"
```

**Native:**
```bash
uv run pricing/tail_risk_forecast/python/viz/plot_forecast.py --input pricing/tail_risk_forecast/output/forecast_SPY.json
```

## Output

- `output/forecast_<TICKER>.json` -- HAR model coefficients, VaR/ES forecasts, jump intensity
- `output/plots/<TICKER>_tail_risk.png` -- 2x2 dashboard: VaR/ES risk gauge, volatility forecast, HAR-RV coefficients, analysis summary

## Testing

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest pricing/tail_risk_forecast"
```

**Native:**
```bash
eval $(opam env) && dune runtest pricing/tail_risk_forecast
```

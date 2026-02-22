# Market Regime Forecast - Multi-Model Regime Classification for Equities and Income ETFs

Classifies the current market regime (trend: Bull/Bear/Sideways; volatility: High/Normal/Low) using four complementary statistical models, then synthesizes a consensus view. Includes covered-call suitability scoring for income ETF positioning.

## Overview

- Four model backends: Basic (GARCH + HMM), Markov-Switching GARCH, Bayesian Online Changepoint Detection (BOCPD), and Gaussian Process regression
- Trend classification via 3-state Hidden Markov Model or GP posterior mean; volatility classification via GARCH percentiles or MS-GARCH regime probabilities
- Covered-call suitability rating (1--5 stars) with strategy recommendations per regime combination
- Multi-model consensus visualization with agreement metrics and per-model diagnostics

## Architecture

```
market_regime_forecast/
├── ocaml/
│   ├── bin/main.ml              # CLI: model selection, I/O, printing
│   ├── lib/
│   │   ├── types.ml             # Regime types, GARCH/HMM params, config
│   │   ├── garch.ml             # GARCH(1,1) via Nelder-Mead MLE
│   │   ├── hmm.ml               # 3-state HMM: Baum-Welch, Viterbi
│   │   ├── ms_garch.ml          # Markov-Switching GARCH (regime-dependent params)
│   │   ├── bocpd.ml             # Bayesian Online Changepoint Detection
│   │   ├── gp.ml                # Gaussian Process regression (RBF/Matern kernels)
│   │   ├── classifier.ml        # Combined classification + covered-call scoring
│   │   └── io.ml                # JSON I/O, console formatting
│   └── test/
│       └── test_market_regime_forecast.ml
├── python/
│   ├── fetch/
│   │   ├── fetch_prices.py      # Fetch historical prices (IBKR/yfinance)
│   │   └── fetch_earnings.py    # Fetch upcoming earnings dates
│   ├── viz/
│   │   └── plot_regime.py       # Multi-model comparison dashboard
│   ├── full_analysis.py         # Income ETF regime + earnings combined view
│   └── full_etf_analysis.py     # Full ETF analysis with underlying mapping
├── data/                        # Price data JSON files
└── output/                      # Forecast JSON and plots
```

## Quickstart

### 1. Build

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build pricing/market_regime_forecast"
```

**Native:**
```bash
eval $(opam env) && dune build pricing/market_regime_forecast
```

### 2. Fetch Data

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/market_regime_forecast/python/fetch/fetch_prices.py --ticker SPY --years 5"
```

**Native:**
```bash
uv run pricing/market_regime_forecast/python/fetch/fetch_prices.py --ticker SPY --years 5
```

### 3. Run Analysis

Run all four models and save their outputs:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec market_regime_forecast -- pricing/market_regime_forecast/data/spy_prices.json --model basic --output pricing/market_regime_forecast/output/SPY_basic.json"
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec market_regime_forecast -- pricing/market_regime_forecast/data/spy_prices.json --model ms-garch --output pricing/market_regime_forecast/output/SPY_ms-garch.json"
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec market_regime_forecast -- pricing/market_regime_forecast/data/spy_prices.json --model bocpd --output pricing/market_regime_forecast/output/SPY_bocpd.json"
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec market_regime_forecast -- pricing/market_regime_forecast/data/spy_prices.json --model gp --output pricing/market_regime_forecast/output/SPY_gp.json"
```

**Native:**
```bash
eval $(opam env) && dune exec market_regime_forecast -- pricing/market_regime_forecast/data/spy_prices.json --model basic --output pricing/market_regime_forecast/output/SPY_basic.json
eval $(opam env) && dune exec market_regime_forecast -- pricing/market_regime_forecast/data/spy_prices.json --model ms-garch --output pricing/market_regime_forecast/output/SPY_ms-garch.json
eval $(opam env) && dune exec market_regime_forecast -- pricing/market_regime_forecast/data/spy_prices.json --model bocpd --output pricing/market_regime_forecast/output/SPY_bocpd.json
eval $(opam env) && dune exec market_regime_forecast -- pricing/market_regime_forecast/data/spy_prices.json --model gp --output pricing/market_regime_forecast/output/SPY_gp.json
```

CLI options:

| Flag | Description |
|------|-------------|
| `<price_data.json>` | Input price data JSON file (positional, required) |
| `--model <type>` | Model type: `basic`, `ms-garch`, `bocpd`, or `gp` (default: basic) |
| `--output <file>` | Save forecast to JSON file |
| `--save-params` | Save fitted GARCH/HMM params for quick inference |
| `--quiet` | Suppress detailed console output |

### 4. Visualize

Generate a multi-model comparison dashboard:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/market_regime_forecast/python/viz/plot_regime.py --basic pricing/market_regime_forecast/output/SPY_basic.json --ms-garch pricing/market_regime_forecast/output/SPY_ms-garch.json --bocpd pricing/market_regime_forecast/output/SPY_bocpd.json --gp pricing/market_regime_forecast/output/SPY_gp.json --ticker SPY"
```

**Native:**
```bash
uv run pricing/market_regime_forecast/python/viz/plot_regime.py --basic pricing/market_regime_forecast/output/SPY_basic.json --ms-garch pricing/market_regime_forecast/output/SPY_ms-garch.json --bocpd pricing/market_regime_forecast/output/SPY_bocpd.json --gp pricing/market_regime_forecast/output/SPY_gp.json --ticker SPY
```

## Output

- `output/<TICKER>_basic.json` -- Basic model forecast (GARCH + HMM)
- `output/<TICKER>_ms-garch.json` -- MS-GARCH forecast with regime parameters and transition matrix
- `output/<TICKER>_bocpd.json` -- BOCPD forecast with run-length analysis and changepoints
- `output/<TICKER>_gp.json` -- GP forecast with kernel params and uncertainty quantification
- `output/<TICKER>_regime_analysis.png` -- 5-panel dashboard: 4 model panels + consensus overview

## Testing

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest pricing/market_regime_forecast"
```

**Native:**
```bash
eval $(opam env) && dune runtest pricing/market_regime_forecast
```

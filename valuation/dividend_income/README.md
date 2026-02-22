# Dividend Income - Safety-Scored Dividend Analysis

Evaluates dividend-paying stocks for income investors using dividend discount models (DDM), safety scoring, payout sustainability, and growth metrics. Classifies stocks from Dividend Kings down to No Streak and produces buy/hold/avoid signals.

## Overview

- Multi-model DDM valuation: Gordon Growth, two-stage, H-model, and yield-based
- Safety scoring across five dimensions: payout ratio, coverage, streak, balance sheet, stability
- Dividend status classification (King, Aristocrat, Achiever, Contender, Challenger)
- Yield tier bucketing and Chowder Number calculation for growth-plus-yield assessment

## Architecture

```
dividend_income/
├── ocaml/
│   ├── bin/main.ml                 # CLI
│   ├── lib/
│   │   ├── types.ml                # Core types
│   │   ├── ddm.ml                  # Dividend discount models
│   │   ├── dividend_metrics.ml     # Yield, payout, growth metrics
│   │   ├── safety_scoring.ml       # Safety score and signal
│   │   └── io.ml                   # JSON I/O and formatting
│   └── test/
│       └── test_dividend_income.ml
├── python/
│   ├── fetch/
│   │   └── fetch_dividend_data.py  # Fetch dividend history + fundamentals
│   └── viz/
│       └── plot_dividend.py        # 2x2 dashboard visualization
├── data/                           # Per-ticker dividend data JSON
└── output/                         # Results + plots
```

## Quickstart

### 1. Build

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build valuation/dividend_income"
```

**Native:**
```bash
eval $(opam env) && dune build valuation/dividend_income
```

### 2. Fetch Data

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/dividend_income/python/fetch/fetch_dividend_data.py --ticker KO"
```

**Native:**
```bash
uv run valuation/dividend_income/python/fetch/fetch_dividend_data.py --ticker KO
```

### 3. Run Analysis

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec dividend_income -- --ticker KO"
```

**Native:**
```bash
eval $(opam env) && dune exec dividend_income -- --ticker KO
```

Compare multiple tickers:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec dividend_income -- --tickers KO,PEP,JNJ,PG --compare"
```

**Native:**
```bash
eval $(opam env) && dune exec dividend_income -- --tickers KO,PEP,JNJ,PG --compare
```

### 4. Visualize

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/dividend_income/python/viz/plot_dividend.py --input valuation/dividend_income/output/dividend_result_KO.json"
```

**Native:**
```bash
uv run valuation/dividend_income/python/viz/plot_dividend.py --input valuation/dividend_income/output/dividend_result_KO.json
```

## CLI Options (OCaml)

| Flag | Description | Default |
|------|-------------|---------|
| `--ticker` | Single ticker to analyze | -- |
| `--tickers` | Comma-separated list of tickers | -- |
| `--data` | Data directory | `valuation/dividend_income/data` |
| `--output` | Output directory | `valuation/dividend_income/output` |
| `--python` | Python command to auto-fetch data | -- |
| `--compare` | Enable comparison mode | -- |
| `--required-return` | Required return for DDM | 0.08 |
| `--terminal-growth` | Terminal growth rate for DDM | 0.03 |

## Output

- `output/dividend_result_TICKER.json` -- Per-ticker analysis with DDM valuations and safety scores
- `output/dividend_comparison.json` -- Multi-ticker comparison summary
- `output/plots/TICKER_dividend_analysis.png` -- 2x2 dashboard: safety breakdown, yield comparison, growth trajectory, DDM valuation
- `output/plots/TICKER_dividend_analysis.svg` -- Vector version

## Testing

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest valuation/dividend_income"
```

**Native:**
```bash
eval $(opam env) && dune runtest valuation/dividend_income
```

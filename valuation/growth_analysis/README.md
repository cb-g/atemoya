# Growth Analysis - Revenue and Earnings Growth Scoring

Evaluates growth stocks across revenue acceleration, earnings momentum, margin trajectory, and capital efficiency. Classifies stocks from Hypergrowth to Declining and produces composite growth scores with Rule of 40 assessment.

## Overview

- Growth tier classification: Hypergrowth, High Growth, Moderate, Slow, No Growth, Declining
- Rule of 40 evaluation (revenue growth + profit margin) with tier bucketing
- Margin trajectory analysis: expanding, stable, or contracting operating leverage
- Composite scoring: revenue growth, earnings growth, margins, efficiency, quality

## Architecture

```
growth_analysis/
├── ocaml/
│   ├── bin/main.ml                # CLI
│   ├── lib/
│   │   ├── types.ml               # Core types (growth_data, metrics, scores, signals)
│   │   ├── growth_metrics.ml      # Growth metric calculations
│   │   ├── scoring.ml             # Scoring and comparison
│   │   └── io.ml                  # JSON I/O and formatting
│   └── test/
│       └── test_growth_analysis.ml
├── python/
│   ├── fetch/
│   │   └── fetch_growth_data.py   # Fetch revenue, earnings, margin data
│   └── viz/
│       └── plot_growth.py         # 2x2 dashboard visualization
├── data/                          # Per-ticker growth data JSON
└── output/                        # Results + plots
```

## Quickstart

### 1. Build

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build valuation/growth_analysis"
```

**Native:**
```bash
eval $(opam env) && dune build valuation/growth_analysis
```

### 2. Fetch Data

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/growth_analysis/python/fetch/fetch_growth_data.py --ticker PLTR"
```

**Native:**
```bash
uv run valuation/growth_analysis/python/fetch/fetch_growth_data.py --ticker PLTR
```

### 3. Run Analysis

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec growth_analysis -- --ticker PLTR"
```

**Native:**
```bash
eval $(opam env) && dune exec growth_analysis -- --ticker PLTR
```

Compare multiple tickers:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec growth_analysis -- --tickers PLTR,CRWD,NVDA,AMZN --compare"
```

**Native:**
```bash
eval $(opam env) && dune exec growth_analysis -- --tickers PLTR,CRWD,NVDA,AMZN --compare
```

### 4. Visualize

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/growth_analysis/python/viz/plot_growth.py --input valuation/growth_analysis/output/growth_result_PLTR.json"
```

**Native:**
```bash
uv run valuation/growth_analysis/python/viz/plot_growth.py --input valuation/growth_analysis/output/growth_result_PLTR.json
```

## CLI Options (OCaml)

| Flag | Description | Default |
|------|-------------|---------|
| `--ticker` | Single ticker to analyze | -- |
| `--tickers` | Comma-separated list of tickers | -- |
| `--data` | Data directory | `valuation/growth_analysis/data` |
| `--output` | Output directory | `valuation/growth_analysis/output` |
| `--python` | Python command to auto-fetch data | -- |
| `--compare` | Enable comparison mode | -- |

## Output

- `output/growth_result_TICKER.json` -- Per-ticker growth metrics, margin analysis, valuation, score, and signal
- `output/growth_comparison.json` -- Multi-ticker comparison ranked by growth score
- `output/plots/TICKER_growth_analysis.png` -- 2x2 dashboard: growth radar, Rule of 40 gauge, margin trajectory, score breakdown
- `output/plots/TICKER_growth_analysis.svg` -- Vector version

## Testing

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest valuation/growth_analysis"
```

**Native:**
```bash
eval $(opam env) && dune runtest valuation/growth_analysis
```

# ETF Analysis - Cost, Tracking, and Derivatives Scoring

Evaluates ETFs across cost efficiency, tracking quality, liquidity, and size. Includes specialized analysis for derivatives-based ETFs (covered call, buffer, volatility, put-write, leveraged) with capture ratio and distribution assessment.

## Overview

- Composite quality scoring: cost, tracking error, liquidity, and AUM tiers
- NAV premium/discount detection and bid-ask spread analysis
- Derivatives-specific analysis: covered call yield vs upside capture, buffer levels, vol decay
- Side-by-side comparison mode for competing ETFs with best-in-class picks

## Architecture

```
etf_analysis/
├── ocaml/
│   ├── bin/main.ml              # CLI
│   ├── lib/
│   │   ├── types.ml             # ETF data, scores, signals, derivatives types
│   │   ├── scoring.ml           # Quality scoring engine
│   │   ├── costs.ml             # Expense ratio analysis
│   │   ├── derivatives.ml       # Covered call, buffer, vol analysis
│   │   ├── premium_discount.ml  # NAV premium/discount
│   │   └── io.ml                # JSON I/O and formatting
│   └── test/
│       └── test_etf_analysis.ml
├── python/
│   ├── fetch/
│   │   └── fetch_etf_data.py    # Fetch ETF data via yfinance
│   └── viz/
│       └── plot_etf.py          # 2x2 dashboard visualization
├── data/                        # Per-ticker ETF data JSON
└── output/                      # Results + plots
```

## Quickstart

### 1. Build

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build valuation/etf_analysis"
```

**Native:**
```bash
eval $(opam env) && dune build valuation/etf_analysis
```

### 2. Fetch Data

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/etf_analysis/python/fetch/fetch_etf_data.py JEPI"
```

**Native:**
```bash
uv run valuation/etf_analysis/python/fetch/fetch_etf_data.py JEPI
```

With custom benchmark:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/etf_analysis/python/fetch/fetch_etf_data.py QYLD QQQ"
```

**Native:**
```bash
uv run valuation/etf_analysis/python/fetch/fetch_etf_data.py QYLD QQQ
```

### 3. Run Analysis (Single)

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec etf_analysis -- valuation/etf_analysis/data/etf_data_JEPI.json"
```

**Native:**
```bash
eval $(opam env) && dune exec etf_analysis -- valuation/etf_analysis/data/etf_data_JEPI.json
```

### 4. Run Analysis (Compare)

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec etf_analysis -- --compare valuation/etf_analysis/data/etf_data_JEPI.json valuation/etf_analysis/data/etf_data_JEPQ.json valuation/etf_analysis/data/etf_data_QYLD.json"
```

**Native:**
```bash
eval $(opam env) && dune exec etf_analysis -- --compare valuation/etf_analysis/data/etf_data_JEPI.json valuation/etf_analysis/data/etf_data_JEPQ.json valuation/etf_analysis/data/etf_data_QYLD.json
```

### 5. Visualize

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/etf_analysis/python/viz/plot_etf.py --input valuation/etf_analysis/output/etf_result_JEPI.json"
```

**Native:**
```bash
uv run valuation/etf_analysis/python/viz/plot_etf.py --input valuation/etf_analysis/output/etf_result_JEPI.json
```

## CLI Options (OCaml)

| Flag | Description | Default |
|------|-------------|---------|
| `<data_file>` | Single ETF data file to analyze | -- |
| `--compare <files...>` | Compare multiple ETF data files | -- |
| `--holdings N` | Number of top holdings to display | 10 |

## Output

- `output/etf_result_TICKER.json` -- Per-ETF analysis with scores, signals, derivatives analysis
- `output/etf_comparison.json` -- Multi-ETF comparison with best-in-class picks
- `output/plots/TICKER_etf_analysis.png` -- 2x2 dashboard: quality scores, key metrics, premium/discount, derivatives analysis
- `output/plots/TICKER_etf_analysis.svg` -- Vector version

## Testing

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest valuation/etf_analysis"
```

**Native:**
```bash
eval $(opam env) && dune runtest valuation/etf_analysis
```

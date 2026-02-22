# Normalized Multiples - Sector-Benchmarked Valuation Analysis

Analyzes stocks using valuation multiples with explicit time windows (TTM/NTM), compared against sector benchmarks. Calculates quality-adjusted percentile rankings and implied fair values from each multiple.

## Overview

- Explicit time window labeling on all multiples (TTM, NTM, FY0, FY1, FY2) to eliminate ambiguity
- Sector benchmark comparison with percentile ranking (25th, 50th, 75th)
- Quality adjustment: growth premium, margin premium, return premium applied to composite percentile
- Two analysis modes: single-ticker deep dive and multi-ticker comparative ranking

## Architecture

```
normalized_multiples/
├── ocaml/
│   ├── bin/main.ml                     # CLI
│   ├── lib/
│   │   ├── types.ml                    # Core types (multiples, benchmarks, signals)
│   │   ├── multiples.ml                # Multiple normalization logic
│   │   ├── benchmarks.ml               # Sector benchmark loading + comparison
│   │   ├── scoring.ml                  # Single and comparative analysis
│   │   └── io.ml                       # JSON I/O and formatting
│   └── test/
│       └── test_normalized_multiples.ml
├── python/
│   ├── fetch/
│   │   ├── fetch_multiples_data.py     # Fetch per-ticker multiples
│   │   └── fetch_sector_benchmarks.py  # Fetch sector benchmark data
│   └── viz/
│       └── plot_multiples.py           # Valuation + quality dashboards
├── data/
│   ├── multiples_data_TICKER.json      # Per-ticker data
│   └── sector_benchmarks/              # Sector median/percentile data
└── output/
    ├── multiples_result_TICKER.json    # Per-ticker results
    └── plots/                          # Valuation + quality charts
```

## Quickstart

### 1. Build

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build valuation/normalized_multiples"
```

**Native:**
```bash
eval $(opam env) && dune build valuation/normalized_multiples
```

### 2. Fetch Sector Benchmarks

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/normalized_multiples/python/fetch/fetch_sector_benchmarks.py --sector all"
```

**Native:**
```bash
uv run valuation/normalized_multiples/python/fetch/fetch_sector_benchmarks.py --sector all
```

### 3. Fetch Ticker Data

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/normalized_multiples/python/fetch/fetch_multiples_data.py --ticker COST"
```

**Native:**
```bash
uv run valuation/normalized_multiples/python/fetch/fetch_multiples_data.py --ticker COST
```

### 4. Run Analysis (Single)

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec normalized_multiples -- --tickers COST"
```

**Native:**
```bash
eval $(opam env) && dune exec normalized_multiples -- --tickers COST
```

### 5. Run Analysis (Compare)

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec normalized_multiples -- --mode compare --tickers COST,WMT,TGT,SFM"
```

**Native:**
```bash
eval $(opam env) && dune exec normalized_multiples -- --mode compare --tickers COST,WMT,TGT,SFM
```

### 6. Visualize

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/normalized_multiples/python/viz/plot_multiples.py --input valuation/normalized_multiples/output/multiples_result_COST.json"
```

**Native:**
```bash
uv run valuation/normalized_multiples/python/viz/plot_multiples.py --input valuation/normalized_multiples/output/multiples_result_COST.json
```

Comparison view:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/normalized_multiples/python/viz/plot_multiples.py --input valuation/normalized_multiples/output/multiples_comparison.json --comparison"
```

**Native:**
```bash
uv run valuation/normalized_multiples/python/viz/plot_multiples.py --input valuation/normalized_multiples/output/multiples_comparison.json --comparison
```

## CLI Options (OCaml)

| Flag | Description | Default |
|------|-------------|---------|
| `--tickers` | Comma-separated list of tickers (required) | -- |
| `--mode` | Analysis mode: `single` or `compare` | `single` |
| `--data` | Data directory | `valuation/normalized_multiples/data` |
| `--output` | Output directory | `valuation/normalized_multiples/output` |
| `--python` | Python command for auto-fetching | -- |
| `--json` | Output JSON instead of formatted text | -- |

## Output

- `output/multiples_result_TICKER.json` -- Per-ticker percentile ranks, implied prices, quality adjustments, signal
- `output/multiples_comparison.json` -- Multi-ticker ranking by value score and quality-adjusted score
- `output/plots/TICKER_multiples_valuation.png` -- Percentile ranks and implied price spread
- `output/plots/TICKER_multiples_quality.png` -- Quality adjustment breakdown and price vs implied value
- `output/plots/multiples_comparison.png` -- Comparative ranking chart

## Testing

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest valuation/normalized_multiples"
```

**Native:**
```bash
eval $(opam env) && dune runtest valuation/normalized_multiples
```

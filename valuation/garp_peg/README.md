# GARP PEG - Growth at a Reasonable Price Analysis

Implements the GARP (Growth at a Reasonable Price) investment framework using PEG ratio variants, quality scoring, and balance sheet analysis. Identifies stocks with strong growth that are not yet overpriced.

## Overview

- Three PEG ratio variants: trailing, forward, and PEGY (dividend-adjusted)
- Composite GARP scoring: PEG value, growth rate, quality (FCF conversion, ROE, ROA), balance sheet
- Implied fair P/E and fair price derivation from growth rates
- Multi-ticker comparison with ranking by GARP score

## Architecture

```
garp_peg/
├── ocaml/
│   ├── bin/main.ml           # CLI
│   ├── lib/
│   │   ├── types.ml          # Core types (garp_data, peg_metrics, scores, signals)
│   │   ├── peg.ml            # PEG ratio calculations
│   │   ├── scoring.ml        # GARP scoring and comparison
│   │   └── io.ml             # JSON I/O and formatting
│   └── test/
│       └── test_garp_peg.ml
├── python/
│   ├── fetch/
│   │   └── fetch_garp_data.py  # Fetch P/E, growth, quality data
│   └── viz/
│       └── plot_garp.py        # Visualization
├── data/                       # Per-ticker GARP data JSON
└── output/                     # Results + plots
```

## Quickstart

### 1. Build

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build valuation/garp_peg"
```

**Native:**
```bash
eval $(opam env) && dune build valuation/garp_peg
```

### 2. Fetch Data

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/garp_peg/python/fetch/fetch_garp_data.py --ticker NVDA --output valuation/garp_peg/data"
```

**Native:**
```bash
uv run valuation/garp_peg/python/fetch/fetch_garp_data.py --ticker NVDA --output valuation/garp_peg/data
```

### 3. Run Analysis

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec garp_peg -- --ticker NVDA"
```

**Native:**
```bash
eval $(opam env) && dune exec garp_peg -- --ticker NVDA
```

Compare multiple tickers:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec garp_peg -- --tickers NVDA,AAPL,MSFT,META --compare"
```

**Native:**
```bash
eval $(opam env) && dune exec garp_peg -- --tickers NVDA,AAPL,MSFT,META --compare
```

### 4. Visualize

Single result:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/garp_peg/python/viz/plot_garp.py --result valuation/garp_peg/output/garp_result_NVDA.json"
```

**Native:**
```bash
uv run valuation/garp_peg/python/viz/plot_garp.py --result valuation/garp_peg/output/garp_result_NVDA.json
```

Comparison:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/garp_peg/python/viz/plot_garp.py --comparison valuation/garp_peg/output/garp_comparison.json"
```

**Native:**
```bash
uv run valuation/garp_peg/python/viz/plot_garp.py --comparison valuation/garp_peg/output/garp_comparison.json
```

## CLI Options (OCaml)

| Flag | Description | Default |
|------|-------------|---------|
| `--ticker` | Single ticker to analyze | -- |
| `--tickers` | Comma-separated list for comparison | -- |
| `--data` | Data directory | `valuation/garp_peg/data` |
| `--output` | Output directory | `valuation/garp_peg/output` |
| `--python` | Path to Python fetch script | -- |
| `--compare` | Enable comparison mode | -- |

## Output

- `output/garp_result_TICKER.json` -- Per-ticker PEG metrics, quality scores, signal, implied fair price
- `output/garp_comparison.json` -- Multi-ticker ranking by GARP score
- `output/TICKER_garp_analysis.png` -- Analysis dashboard
- `output/TICKER_garp_analysis.svg` -- Vector version
- `output/garp_comparison.png` -- Comparison chart

## Testing

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest valuation/garp_peg"
```

**Native:**
```bash
eval $(opam env) && dune runtest valuation/garp_peg
```

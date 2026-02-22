# Relative Valuation - Comparable Company Analysis

Performs relative valuation by comparing a target company against a peer group using multiple valuation ratios. Computes peer similarity scores, implied valuations from peer medians, and a composite assessment of whether the stock is under- or overvalued relative to comparable companies.

## Overview

- Peer similarity scoring across industry, size, growth, and profitability dimensions
- Eight multiple comparisons: trailing/forward P/E, P/B, P/S, P/FCF, EV/EBITDA, EV/EBIT, EV/Revenue
- Implied price derivation from peer median multiples for each valuation method
- Composite relative score with assessment (Very Undervalued through Very Overvalued) and signal

## Architecture

```
relative_valuation/
├── ocaml/
│   ├── bin/main.ml                # CLI
│   ├── lib/
│   │   ├── types.ml               # Core types (company_data, multiples, similarity, signals)
│   │   ├── multiples.ml           # Multiple calculation and comparison
│   │   ├── peer_selection.ml      # Peer similarity scoring
│   │   ├── scoring.ml             # Composite scoring and assessment
│   │   └── io.ml                  # JSON I/O and formatting
│   └── test/
│       └── test_relative_valuation.ml
├── python/
│   ├── fetch/
│   │   └── fetch_peer_data.py     # Fetch target + peer fundamentals
│   └── viz/
│       └── plot_relative.py       # 2x2 dashboard visualization
├── data/                          # Per-target peer data JSON
└── output/                        # Results + plots
```

## Quickstart

### 1. Build

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build valuation/relative_valuation"
```

**Native:**
```bash
eval $(opam env) && dune build valuation/relative_valuation
```

### 2. Fetch Data

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/relative_valuation/python/fetch/fetch_peer_data.py --target SFM --peers COST,WMT,TGT,KR,ACI"
```

**Native:**
```bash
uv run valuation/relative_valuation/python/fetch/fetch_peer_data.py --target SFM --peers COST,WMT,TGT,KR,ACI
```

### 3. Run Analysis

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec relative_valuation -- --target SFM"
```

**Native:**
```bash
eval $(opam env) && dune exec relative_valuation -- --target SFM
```

With auto-fetch:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec relative_valuation -- --target SFM --peers COST,WMT,TGT,KR,ACI --python 'uv run'"
```

**Native:**
```bash
eval $(opam env) && dune exec relative_valuation -- --target SFM --peers COST,WMT,TGT,KR,ACI --python 'uv run'
```

### 4. Visualize

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/relative_valuation/python/viz/plot_relative.py --input valuation/relative_valuation/output/relative_result_SFM.json"
```

**Native:**
```bash
uv run valuation/relative_valuation/python/viz/plot_relative.py --input valuation/relative_valuation/output/relative_result_SFM.json
```

## CLI Options (OCaml)

| Flag | Description | Default |
|------|-------------|---------|
| `--target` | Target ticker to analyze (required) | -- |
| `--peers` | Comma-separated list of peer tickers | -- |
| `--data` | Data directory | `valuation/relative_valuation/data` |
| `--output` | Output directory | `valuation/relative_valuation/output` |
| `--python` | Python command to auto-fetch data | -- |

## Output

- `output/relative_result_TICKER.json` -- Peer similarities, multiple comparisons, implied valuations, composite score, signal
- `output/relative_valuation_TICKER.png` -- 2x2 dashboard: peer similarity, multiple comparison, implied price waterfall, summary
- `output/relative_valuation_TICKER.svg` -- Vector version
- `output/plots/TICKER_relative_valuation.png` -- Alternative plot location

## Testing

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest valuation/relative_valuation"
```

**Native:**
```bash
eval $(opam env) && dune runtest valuation/relative_valuation
```

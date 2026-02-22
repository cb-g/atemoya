# Crypto Treasury - mNAV Valuation Model

Valuates companies that hold Bitcoin and/or Ethereum as treasury assets using the multiple of Net Asset Value (mNAV) methodology. Determines whether buying the stock is cheaper or more expensive than buying the underlying crypto directly.

## Overview

- Computes NAV from BTC/ETH holdings at live spot prices
- Calculates mNAV (Market Cap / NAV) to measure premium or discount to crypto holdings
- Derives implied crypto prices, per-share exposure, unrealized gains, and leverage (debt/NAV)
- Generates investment signals: Strong Buy (mNAV < 0.8) through Overvalued (mNAV > 1.5)

## Architecture

```
crypto_treasury/
├── ocaml/
│   ├── bin/                   # CLI (in progress)
│   ├── lib/
│   │   ├── types.ml           # Holdings, mNAV metrics, signals
│   │   └── mnav.ml            # NAV, mNAV, implied price calculations
│   └── test/                  # Tests
├── python/
│   ├── crypto_valuation.py    # Fetch + valuate (combined)
│   └── plot_crypto.py         # Visualization
├── data/
│   └── holdings.json          # BTC/ETH holdings per company
└── output/
    ├── crypto_treasury_all.json          # All valuations
    └── crypto_treasury_comparison.png    # Comparison chart
```

## Quickstart

### 1. Update Holdings Data

Edit `data/holdings.json` with current BTC/ETH holdings from company filings.

### 2. Run Valuation (All Companies)

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/crypto_treasury/python/crypto_valuation.py"
```

**Native:**
```bash
uv run valuation/crypto_treasury/python/crypto_valuation.py
```

### 3. Run Valuation (Single Ticker)

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/crypto_treasury/python/crypto_valuation.py --ticker MSTR"
```

**Native:**
```bash
uv run valuation/crypto_treasury/python/crypto_valuation.py --ticker MSTR
```

### 4. Visualize

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run valuation/crypto_treasury/python/plot_crypto.py"
```

**Native:**
```bash
uv run valuation/crypto_treasury/python/plot_crypto.py
```

## CLI Options (crypto_valuation.py)

| Flag | Description | Default |
|------|-------------|---------|
| `--ticker` | Single ticker to valuate | All tickers in holdings.json |
| `--data-dir` | Directory containing holdings.json | `valuation/crypto_treasury/data` |
| `--output-dir` | Output directory for results | `valuation/crypto_treasury/output` |
| `--json` | Output results as JSON to stdout | -- |

## Output

- `output/crypto_treasury_all.json` -- Full valuation results for all companies
- `output/crypto_treasury_comparison.png` -- Four-panel chart: premium/discount, holdings value, leverage, summary table
- `output/crypto_treasury_comparison.svg` -- Vector version of the above

## Testing

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest valuation/crypto_treasury"
```

**Native:**
```bash
eval $(opam env) && dune runtest valuation/crypto_treasury
```

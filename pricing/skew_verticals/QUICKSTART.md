# Quickstart: Skew Vertical Spreads

## What This Does

Scans for high-probability vertical spread opportunities using:
1. **Volatility Skew:** OTM options overpriced vs ATM
2. **IV/RV Comparison:** Sell expensive OTM, buy fair ATM
3. **Momentum:** Directional edge alignment

Target: 1.5:1+ reward/risk for debit spreads, ~30-45% win rate.

## Quick Start

### 1. Run Scanner

```bash
cd /home/uuu/claude/fin/atemoya
./pricing/skew_verticals/run_scanner.sh AAPL
```

This will:
- Fetch options chain from yfinance
- Fetch price history for momentum
- Calculate skew metrics and z-scores
- Find optimal vertical spreads
- Apply 3-part filter system
- Display recommendation with edge score

### 2. View Output

The scanner outputs:
- **Recommendation:** "Strong Buy" / "Buy" / "Pass"
- **Edge Score:** 0-100
- **Spread Details:** Strikes, deltas, IVs, prices
- **Economics:** Debit, max profit/loss, reward/risk, breakeven
- **Expected Value:** Probability, EV, expected return
- **Filter Results:** Which filters passed/failed
- **Metrics:** Full skew and momentum analysis

### 3. Forward Testing (Optional)

Track results over time:

```bash
# View all scans
uv run pricing/skew_verticals/python/tracking/view_history.py

# Update expired trades
uv run pricing/skew_verticals/python/tracking/update_results.py
```

See [FORWARD_TESTING.md](FORWARD_TESTING.md) for complete workflow.

## Example Output

```
╔════════════════════════════════════════════════════╗
║  TRADE RECOMMENDATION: AAPL                        ║
╚════════════════════════════════════════════════════╝

>>> Strong Buy <<<
Edge Score: 82/100

=== Vertical Spread: AAPL ===
Type: bull_call
Expiration: 2026-02-06 (31 days)

Long leg (BUY):
  Strike: $150.00 | Delta: 0.52 | IV: 24.5% | Price: $4.20

Short leg (SELL):
  Strike: $155.00 | Delta: 0.28 | IV: 31.2% | Price: $1.80

Spread Economics:
  Debit (cost): $2.40
  Max profit: $2.60
  Max loss: $2.40
  Reward/Risk: 8.3:1
  Breakeven: $152.40

Expected Value:
  Prob profit: 38.5%
  Expected value: $0.62
  Expected return: 25.8%

✓ EXCELLENT reward/risk (≥5:1)
✓ POSITIVE expected value

=== Filters ===
Skew filter: ✓ PASS
IV/RV filter: ✓ PASS
Momentum filter: ✓ PASS
```

## Components

### OCaml (Analytics)
- `types.ml` - Type definitions
- `skew.ml` - Skew calculator with z-scores
- `momentum.ml` - Momentum indicators
- `spreads.ml` - Spread optimizer
- `scanner.ml` - Filter logic and recommendations
- `io.ml` - CSV data loading
- `main.ml` - Scanner executable

### Python (Data + Analysis)
- `fetch_options_chain.py` - Get options data
- `fetch_prices.py` - Get price history
- `monte_carlo.py` - GBM expected value calculator
- `trade_logger.py` - Log scans to database
- `update_results.py` - Update completed trades
- `view_history.py` - Analyze performance

## Files

```
pricing/skew_verticals/
├── README.md              # Full documentation
├── FORWARD_TESTING.md     # Testing workflow
├── QUICKSTART.md          # This file
├── run_scanner.sh         # Main runner script
├── ocaml/                 # Analytics code
│   ├── lib/
│   └── bin/
├── python/                # Data fetching and tracking
│   ├── fetch/
│   ├── analysis/
│   └── tracking/
└── data/                  # Stored data
    └── trade_history.csv  # Forward test database
```

## Next Steps

1. **Test on multiple tickers:** Run scanner on 5-10 liquid stocks
2. **Start forward testing:** Log "Strong Buy" recommendations
3. **Collect 6-12 months of data:** Validate claimed performance
4. **Optimize:** Refine filters based on real results

## Notes

- Just implemented - performance claims NOT YET VERIFIED
- Building forward-testing database prospectively
- Need 50+ completed trades for statistical validation
- Claimed examples: QUBT (380%), SBET (280%), MP (400%)
- Minimum reward/risk: 1.5:1 for debit spreads, 0.1:1 for credit spreads
- IV ceiling: 200% (accommodates high-vol stocks)

See [README.md](README.md) for complete strategy details.

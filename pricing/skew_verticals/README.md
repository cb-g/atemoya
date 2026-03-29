# Skew-Based Vertical Spreads Scanner

Identifies high-probability vertical spread opportunities by exploiting volatility skew mispricing combined with momentum signals.

## Strategy Overview

**Core Thesis:**
- ATM options are efficiently priced by market makers
- OTM options are systematically overpriced due to skew (crash protection demand)
- Buy ATM (fair price), sell OTM (rich price) = structural edge
- Add momentum filter for directional alignment

**Target Profile:**
- Reward/Risk ratio: 1.5:1+ for debit spreads, 0.1:1+ for credit spreads
- Win rate: ~30-45% depending on spread type
- Asymmetric payoffs: defined risk with favorable expected value

## Three-Part Filter System

### 1. Skew Filter
- **Metric:** Call/Put skew z-score
- **Calculation:** Skew = (ATM_IV - 25Δ_IV) / ATM_IV
- **Threshold:** z-score < -2.0 (extreme skew compression)
- **Why:** Identifies when OTM options are abnormally expensive vs ATM

### 2. IV/RV Filter
- **Condition:** VRP > 0 (positive variance risk premium) AND OTM_IV > RV
- **Why:** Positive VRP means options are overpriced vs realized volatility; OTM IV > RV confirms short leg collects excess premium
- **Edge:** Sell expensive OTM vol when options market systematically overprices volatility

### 3. Momentum Filter
- **Bull Calls:** Momentum score > 0.3 (positive trend)
- **Bear Puts:** Momentum score < -0.3 (negative trend)
- **Components:**
  - Time series momentum (1M, 3M returns)
  - Cross-sectional ranking
  - Beta-adjusted alpha
  - Proximity to 52W high

## Architecture

```
pricing/skew_verticals/
├── ocaml/
│   ├── lib/
│   │   ├── types.ml          # Type definitions
│   │   ├── skew.ml           # Skew calculator with z-scores
│   │   ├── momentum.ml       # Momentum indicators
│   │   ├── spreads.ml        # Spread optimizer
│   │   ├── scanner.ml        # Filter logic and recommendations
│   │   └── io.ml             # CSV data loading
│   └── bin/
│       └── main.ml           # Scanner executable
├── python/
│   ├── fetch/
│   │   ├── fetch_options_chain.py  # Get all strikes/IVs/deltas
│   │   └── fetch_prices.py         # Get stock + market prices
│   ├── analysis/
│   │   └── monte_carlo.py    # GBM expected value calculator
│   └── tracking/
│       ├── trade_logger.py   # Log scans to database
│       ├── update_results.py # Close out trades post-expiration
│       └── view_history.py   # Analyze forward test results
└── data/
    └── trade_history.csv     # Forward-testing database
```

## Daily Signal Pipeline

Three-stage automated pipeline: **collect** (after market close) → **scan** (after collection) → **notify** (before market open).

Runs on all 523 liquid tickers daily. Skew z-scores need history to detect extremes — signals improve after 3+ days of collection.

**What gets stored:**
- `data/snapshots/{TICKER}/{YYYY-MM-DD}.json` - Full snapshot archive per day
- `data/{TICKER}_skewvert_history.csv` - Append-only history of daily skew/VRP/momentum metrics

#### Automated Cron Setup

All times below are UTC. Runs Tue-Sat to capture Mon-Fri market data.

**Native (uv installed on host):**

Cron runs with minimal PATH — add this line to the top of your crontab so `uv` is found:
```
PATH=/home/devusr/.local/bin:/usr/local/bin:/usr/bin:/bin
```

```bash
# 1. Collect skew verticals snapshots for all liquid tickers
0 3 * * 2-6 cd /path/to/atemoya && uv run pricing/skew_verticals/python/fetch/collect_snapshot.py --tickers all_liquid >> /tmp/skewvert_collect.log 2>&1

# 2. Run signal scanner after collection completes
15 4 * * 2-6 cd /path/to/atemoya && uv run pricing/skew_verticals/python/scan_signals.py --segments --quiet --output pricing/skew_verticals/output/signal_scan.csv >> /tmp/skewvert_scan.log 2>&1

# 3. Send morning trade notifications (before market open)
15 9 * * 1-5 cd /path/to/atemoya && uv run pricing/skew_verticals/python/notify_signals.py >> /tmp/skewvert_notify.log 2>&1
```

**Docker (from host crontab):**
```bash
0 3 * * 2-6 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/skew_verticals/python/fetch/collect_snapshot.py --tickers all_liquid" >> /tmp/skewvert_collect.log 2>&1
15 4 * * 2-6 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/skew_verticals/python/scan_signals.py --segments --quiet --output pricing/skew_verticals/output/signal_scan.csv" >> /tmp/skewvert_scan.log 2>&1
15 9 * * 1-5 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/skew_verticals/python/notify_signals.py" >> /tmp/skewvert_notify.log 2>&1
```

Notifications require `NTFY_TOPIC` set in `.env` at the project root.

#### Manual / Ad-hoc Usage

```bash
# Collect a single ticker
uv run pricing/skew_verticals/python/fetch/collect_snapshot.py --ticker AAPL

# Run scanner with z-score lookback window
uv run pricing/skew_verticals/python/scan_signals.py --segments --window 60

# Dry-run notification
uv run pricing/skew_verticals/python/notify_signals.py --dry-run
```

## Usage (OCaml Scanner)

For the original single-ticker OCaml scanner with spread optimization:

### 1. Fetch Data

```bash
# Fetch options chain
uv run pricing/skew_verticals/python/fetch/fetch_options_chain.py \
  --ticker AAPL

# Fetch price history for momentum
uv run pricing/skew_verticals/python/fetch/fetch_prices.py \
  --ticker AAPL --days 252
```

### 2. Run Scanner

```bash
cd pricing/skew_verticals/ocaml
dune build
dune exec bin/main.exe AAPL
```

### 3. Analyze Expected Value (Optional)

```bash
uv run pricing/skew_verticals/python/analysis/monte_carlo.py \
  --spot 150.0 \
  --volatility 0.25 \
  --days 21 \
  --long-strike 150 \
  --short-strike 155 \
  --debit 1.50 \
  --spread-type bull_call \
  --momentum-score 0.5
```

### 4. Track Results

See [FORWARD_TESTING.md](FORWARD_TESTING.md) for complete forward-testing workflow.

## Output Example

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

Notes: All filters passed
```

## Key Metrics

### Skew Metrics
- **Call Skew:** (ATM_IV - 25Δ_Call_IV) / ATM_IV
- **Put Skew:** (ATM_IV - 25Δ_Put_IV) / ATM_IV
- **Z-Score:** Current skew vs 30-day historical average
- **VRP:** Variance Risk Premium (ATM_IV - Realized_Vol)

### Spread Economics
- **Debit:** Net cost (long price - short price)
- **Max Profit:** Width - Debit
- **Max Loss:** Debit
- **Reward/Risk:** Max Profit / Max Loss
- **Breakeven:** Long strike ± Debit

### Edge Score (0-100)
- 40 pts: Skew z-score magnitude
- 20 pts: Momentum strength
- 30 pts: Reward/risk ratio
- 10 pts: Expected value

## Forward Testing

See [FORWARD_TESTING.md](FORWARD_TESTING.md) for:
- Database schema
- Workflow for tracking scans → results
- Performance analysis tools

**Status:** Just implemented - collecting data prospectively to verify performance claims.

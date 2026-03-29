# Forward Factor Strategy

Calendar spread trading strategy based on term structure mispricing.

## Strategy Overview

**Core Concept:** Trade calendar spreads when the implied forward volatility shows significant backwardation (front month IV > back month IV).

**Signal:** Forward Factor (FF) ≥ 0.20 (20% backwardation)

**Position:** ATM call calendar spreads (sell front month, buy back month)

**Backtest Results:**
- 27% CAGR (quarter Kelly sizing)
- 2.42 Sharpe ratio
- 66% win rate
- Best DTE pair: 60-90 days

## Mathematical Foundation

### Forward Volatility

The market's implied view of volatility for a future time window:

```
Forward Variance: V_fwd = (σ2² × T2 - σ1² × T1) / (T2 - T1)
Forward Volatility: σ_fwd = sqrt(V_fwd)
```

Where:
- σ1 = front period IV (annualized)
- σ2 = back period IV (annualized)
- T1 = front period time (years)
- T2 = back period time (years)

### Forward Factor

Measures the degree of backwardation:

```
FF = (σ1 - σ_fwd) / σ_fwd
```

**Interpretation:**
- FF ≥ 1.00 (100%): Extreme backwardation - exceptional setup
- FF ≥ 0.50 (50%): Strong backwardation - high quality
- FF ≥ 0.20 (20%): Valid backwardation - entry threshold
- FF < 0.20: Below threshold, skip
- FF < 0: Contango, avoid

## Trading Mechanics

### Entry Criteria
1. Forward Factor ≥ 0.20
2. Sufficient option liquidity
3. DTE pair: 30-60, 30-90, or 60-90 (60-90 preferred)

### Position Structure
- **Sell:** Front month ATM call (e.g., 30 DTE)
- **Buy:** Back month ATM call (e.g., 60-90 DTE)
- **Cost:** Net debit (back premium - front premium)
- **Max Loss:** Net debit paid
- **Max Profit:** Typically 50-100% of debit

### Position Sizing
- Kelly fraction: Quarter Kelly (conservative)
- Range: 2-8% of portfolio per trade
- Default: 4% for FF ≥ 0.20
- Scale up to 8% for FF ≥ 1.00

### Exit Rules
1. Front expiration: Close or roll ~7 DTE
2. Profit target: 50-75% of max profit
3. Stop loss: 100% of debit (let expire)

## Daily Signal Pipeline

Three-stage automated pipeline: **collect** (after market close) → **scan** (after collection) → **notify** (before market open).

Runs on all 523 liquid tickers daily (not earnings-gated). The more history accumulated, the better the z-scores.

**What gets stored:**
- `data/snapshots/{TICKER}/{YYYY-MM-DD}.json` - Full snapshot archive per day
- `data/{TICKER}_ff_history.csv` - Append-only history (one row per DTE pair per day)

#### Automated Cron Setup

All times below are UTC. Runs Tue-Sat to capture Mon-Fri market data.

**Native (uv installed on host):**

Cron runs with minimal PATH — add this line to the top of your crontab so `uv` is found:
```
PATH=/home/devusr/.local/bin:/usr/local/bin:/usr/bin:/bin
```

```bash
# 1. Collect forward factor snapshots for all liquid tickers
45 7 * * 2-6 cd /path/to/atemoya && uv run pricing/forward_factor/python/fetch/collect_snapshot.py --tickers all_liquid >> /tmp/ff_collect.log 2>&1

# 2. Run signal scanner after collection completes
0 9 * * 2-6 cd /path/to/atemoya && uv run pricing/forward_factor/python/scan_signals.py --segments --quiet --output pricing/forward_factor/output/signal_scan.csv >> /tmp/ff_scan.log 2>&1

# 3. Send morning trade notifications (before market open)
20 9 * * 1-5 cd /path/to/atemoya && uv run pricing/forward_factor/python/notify_signals.py >> /tmp/ff_notify.log 2>&1
```

**Docker (from host crontab):**
```bash
45 7 * * 2-6 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/forward_factor/python/fetch/collect_snapshot.py --tickers all_liquid" >> /tmp/ff_collect.log 2>&1
0 9 * * 2-6 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/forward_factor/python/scan_signals.py --segments --quiet --output pricing/forward_factor/output/signal_scan.csv" >> /tmp/ff_scan.log 2>&1
20 9 * * 1-5 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/forward_factor/python/notify_signals.py" >> /tmp/ff_notify.log 2>&1
```

Notifications require `NTFY_TOPIC` set in `.env` at the project root.

#### Manual / Ad-hoc Usage

```bash
# Collect a single ticker
uv run pricing/forward_factor/python/fetch/collect_snapshot.py --ticker AAPL

# Run scanner filtered to 60-90 DTE pair (best performing in backtest)
uv run pricing/forward_factor/python/scan_signals.py --segments --dte-pair 60-90

# Run scanner with z-score lookback window
uv run pricing/forward_factor/python/scan_signals.py --window 60

# Dry-run notification
uv run pricing/forward_factor/python/notify_signals.py --dry-run
```

## Quick Start (OCaml Scanner)

For the original single-run OCaml scanner with Kelly sizing:

### 1. Fetch Options Data

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/forward_factor/python/fetch_chains.py"
```

**Native:**
```bash
uv run pricing/forward_factor/python/fetch_chains.py
```

This fetches options chains for default universe (SPY, QQQ, AAPL, etc.) and saves to `data/options_chains.json`.

### 2. Run Scanner

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec forward_factor"
```

**Native:**
```bash
eval $(opam env) && dune exec forward_factor
```

The scanner:
- Calculates forward factors for all DTE pairs
- Filters by FF ≥ 0.20
- Ranks opportunities by FF
- Suggests position sizing
- Prints detailed recommendations

### 3. Review Recommendations

Output includes:
- Forward Factor and strength classification
- Calendar spread structure (strikes, prices)
- Net debit and profit potential
- Expected return (from backtest)
- Suggested position size (2-8%)
- Rationale for the setup

## Project Structure

```
pricing/forward_factor/
├── ocaml/                    # Core analytics (OCaml)
│   ├── lib/
│   │   ├── types.ml         # Type definitions
│   │   ├── forward_vol.ml   # Forward vol calculator
│   │   ├── calendar.ml      # Calendar spread pricer
│   │   └── scanner.ml       # Opportunity scanner
│   └── bin/
│       └── main.ml          # Main executable
├── python/                   # Data & signals (Python)
│   ├── fetch/
│   │   └── collect_snapshot.py  # Daily cron collector
│   ├── fetch_chains.py       # One-shot chain fetcher (for OCaml)
│   ├── scan_signals.py       # Z-score signal scanner
│   ├── notify_signals.py     # ntfy.sh notification sender
│   └── pyproject.toml        # Python dependencies
├── data/                     # Time series data
│   ├── {TICKER}_ff_history.csv
│   ├── snapshots/{TICKER}/{YYYY-MM-DD}.json
│   └── options_chains.json   # One-shot chain data (for OCaml)
└── output/                   # Scanner results
    └── signal_scan.csv
```

## Strategy Details

### Why It Works

1. **Mean Reversion:** Volatility term structure tends to normalize
2. **Theta Decay:** Front month decays faster than back month
3. **Vega Exposure:** Positive vega benefits from IV expansion
4. **Statistical Edge:** Backwardation often precedes IV collapse

### Risk Factors

1. **Gap Risk:** Large moves beyond strikes reduce profit
2. **IV Collapse:** Affects both legs, but front more sensitive
3. **Theta:** Works against position initially (back > front premium)
4. **Liquidity:** Need liquid options for good fills

### Backtest Highlights

- Period: 2015-2024 (full cycle)
- Universe: Top 50 liquid names
- Sample: 1,247 trades
- Win Rate: 66% (FF ≥ 0.20)
- Avg Win: 45% of debit
- Avg Loss: 100% of debit (max loss)
- Best FF Bucket: FF ≥ 1.00 → 80% avg return

## Advanced Usage

### Double Calendars

For wider profit zones, use 35-delta wings instead of ATM:
- Sell front 35-delta call + put
- Buy back 35-delta call + put
- Higher debit but more forgiving

### Forward Testing

Track all recommendations to validate:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/forward_factor/python/tracking/log_trade.py --ticker AAPL --ff 0.45 --spread '30-60 ATM call calendar'"
```

**Native:**
```bash
uv run pricing/forward_factor/python/tracking/log_trade.py --ticker AAPL --ff 0.45 --spread '30-60 ATM call calendar'
```

### Custom Universe

Edit `fetch_chains.py` to scan different tickers:
```python
universe = ['AAPL', 'GOOGL', 'TSLA']  # Your list
```

## License

Part of the Atemoya quantitative finance framework.

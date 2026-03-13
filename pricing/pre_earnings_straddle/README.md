# Pre-Earnings Straddle Strategy

Trading the IV repricing into earnings, **NOT** the earnings gap itself.

## Strategy Overview

**Core Thesis:**
- Most traders think the "IV ramp" into earnings is free edge
- It's not - the ramp is mostly mechanical (math artifact)
- Real edge comes from event volatility being **mispriced vs history**
- We enter ~14 days before earnings and **exit before** the announcement

**Key Insight:**
The "IV ramp" happens because we're packing the same event variance into fewer days as earnings approaches. Total variance is actually shrinking (being consumed on ambient days). Without the event component being repriced higher, straddles lose money despite IV going up.

**What We're Actually Trading:**
- Repricing of **event volatility** (the earnings jump component)
- **NOT** the mechanical IV ramp
- **NOT** the actual earnings gap

## Backtest Results (21,500 Trades, 2009-Present)

**Unfiltered** (buy every pre-earnings straddle):
- Median return: -6.3% (most trades lose)
- Mean return: +0.3% (slightly positive)
- Win rate: 37%

**Filtered** (using 4-signal model, predicted return > 0):
- Median return: -3.6% (still lose often)
- Mean return: +3.3% (positive edge)
- Win rate: 42%

**Profile:** Many small/moderate losses, occasional big winners. Classic long volatility payoff.

## Four Predictive Signals (All Negative Relationships)

Lower values = better returns. All compare current implied move vs history:

1. **Current / Last Implied Ratio**
   - Current implied move / Previous earnings implied move
   - <0.9 = cheap, >1.1 = expensive

2. **Current - Last Realized Gap**
   - Current implied move - Last earnings realized move
   - Negative = current is cheaper than what actually happened last time

3. **Current / Average Implied Ratio**
   - Current implied move / Historical average implied move
   - <0.9 = cheap vs history, >1.1 = expensive vs history

4. **Current - Average Realized Gap**
   - Current implied move - Historical average realized move
   - Negative = current is cheaper than historical average reality

**What They All Say:**
Current implied move should be **cheap relative to history** for the trade to work.

## Linear Regression Model

```
Predicted Return = β0
                 + β1 * (Current/Last Implied)
                 + β2 * (Current - Last Realized)
                 + β3 * (Current/Avg Implied)
                 + β4 * (Current - Avg Realized)
```

Default coefficients (from backtest):
- β0 = 0.033 (3.3% base expected return)
- β1 = -0.05 (negative: lower ratio = better)
- β2 = -0.04 (negative: lower gap = better)
- β3 = -0.06 (negative: lower ratio = better)
- β4 = -0.05 (negative: lower gap = better)

Filter: Only take trades with predicted return > 0.

## Trade Structure

**Entry:**
- Buy ATM straddle (call + put at same strike)
- Timing: ~14 days before earnings (±4 day window)
- Expiration: Nearest monthly **after** earnings date

**Exit:**
- Day before earnings announcement (or same day before announcement)
- **DO NOT hold through the earnings gap**

**Sizing:**
- Use small Kelly fraction (2-6% recommended)
- Diversify across multiple names
- Max loss = debit paid (defined risk)

**Holding Period:** ~14 days

## Implementation

### 1. Fetch Historical Data

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/pre_earnings_straddle/python/fetch/fetch_earnings_data.py \
  --ticker AAPL --years 3"
```

**Native:**
```bash
uv run pricing/pre_earnings_straddle/python/fetch/fetch_earnings_data.py \
  --ticker AAPL --years 3
```

### 2. Fetch Current Opportunity

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/pre_earnings_straddle/python/fetch/fetch_straddle_data.py \
  --ticker AAPL"
```

**Native:**
```bash
uv run pricing/pre_earnings_straddle/python/fetch/fetch_straddle_data.py \
  --ticker AAPL
```

### 3. Run Scanner

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec pre_earnings_straddle -- AAPL"
```

**Native:**
```bash
eval $(opam env) && dune exec pre_earnings_straddle -- AAPL
```

### 4. Track Results (Forward Testing)

See [FORWARD_TESTING.md](FORWARD_TESTING.md) for complete workflow.

## Daily IV Snapshot Collection

Build your own implied move history by collecting pre-earnings IV daily.
Over time, this replaces the RV\*1.2 estimate in `fetch_earnings_data.py`
with actual ATM straddle IV data.

### Single Run

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/pre_earnings_straddle/python/fetch/collect_earnings_iv.py \
  --tickers AAPL,NVDA,TSLA,AMZN,GOOGL,META,MSFT"
```

**Native:**
```bash
uv run pricing/pre_earnings_straddle/python/fetch/collect_earnings_iv.py \
  --tickers AAPL,NVDA,TSLA,AMZN,GOOGL,META,MSFT
```

Each run:
- Checks which tickers have earnings within 18 days
- Fetches ATM straddle IV (IBKR if available, yfinance fallback)
- Archives snapshot to `data/snapshots/{TICKER}/{YYYY-MM-DD}.json`
- Appends to `data/{TICKER}_iv_snapshots.csv`
- Idempotent: skips tickers already collected today

### Automated Cron Setup

The daily pipeline has three stages: **collect** (after market close) → **scan** (after collection) → **notify** (before market open). All times below are UTC. Collectors run on Tue-Sat (for Mon-Fri market data).

**Native (uv installed on host):**
```bash
# 1. Collect IV snapshots for all liquid tickers
15 4 * * 2-6 cd /path/to/atemoya && uv run pricing/pre_earnings_straddle/python/fetch/collect_earnings_iv.py --tickers all_liquid >> /tmp/earnings_collect.log 2>&1

# 2. Run signal scanner after collection completes
30 5 * * 2-6 cd /path/to/atemoya && uv run pricing/pre_earnings_straddle/python/scan_signals.py --segments --quiet --output pricing/pre_earnings_straddle/output/signal_scan.csv >> /tmp/earnings_scan.log 2>&1

# 3. Send morning trade notifications (before market open)
10 9 * * 1-5 cd /path/to/atemoya && uv run pricing/pre_earnings_straddle/python/notify_signals.py >> /tmp/earnings_notify.log 2>&1
```

**Docker (from host crontab):**
```bash
15 4 * * 2-6 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/pre_earnings_straddle/python/fetch/collect_earnings_iv.py --tickers all_liquid" >> /tmp/earnings_collect.log 2>&1
30 5 * * 2-6 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/pre_earnings_straddle/python/scan_signals.py --segments --quiet --output pricing/pre_earnings_straddle/output/signal_scan.csv" >> /tmp/earnings_scan.log 2>&1
10 9 * * 1-5 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/pre_earnings_straddle/python/notify_signals.py" >> /tmp/earnings_notify.log 2>&1
```

Notifications require `NTFY_TOPIC` set in `.env` at the project root.

### Adding Tickers

Use `--tickers all_liquid` to automatically collect all tickers from the liquidity module. Alternatively, pass specific tickers: `--tickers AAPL,NVDA,TSLA`. Each ticker gets independent history. After 2+ quarters of collection, `fetch_earnings_data.py` automatically uses real snapshot IV instead of the RV\*1.2 estimate.

## Why This Works

**Behavioral Edge:**
- Market tends to underprice event vol when recent history was calm
- Market tends to overprice when recent history was volatile
- Mean reversion in event volatility

**Structural Edge:**
- Long vol strategies benefit from vol-of-vol
- Occasional regime shifts create outsized winners
- Acts as portfolio hedge for short-vol books

**Statistical Edge:**
- 21,500 trades show consistent out-of-sample performance
- Walk-forward validation across multiple regimes
- Monotonic signal relationships (not curve-fit)

## Risk Profile

**Expectation:**
- Lose on ~58% of trades
- Small to moderate losses most of the time
- Occasional large winners (tail events)
- Positive expected value over many trades

**Max Drawdown:**
- Can last several months before big winner
- Requires patience and discipline
- Use small position sizing

**Not Suitable If:**
- You need consistent monthly profits
- You can't handle losing streaks
- You have limited capital for diversification

## Files

```
pricing/pre_earnings_straddle/
├── README.md                      # This file
├── FORWARD_TESTING.md             # Testing workflow
├── ocaml/
│   ├── lib/
│   │   ├── types.ml               # Type definitions
│   │   ├── signals.ml             # 4-signal calculator
│   │   ├── model.ml               # Linear regression
│   │   ├── scanner.ml             # Recommendation engine
│   │   └── io.ml                  # CSV loading
│   └── bin/
│       └── main.ml                # Scanner executable
├── python/
│   ├── fetch/
│   │   ├── fetch_earnings_data.py       # Build historical database
│   │   ├── fetch_straddle_data.py       # Get current opportunity
│   │   └── collect_earnings_iv.py       # Daily IV snapshot collector
│   └── tracking/
│       ├── trade_logger.py              # Log scans
│       ├── update_results.py            # Update P&L
│       └── view_history.py              # Analyze results
└── data/
    ├── earnings_history.csv             # Historical implied/realized
    ├── model_coefficients.csv           # Trained model
    └── trade_history.csv                # Forward test database
```

## Important Notes

**Data Limitations:**
- Historical implied moves are estimated via RV\*1.2 by default (a crude approximation)
- Run the daily IV snapshot collector (`collect_earnings_iv.py`) to build actual implied move history over time
- Set `DATA_PROVIDER=ibkr` for real-time option chain data from Interactive Brokers; defaults to yfinance

**This is NOT:**
- A get-rich-quick scheme
- A high win-rate strategy
- Suitable for small accounts
- Trading the actual earnings gap

**This IS:**
- A long volatility strategy
- A portfolio hedge component
- A mean-reversion play on event vol
- Positive expected value over time

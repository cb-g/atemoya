# Forward Testing: Building Historical Data Month-by-Month

**The Smart Approach: Collect real data prospectively instead of fighting buggy historical APIs.**

## The Problem

- yfinance has timezone bugs with historical earnings
- Historical options IV data is expensive/unavailable
- We can't verify the claimed 66% win rate / 7.3% return without data

## The Solution

**Build the dataset going forward as earnings happen:**

1. **Before Earnings**: Scan ticker → log to database
2. **After Earnings**: Update with actual P&L
3. **Month-by-Month**: Accumulate real trades
4. **After 6-12 months**: Backtest on YOUR data with YOUR results

## Current Status

**Database**: `pricing/earnings_vol/data/trade_history.csv`
- Total scans: **1** (NVDA - pending Feb 25)
- Completed trades: **0**
- Target: 100-200 trades within 12 months

## Weekly Workflow

### Step 1: Scan Upcoming Earnings

**Docker:**
```bash
# Find a ticker with earnings next week, then:

# 1. Fetch earnings data
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/earnings_vol/python/fetch/fetch_earnings.py --ticker AAPL"

# 2. Fetch IV term structure
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/earnings_vol/python/fetch/fetch_iv_term.py --ticker AAPL"

# 3. Run scanner
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec earnings_vol -- \
  -ticker AAPL -account 10000 -kelly 0.10 -structure calendar"
```

**Native:**
```bash
# Find a ticker with earnings next week, then:

# 1. Fetch earnings data
uv run pricing/earnings_vol/python/fetch/fetch_earnings.py --ticker AAPL

# 2. Fetch IV term structure
uv run pricing/earnings_vol/python/fetch/fetch_iv_term.py --ticker AAPL

# 3. Run scanner
eval $(opam env) && dune exec earnings_vol -- \
  -ticker AAPL -account 10000 -kelly 0.10 -structure calendar
```

This shows recommendation but doesn't save to database yet.

### Step 2: Log the Scan

Copy the scanner output and log it:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/earnings_vol/python/tracking/trade_logger.py \
  --ticker AAPL \
  --earnings-date 2026-01-30 \
  --days-to-earnings 7 \
  --spot-price 225.00 \
  --volume 50000000 \
  --front-iv 0.35 \
  --back-iv 0.30 \
  --term-slope -0.05 \
  --rv 0.28 \
  --iv-rv-ratio 1.25 \
  --recommendation 'Recommended'"
```

**Native:**
```bash
uv run pricing/earnings_vol/python/tracking/trade_logger.py \
  --ticker AAPL \
  --earnings-date 2026-01-30 \
  --days-to-earnings 7 \
  --spot-price 225.00 \
  --volume 50000000 \
  --front-iv 0.35 \
  --back-iv 0.30 \
  --term-slope -0.05 \
  --rv 0.28 \
  --iv-rv-ratio 1.25 \
  --recommendation 'Recommended'
```

**If you actually trade it**, add position details:

```bash
  --position-type calendar \
  --kelly-fraction 0.60 \
  --position-size 600 \
  --num-contracts 2
```

### Step 3: After Earnings, Update Results

Wait 1-2 days after earnings, then:

**Docker:**
```bash
# Update specific trade
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/earnings_vol/python/tracking/update_results.py \
  --ticker AAPL --earnings-date 2026-01-30"

# Or update ALL pending trades
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/earnings_vol/python/tracking/update_results.py --all"
```

**Native:**
```bash
# Update specific trade
uv run pricing/earnings_vol/python/tracking/update_results.py \
  --ticker AAPL --earnings-date 2026-01-30

# Or update ALL pending trades
uv run pricing/earnings_vol/python/tracking/update_results.py --all
```

This fetches post-earnings price, calculates P&L, marks as completed.

### Step 4: View Progress

**Docker:**
```bash
# View all trades
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/earnings_vol/python/tracking/view_history.py"

# View only completed
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/earnings_vol/python/tracking/view_history.py --status completed"

# Export to CSV
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/earnings_vol/python/tracking/view_history.py --export results.csv"
```

**Native:**
```bash
# View all trades
uv run pricing/earnings_vol/python/tracking/view_history.py

# View only completed
uv run pricing/earnings_vol/python/tracking/view_history.py --status completed

# Export to CSV
uv run pricing/earnings_vol/python/tracking/view_history.py --export results.csv
```

## Timeline

- **Month 1**: Scan 10-15 earnings → 10-15 pending
- **Month 2**: Update Month 1 results → 10-15 completed
- **Month 3-6**: Continue building dataset
- **Month 6**: ~50-75 completed trades (initial analysis possible)
- **Month 12**: ~100-200 completed trades → **FULL BACKTEST**

## After 12 Months, You'll Know

✅ **Actual win rate** vs claimed 66%
✅ **Actual mean return** vs claimed 7.3%
✅ **Actual Sharpe ratio** vs claimed 3.5
✅ **Actual max drawdown** vs claimed 20%
✅ **Whether the 3-filter system works**
✅ **If the Kelly sizing is correct**

## Database Schema

`trade_history.csv` columns:

**Pre-Earnings (logged during scan):**
- `scan_date`, `ticker`, `earnings_date`, `days_to_earnings`
- `spot_price`, `avg_volume_30d`
- `front_month_iv`, `back_month_iv`, `term_slope`
- `rv_30d`, `iv_rv_ratio`
- `passes_term_slope`, `passes_volume`, `passes_iv_rv`
- `recommendation` (Recommended/Consider/Avoid)
- `position_type`, `kelly_fraction`, `position_size`, `num_contracts`

**Post-Earnings (updated after):**
- `post_earnings_price`
- `stock_move_pct`
- `actual_return_pct`
- `is_win` (True/False)
- `status` (pending/completed/skipped)

## Scripts

All located in `pricing/earnings_vol/python/tracking/`:

1. **`trade_logger.py`** - Log scans to database
2. **`update_results.py`** - Update with post-earnings P&L
3. **`view_history.py`** - View accumulated history and stats

## Advantages Over Historical Backtest

✅ **Real IV data** - Actual IV at time of scan, not estimates
✅ **No API bugs** - Avoid yfinance timezone issues
✅ **Live tracking** - See strategy performance in real-time
✅ **Paper trading** - Can track if you paper trade positions
✅ **Verifiable** - Data YOU collected, not someone else's claims

## Tips

1. **Scan weekly**: Set a reminder every Monday to scan upcoming earnings
2. **Automate updates**: Run `--all` update after market close on Fridays
3. **Track paper trades**: Log positions even if just paper trading
4. **Be consistent**: Log ALL scans (even "Avoid"), not just trades
5. **Be patient**: 6-12 months to meaningful sample size

## Next Steps

1. ✅ Database initialized (1 scan logged)
2. → Scan 5-10 more tickers this week
3. → After their earnings, update results
4. → Repeat monthly to build dataset
5. → After 6+ months, run first analysis

**Start building your dataset today!**

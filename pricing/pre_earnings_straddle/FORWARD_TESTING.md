# Forward Testing: Pre-Earnings Straddles

Prospectively validate the strategy by collecting real trade data over time.

## Why Forward Test?

The backtest shows promising results:
- Filtered mean return: +3.3%
- Win rate: 42%
- Positive expected value

**We need to verify this in our own trading environment.**

Instead of fighting with historical options data, we collect prospectively:
1. Scan upcoming earnings weekly
2. Log all "Buy" recommendations
3. Track entry/exit prices in real-time
4. Analyze performance after 50+ completed trades

## Database Schema

### trade_history.csv

#### Pre-Trade Data (logged at scan)
- `scan_date`: When we ran the scan
- `ticker`: Stock symbol
- `earnings_date`: Scheduled earnings date
- `days_to_earnings`: Days until earnings
- `entry_date`: When we would enter
- `spot_price`: Stock price
- `atm_strike`: ATM strike price
- `atm_call_price`: ATM call price
- `atm_put_price`: ATM put price
- `straddle_cost`: Total debit (call + put)
- `current_implied_move`: Current implied move %
- `expiration`: Options expiration date
- `days_to_expiry`: Days to expiration

#### Four Signals
- `implied_vs_last_implied_ratio`: Signal 1
- `implied_vs_last_realized_gap`: Signal 2
- `implied_vs_avg_implied_ratio`: Signal 3
- `implied_vs_avg_realized_gap`: Signal 4
- `last_implied`: Last earnings implied move
- `last_realized`: Last earnings realized move
- `avg_implied`: Historical average implied
- `avg_realized`: Historical average realized
- `num_historical_events`: # of events in history

#### Prediction
- `predicted_return`: Model prediction %
- `recommendation`: "Strong Buy", "Buy", "Pass"
- `rank_score`: For portfolio ranking
- `kelly_fraction`: Full Kelly %
- `suggested_size`: Recommended position size %

#### Post-Trade Results (filled after exit)
- `status`: "pending" or "completed"
- `exit_date`: When we exited (day before earnings)
- `exit_straddle_price`: Straddle price at exit
- `actual_pnl`: Actual P&L in dollars
- `actual_return_pct`: Actual return %

## Workflow

### Step 1: Build Historical Earnings Database

First time setup for each ticker:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/pre_earnings_straddle/python/fetch/fetch_earnings_data.py \
  --ticker AAPL --years 3"

docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/pre_earnings_straddle/python/fetch/fetch_earnings_data.py \
  --ticker NVDA --years 3"

# ... for all tickers in your universe
```

**Native:**
```bash
uv run pricing/pre_earnings_straddle/python/fetch/fetch_earnings_data.py \
  --ticker AAPL --years 3

uv run pricing/pre_earnings_straddle/python/fetch/fetch_earnings_data.py \
  --ticker NVDA --years 3

# ... for all tickers in your universe
```

This builds the historical implied/realized moves needed for the 4 signals.

**Note:** With yfinance, implied moves are approximated. In production, use actual historical options data.

### Step 2: Weekly Scan for Opportunities

Every week, scan for upcoming earnings (10-18 days out):

**Docker:**
```bash
# Check earnings calendar for next 2 weeks
# For each upcoming earnings:

docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/pre_earnings_straddle/python/fetch/fetch_straddle_data.py \
  --ticker <TICKER>"

docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec pre_earnings_straddle -- <TICKER>"
```

**Native:**
```bash
# Check earnings calendar for next 2 weeks
# For each upcoming earnings:

uv run pricing/pre_earnings_straddle/python/fetch/fetch_straddle_data.py \
  --ticker <TICKER>

eval $(opam env) && dune exec pre_earnings_straddle -- <TICKER>
```

### Step 3: Log "Buy" Recommendations

When scanner outputs "Buy" or "Strong Buy":

1. **Manually enter the trade** (or paper trade)
2. **Log to database** (currently manual - extract values from scanner output)

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/pre_earnings_straddle/python/tracking/trade_logger.py \
  --ticker AAPL \
  --earnings-date 2026-01-28 \
  --days-to-earnings 14 \
  --spot 265.00 \
  --atm-strike 265 \
  --call-price 8.50 \
  --put-price 7.80 \
  --cost 16.30 \
  --current-implied 0.045 \
  --expiration 2026-02-20 \
  --dte 44 \
  --sig1 0.92 \
  --sig2 -0.01 \
  --sig3 0.88 \
  --sig4 -0.015 \
  --last-implied 0.049 \
  --last-realized 0.055 \
  --avg-implied 0.051 \
  --avg-realized 0.060 \
  --num-events 12 \
  --predicted-return 0.042 \
  --recommendation 'Buy' \
  --rank-score 0.042 \
  --kelly 0.08 \
  --size 0.032"
```

**Native:**
```bash
uv run pricing/pre_earnings_straddle/python/tracking/trade_logger.py \
  --ticker AAPL \
  --earnings-date 2026-01-28 \
  --days-to-earnings 14 \
  --spot 265.00 \
  --atm-strike 265 \
  --call-price 8.50 \
  --put-price 7.80 \
  --cost 16.30 \
  --current-implied 0.045 \
  --expiration 2026-02-20 \
  --dte 44 \
  --sig1 0.92 \
  --sig2 -0.01 \
  --sig3 0.88 \
  --sig4 -0.015 \
  --last-implied 0.049 \
  --last-realized 0.055 \
  --avg-implied 0.051 \
  --avg-realized 0.060 \
  --num-events 12 \
  --predicted-return 0.042 \
  --recommendation 'Buy' \
  --rank-score 0.042 \
  --kelly 0.08 \
  --size 0.032
```

### Step 4: Exit Day Before Earnings

For each pending trade, exit the day before earnings:

1. **Check straddle price** (call + put at same strikes)
2. **Close the position**
3. **Update database** with exit price

**Docker:**
```bash
# Manual update with exit price
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/pre_earnings_straddle/python/tracking/update_results.py \
  --ticker AAPL \
  --exit-price 18.75"
```

**Native:**
```bash
# Manual update with exit price
uv run pricing/pre_earnings_straddle/python/tracking/update_results.py \
  --ticker AAPL \
  --exit-price 18.75
```

This calculates:
- P&L = exit_price - entry_cost
- Return% = P&L / entry_cost * 100

### Step 5: Analyze Performance

**Docker:**
```bash
# View all trades
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/pre_earnings_straddle/python/tracking/view_history.py"

# View only "Strong Buy"
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/pre_earnings_straddle/python/tracking/view_history.py --filter 'Strong Buy'"
```

**Native:**
```bash
# View all trades
uv run pricing/pre_earnings_straddle/python/tracking/view_history.py

# View only "Strong Buy"
uv run pricing/pre_earnings_straddle/python/tracking/view_history.py --filter 'Strong Buy'
```

Output includes:
- Overall win rate and returns
- Performance by recommendation level
- Predicted vs actual returns
- Top winners/losers
- Pending trades

## Timeline & Expectations

### Short Term (1-3 months)
- 10-30 scans
- 5-15 completed trades
- High variance in results
- Too early for conclusions

### Medium Term (3-6 months)
- 30-80 scans
- 15-40 completed trades
- Confidence intervals narrowing
- Signal validation possible

### Long Term (6-12 months)
- 50-200+ scans
- Statistical significance
- Can validate:
  - True win rate
  - True expected return
  - Signal predictive power
  - Kelly fraction accuracy

## Key Questions to Answer

1. **Does the model work?**
   - Is predicted return correlated with actual?
   - Do higher predicted returns actually perform better?

2. **Do the signals work?**
   - Are cheap-vs-history trades actually better?
   - Which signal is strongest?

3. **What's the true profile?**
   - Real win rate (claimed ~42%)
   - Real return distribution
   - Real max drawdown periods

4. **Is it tradable?**
   - Sufficient liquidity?
   - Slippage acceptable?
   - Can we actually exit day before earnings consistently?

## Best Practices

### Ticker Selection
- Liquid options (tight bid-ask)
- Regular earnings (quarterly)
- Sufficient history (≥8 events)
- Mix of sectors

### Scanning Frequency
- **Weekly:** Scan upcoming earnings
- **Targeted:** 10-18 days before earnings
- **Goal:** 10+ scans per month

### Discipline
- Log ALL scans (including "Pass")
- No cherry-picking
- Exit before earnings (no exceptions)
- Track slippage and commissions

### Data Quality
- Use real bid/ask (not last price)
- Check for corporate actions
- Verify earnings dates
- Note any data issues

## File Locations

```
pricing/pre_earnings_straddle/data/
├── earnings_history.csv         # Historical implied/realized moves
├── model_coefficients.csv       # Trained model (can retrain)
└── trade_history.csv            # Forward test database
```

## Future Enhancements

Once we have enough data:

1. **Retrain model** on our own data
2. **Optimize Kelly fractions** for our execution
3. **Filter refinement** (add more signals?)
4. **Portfolio construction** (correlation, diversification)
5. **Risk management** (stop-losses, profit targets?)

## Important Notes

- This is a **long volatility** strategy - expect many losers
- Edge shows up over **many trades**, not individual names
- **Patience required** - drawdowns can last months
- **Small sizing** critical - use 2-6% Kelly
- **Discipline required** - must exit before earnings

## Data Limitations

**Current Implementation:**
- yfinance doesn't provide historical options data
- Implied moves are approximated
- Exit prices need manual tracking

**Production Requirements:**
- Historical options database (IBKR, TastyTrade)
- Real-time IV data
- Automated entry/exit tracking
- Better implied move calculations

This is a **proof of concept** implementation. For serious trading, upgrade data sources.

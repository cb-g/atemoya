# Forward Testing: Skew Vertical Spreads

This document explains how to use the forward-testing database to prospectively validate the skew-based vertical spreads strategy.

## Why Forward Testing?

The strategy makes bold claims:
- Win rate: ~30-35%
- Reward/risk: 5:1 to 10:1
- Real examples: QUBT (380%), SBET (280%), MP (400%)

**We need to verify these claims.**

Instead of fighting buggy historical APIs, we collect data prospectively:
1. Run scanner weekly/monthly
2. Log all scans to database
3. Wait for expiration
4. Update with actual results
5. Analyze performance over time

After 6-12 months, we'll have 50-200 real trades to validate the strategy.

## Database Schema

### trade_history.csv

#### Pre-Trade Columns (logged at scan time)
- `scan_date`: When scan was run
- `ticker`: Stock symbol
- `expiration`: Option expiration date
- `days_to_expiry`: Days until expiration
- `spot_price`: Stock price at scan
- `spread_type`: "bull_call" or "bear_put"
- `long_strike`: Strike of option we buy
- `short_strike`: Strike of option we sell
- `debit`: Net cost of spread
- `max_profit`: Maximum possible profit
- `reward_risk`: Reward/risk ratio
- `breakeven`: Breakeven price at expiration

#### Skew Metrics
- `atm_iv`: ATM implied volatility
- `realized_vol`: 30-day realized volatility
- `call_skew`: Call skew metric
- `call_skew_zscore`: Call skew z-score
- `put_skew`: Put skew metric
- `put_skew_zscore`: Put skew z-score
- `vrp`: Variance risk premium

#### Momentum Metrics
- `return_1m`: 1-month return
- `return_3m`: 3-month return
- `momentum_score`: Overall momentum score (-1 to +1)

#### Recommendation
- `recommendation`: "Strong Buy", "Buy", or "Pass"
- `edge_score`: Edge score (0-100)
- `expected_value`: Predicted EV
- `prob_profit`: Predicted probability of profit

#### Filters
- `passes_skew_filter`: True/False
- `passes_ivrv_filter`: True/False
- `passes_momentum_filter`: True/False

#### Post-Trade Columns (filled after expiration)
- `status`: "pending" or "completed"
- `close_date`: When trade was closed
- `exit_spot_price`: Stock price at expiration
- `actual_pnl`: Actual profit/loss in dollars
- `actual_return_pct`: Actual return percentage

## Workflow

### Step 1: Run Scanner and Log Results

**Docker:**
```bash
# 1. Fetch fresh data
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_verticals/python/fetch/fetch_options_chain.py --ticker AAPL"
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_verticals/python/fetch/fetch_prices.py --ticker AAPL"

# 2. Run scanner
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec skew_verticals -- AAPL"

# 3. If you get a recommendation, log it to the database
# (You'll need to extract values from the scanner output and pass them to trade_logger.py)
```

**Native:**
```bash
# 1. Fetch fresh data
uv run pricing/skew_verticals/python/fetch/fetch_options_chain.py --ticker AAPL
uv run pricing/skew_verticals/python/fetch/fetch_prices.py --ticker AAPL

# 2. Run scanner
eval $(opam env) && dune exec skew_verticals -- AAPL

# 3. If you get a recommendation, log it to the database
# (You'll need to extract values from the scanner output and pass them to trade_logger.py)
```

The scanner will output all the metrics you need. You can manually log them, or we can extend the OCaml code to call the Python logger automatically.

### Step 2: Wait for Expiration

Do nothing. Let time pass. The trades are logged with status="pending".

### Step 3: Update Results After Expiration

**Docker:**
```bash
# Update all expired pending trades
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_verticals/python/tracking/update_results.py"

# Or update a specific trade
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_verticals/python/tracking/update_results.py \
  --ticker AAPL \
  --expiration 2026-02-06"
```

**Native:**
```bash
# Update all expired pending trades
uv run pricing/skew_verticals/python/tracking/update_results.py

# Or update a specific trade
uv run pricing/skew_verticals/python/tracking/update_results.py \
  --ticker AAPL \
  --expiration 2026-02-06
```

This script:
1. Finds pending trades past their expiration
2. Fetches the stock price at expiration
3. Calculates actual P&L using spread payoff formulas
4. Updates the database with results

### Step 4: Analyze Performance

**Docker:**
```bash
# View all trades
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_verticals/python/tracking/view_history.py"

# View only "Strong Buy" recommendations
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_verticals/python/tracking/view_history.py --filter 'Strong Buy'"
```

**Native:**
```bash
# View all trades
uv run pricing/skew_verticals/python/tracking/view_history.py

# View only "Strong Buy" recommendations
uv run pricing/skew_verticals/python/tracking/view_history.py --filter 'Strong Buy'
```

Output includes:
- Overall win rate and average return
- Performance by recommendation level
- Performance by spread type
- Top winners and losers
- Pending trades

## Example Output

```
=== Trade History Summary ===
Total scans: 47
Pending: 12
Completed: 35

=== Recommendations ===
  Strong Buy: 8
  Buy: 15
  Pass: 24

=== Completed Trades Performance ===
Total completed: 35

Overall:
  Win rate: 34.3% (12W/23L)
  Average return: +8.2%
  Median return: -12.5%

By Recommendation:
  Strong Buy: 5 trades | 60.0% win rate | +42.1% avg return
  Buy: 12 trades | 33.3% win rate | +5.8% avg return
  Pass: 18 trades | 22.2% win rate | -8.9% avg return

By Spread Type:
  bull_call: 22 trades | 36.4% win rate | +10.3% avg return
  bear_put: 13 trades | 30.8% win rate | +4.7% avg return

=== Top 5 Winners ===
  ticker spread_type  actual_return_pct  actual_pnl recommendation
    QUBT   bull_call              380.5       15.22     Strong Buy
    SBET   bull_call              280.3       11.21     Strong Buy
      MP    bear_put              145.8        8.75            Buy
```

## Timeline

### Short Term (1-3 months)
- 10-30 scans logged
- 5-15 completed trades
- Early signal on filter effectiveness
- Initial win rate estimates (high variance)

### Medium Term (3-6 months)
- 30-80 scans logged
- 15-40 completed trades
- Confidence intervals narrowing
- Strategy refinements possible

### Long Term (6-12 months)
- 50-200+ scans logged
- Statistical significance achieved
- Validate or reject claimed performance
- Enough data for:
  - Sharpe ratio calculation
  - Drawdown analysis
  - Filter optimization
  - Position sizing calibration

## Key Questions to Answer

1. **Does the skew filter work?**
   - Compare win rates: passes skew filter vs fails
   - Compare returns: extreme skew vs normal skew

2. **Does momentum help?**
   - Compare: with momentum filter vs without
   - Is directional edge real or noise?

3. **What's the true win rate?**
   - Claimed: 30-35%
   - Need 50+ trades for 95% confidence interval

4. **Are asymmetric payoffs real?**
   - Do winners actually average 5-10x losers?
   - Or is it survivorship bias from cherry-picked examples?

5. **Which recommendation level works?**
   - "Strong Buy" only?
   - "Buy" + "Strong Buy"?
   - What edge score threshold?

## Best Practices

### Scan Frequency
- **Weekly:** Scan 5-10 high-volume tickers every week
- **Event-driven:** Scan after earnings, big moves, volatility spikes
- **Goal:** ~10 scans per month = 120/year

### Ticker Selection
- High liquidity (tight bid-ask spreads)
- Active options market (OI > 1000)
- Clear momentum signals
- Mix of sectors

### Data Quality
- Always fetch fresh data before scanning
- Verify bid-ask spreads are reasonable (<5% of mid)
- Check for corporate actions (splits, dividends)
- Log any data issues in notes field

### Discipline
- Log ALL scans, not just "Strong Buy"
- Include "Pass" recommendations
- No cherry-picking results
- Update results systematically after expiration

## File Locations

```
pricing/skew_verticals/data/
├── trade_history.csv           # Main database
├── AAPL_2026-02-06_calls.csv  # Options data snapshots
├── AAPL_2026-02-06_puts.csv
├── AAPL_prices.csv             # Price history
└── SPY_prices.csv              # Market data
```

## Future Enhancements

Once we have enough data:

1. **Automated logging:** Extend OCaml scanner to call Python logger automatically
2. **Backadjustment:** Track implied vol changes over trade lifetime
3. **Greeks tracking:** Log delta, gamma, theta daily
4. **Risk management:** Implement stop-losses, profit targets
5. **Portfolio view:** Multiple concurrent positions, correlation
6. **Visualization:** P&L curves, win rate by filter, etc.

## Notes

- This is a **prospective** study - we log scans as we go, not retroactively
- Results are **unbiased** - we track everything, not just winners
- Timeline is **patient** - 6-12 months minimum for valid conclusions
- Goal is **validation** - does this strategy actually work as claimed?

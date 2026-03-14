# Dispersion Trading

Trade the volatility dispersion between an index and its constituents.

## Concept

**Dispersion** is the difference between index implied volatility and the weighted average of single-name implied volatilities.

- **Long Dispersion**: Buy single-name options, sell index options
  - Profits when stocks move independently (low realized correlation)
  - Bet: σ_avg > σ_index

- **Short Dispersion**: Sell single-name options, buy index options
  - Profits when stocks move together (high realized correlation)
  - Bet: σ_index > σ_avg

## Key Metrics

1. **Dispersion Level**: σ_avg - σ_index
2. **Implied Correlation**: ρ_impl = (σ_index² - Σw_i²σ_i²) / (2Σw_i w_j σ_i σ_j)
3. **Realized Correlation**: From historical price comovement
4. **Z-Score**: Mean reversion signal

## Daily Signal Pipeline

Three-stage automated pipeline: **collect** (after market close) → **scan** (after collection) → **notify** (before market open).

Lightweight — fetches IV for 1 index + 10 constituents (~11 API calls). One row per day in history.

**What gets stored:**
- `data/snapshots/{YYYY-MM-DD}.json` - Full snapshot archive per day
- `data/dispersion_history.csv` - Append-only history of daily dispersion/correlation metrics

#### Automated Cron Setup

All times below are UTC. Runs Tue-Sat to capture Mon-Fri market data.

**Native (uv installed on host):**
```bash
# 1. Collect dispersion snapshot (index + constituents)
30 7 * * 2-6 cd /path/to/atemoya && uv run pricing/dispersion_trading/python/fetch/collect_snapshot.py >> /tmp/dispersion_collect.log 2>&1

# 2. Run signal scanner after collection completes
45 7 * * 2-6 cd /path/to/atemoya && uv run pricing/dispersion_trading/python/scan_signals.py --quiet --output pricing/dispersion_trading/output/signal_scan.csv >> /tmp/dispersion_scan.log 2>&1

# 3. Send morning trade notifications (before market open)
35 9 * * 1-5 cd /path/to/atemoya && uv run pricing/dispersion_trading/python/notify_signals.py >> /tmp/dispersion_notify.log 2>&1
```

**Docker (from host crontab):**
```bash
30 7 * * 2-6 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/dispersion_trading/python/fetch/collect_snapshot.py" >> /tmp/dispersion_collect.log 2>&1
45 7 * * 2-6 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/dispersion_trading/python/scan_signals.py --quiet --output pricing/dispersion_trading/output/signal_scan.csv" >> /tmp/dispersion_scan.log 2>&1
35 9 * * 1-5 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/dispersion_trading/python/notify_signals.py" >> /tmp/dispersion_notify.log 2>&1
```

Notifications require `NTFY_TOPIC` set in `.env` at the project root.

#### Manual / Ad-hoc Usage

```bash
# Collect with default constituents (top 10 S&P 500)
uv run pricing/dispersion_trading/python/fetch/collect_snapshot.py

# Collect with custom constituents
uv run pricing/dispersion_trading/python/fetch/collect_snapshot.py --constituents AAPL,MSFT,GOOGL,AMZN,NVDA

# Dry-run notification
uv run pricing/dispersion_trading/python/notify_signals.py --dry-run
```

## Workflow (OCaml)

For the original OCaml analysis:

**Docker:**
```bash
# 1. Fetch options data for index and constituents
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/dispersion_trading/python/fetch/fetch_options.py --index SPY --constituents AAPL,MSFT,GOOGL,AMZN,NVDA"

# 2. Run analysis
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec dispersion_trading -- --mode analyze"

# 3. Run backtest
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec dispersion_trading -- --mode backtest"

# 4. Visualize
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/dispersion_trading/python/viz/plot_dispersion.py"
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/dispersion_trading/python/viz/plot_correlation.py"
```

**Native:**
```bash
# 1. Fetch options data for index and constituents
uv run pricing/dispersion_trading/python/fetch/fetch_options.py --index SPY --constituents AAPL,MSFT,GOOGL,AMZN,NVDA

# 2. Run analysis
eval $(opam env) && dune exec dispersion_trading -- --mode analyze

# 3. Run backtest
eval $(opam env) && dune exec dispersion_trading -- --mode backtest

# 4. Visualize
uv run pricing/dispersion_trading/python/viz/plot_dispersion.py
uv run pricing/dispersion_trading/python/viz/plot_correlation.py
```

## Output

- `data/`: Market data CSVs
- `output/`: Backtest results, metrics
- `output/*.png`: Visualizations

## Strategy

- **Entry**: Z-score > 1.5 (long) or < -1.5 (short)
- **Exit**: Mean reversion or expiry
- **Hedging**: Delta-neutral (rebalance daily)
- **P&L Attribution**: Vol, gamma, theta, correlation

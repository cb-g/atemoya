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

## Workflow

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

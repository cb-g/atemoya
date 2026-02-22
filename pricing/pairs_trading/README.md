# Pairs Trading

Statistical arbitrage strategy trading the mean-reverting spread between two cointegrated assets.

## Concept

**Pairs trading** exploits temporary divergences in the relationship between two historically correlated assets.

### Key Concepts

1. **Cointegration**: Two price series that move together long-term
   - Test: Engle-Granger (regression + ADF test on residuals)
   - Requirement: Spread must be stationary

2. **Hedge Ratio (β)**: Optimal ratio to combine assets
   - From regression: Y = α + βX + ε
   - Trade: Buy/sell β units of X for each unit of Y

3. **Spread**: Mean-reverting residual
   - Spread = Y - (βX + α)
   - Trade when spread deviates from mean

4. **Z-Score**: Normalized spread distance from mean
   - Z = (Spread - Mean) / StdDev
   - Entry: |Z| > 2.0
   - Exit: |Z| < 0.5

## Trading Rules

- **Long Spread** (Z < -2.0): Buy Y, Sell X
  - Bet: Spread will increase (Y outperforms X)

- **Short Spread** (Z > 2.0): Sell Y, Buy X
  - Bet: Spread will decrease (X outperforms Y)

- **Exit**: Z reverts to mean (|Z| < 0.5)

## Workflow

**Docker:**
```bash
# 1. Fetch pair data
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/pairs_trading/python/fetch/fetch_pairs.py --ticker1 GLD --ticker2 GDX --days 252"

# 2. Test cointegration
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec pairs_trading"

# 3. Visualize
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/pairs_trading/python/viz/plot_pairs.py"
```

**Native:**
```bash
# 1. Fetch pair data
uv run pricing/pairs_trading/python/fetch/fetch_pairs.py --ticker1 GLD --ticker2 GDX --days 252

# 2. Test cointegration
eval $(opam env) && dune exec pairs_trading

# 3. Visualize
uv run pricing/pairs_trading/python/viz/plot_pairs.py
```

## Classic Pairs

- **GLD/GDX**: Gold vs Gold Miners
- **XLE/USO**: Energy sector vs Crude Oil
- **EWA/EWC**: Australia vs Canada (resource economies)
- **AAPL/MSFT**: Tech mega-caps
- **PEP/KO**: Pepsi vs Coca-Cola

## Output

- `data/pair_data.csv`: Historical prices
- `data/metadata.csv`: Pair information
- `output/pairs_analysis.png`: Full visualization

## Metrics

- **Hedge Ratio**: β from cointegrating regression
- **Half-Life**: Mean reversion speed (days)
- **ADF Statistic**: Stationarity test
- **Current Z-Score**: Entry signal
- **Correlation**: Price relationship strength

## Strategy

- **Entry**: Z-score > 2.0 or < -2.0
- **Exit**: Mean reversion (|Z| < 0.5)
- **Stop Loss**: Z-score > 4.0 (spread blown out)
- **Position Sizing**: Based on hedge ratio β

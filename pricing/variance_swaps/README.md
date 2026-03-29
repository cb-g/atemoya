# Variance Swaps & Variance Risk Premium (VRP) Trading

Systematic trading strategy to harvest the **Variance Risk Premium** - the persistent gap between implied and realized volatility.

## What It Does

This model:
1. **Prices variance swaps** using the Carr-Madan replication formula
2. **Computes the Variance Risk Premium (VRP)** = Implied Variance - Realized Variance
3. **Generates trading signals** to systematically short variance when VRP is elevated
4. **Constructs replication portfolios** using vanilla options to synthetically trade variance
5. **Backtests VRP strategies** with P&L tracking and Sharpe ratio calculation

### Why Variance Swaps?

- **Pure volatility exposure**: Variance swaps are linear in variance, unlike options
- **No delta risk**: Variance swaps isolate volatility risk from directional market moves
- **Variance Risk Premium**: Historically, implied variance > realized variance by 2-5% (annualized Sharpe ~1.5-2.0)
- **Systematic alpha**: VRP is persistent across assets and time periods

## Core Concepts

### Variance Swap Payoff

```
Payoff = Notional × (Realized_Variance - Variance_Strike)
```

Where:
- **Realized Variance**: Annualized variance computed from daily log-returns
- **Variance Strike**: Fair value from Carr-Madan formula using option prices

### Carr-Madan Replication Formula

```
K_var = (2/T)·e^(rT)·[∫₀^F (P(K)/K²)dK + ∫_F^∞ (C(K)/K²)dK]
```

**Discrete approximation**:
```
K_var = (2/T)·e^(rT)·Σᵢ [(Option_i / K_i²) · ΔK_i]
```

Where:
- Option_i = Put(K_i) if K_i < F, else Call(K_i)
- F = forward price
- ΔK_i = strike spacing (midpoint rule)

### Variance Risk Premium (VRP)

```
VRP = IV² - E[RV²]
VRP% = (IV² - E[RV²]) / IV² × 100
```

**Trading rule**:
- **VRP% > +2%** → Short variance (IV overpriced)
- **VRP% < -1%** → Long variance (IV underpriced)
- Otherwise → Neutral

### Vega Notional

```
Vega_Notional = Notional / (2·√K_var)
```

This is the P&L sensitivity per 1% move in volatility.

## Quick Start

### 1. Fetch Market Data

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/variance_swaps/python/fetch_data.py \
  --ticker SPY \
  --lookback 365 \
  --output pricing/variance_swaps/data"
```

**Native:**
```bash
uv run pricing/variance_swaps/python/fetch_data.py \
  --ticker SPY \
  --lookback 365 \
  --output pricing/variance_swaps/data
```

This fetches:
- Historical OHLC price data
- Current spot price and dividend yield
- Options chain for volatility surface calibration

### 2. Price Variance Swap

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec variance_swaps -- \
  -ticker SPY \
  -op price \
  -horizon 30 \
  -notional 100000 \
  -strikes 20"
```

**Native:**
```bash
eval $(opam env) && dune exec variance_swaps -- \
  -ticker SPY \
  -op price \
  -horizon 30 \
  -notional 100000 \
  -strikes 20
```

**Output**: `pricing/variance_swaps/output/SPY_variance_swap.csv`

Contains:
- Variance strike (K_var)
- Volatility strike (√K_var)
- Vega notional
- Entry date and spot

### 3. Compute VRP

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec variance_swaps -- \
  -ticker SPY \
  -op vrp \
  -horizon 30 \
  -estimator yz \
  -forecast garch"
```

**Native:**
```bash
eval $(opam env) && dune exec variance_swaps -- \
  -ticker SPY \
  -op vrp \
  -horizon 30 \
  -estimator yz \
  -forecast garch
```

**Output**: `pricing/variance_swaps/output/SPY_vrp_yz_garch.csv`

Shows:
- Implied variance (from options)
- Forecast realized variance (from historical returns)
- VRP (absolute and percentage)

### 4. Generate Trading Signal

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec variance_swaps -- \
  -ticker SPY \
  -op signal \
  -horizon 30 \
  -estimator yz \
  -forecast garch"
```

**Native:**
```bash
eval $(opam env) && dune exec variance_swaps -- \
  -ticker SPY \
  -op signal \
  -horizon 30 \
  -estimator yz \
  -forecast garch
```

**Output**: `pricing/variance_swaps/output/SPY_signal_yz_garch.csv`

Signal types:
- **SHORT**: VRP > threshold → sell variance
- **LONG**: VRP < threshold → buy variance
- **NEUTRAL**: VRP within neutral zone

### 5. Build Replication Portfolio

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec variance_swaps -- \
  -ticker SPY \
  -op replicate \
  -notional 100000 \
  -strikes 20"
```

**Native:**
```bash
eval $(opam env) && dune exec variance_swaps -- \
  -ticker SPY \
  -op replicate \
  -notional 100000 \
  -strikes 20
```

**Output**: `pricing/variance_swaps/output/SPY_replication.csv`

Portfolio contains:
- OTM puts (K < F): weights = 2·ΔK / K²
- OTM calls (K ≥ F): weights = 2·ΔK / K²
- Total delta (should be near-zero)
- Total vega
- Total cost

### 6. Visualize Results

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/variance_swaps/python/viz_vrp.py \
  --vrp pricing/variance_swaps/output/SPY_vrp_yz_garch.csv \
  --signals pricing/variance_swaps/output/SPY_signal_yz_garch.csv \
  --output-dir pricing/variance_swaps/output \
  --estimator yz --forecast garch"
```

**Native:**
```bash
uv run pricing/variance_swaps/python/viz_vrp.py \
  --vrp pricing/variance_swaps/output/SPY_vrp_yz_garch.csv \
  --signals pricing/variance_swaps/output/SPY_signal_yz_garch.csv \
  --output-dir pricing/variance_swaps/output \
  --estimator yz --forecast garch
```

Generates:
- VRP time series (implied vs realized variance)
- Trading signals over time
- Position sizing by confidence

## Implementation Details

### OCaml Modules

1. **types.ml**: Core data structures
   - `variance_swap`: Variance swap specification
   - `vrp_observation`: VRP time series point
   - `vrp_trading_signal`: Trading signal with confidence
   - `replication_portfolio`: Option portfolio for replication

2. **variance_swap_pricing.ml**: Carr-Madan pricing
   - `price_variance_swap`: Price variance swap from option grid
   - `carr_madan_discrete`: Discrete Carr-Madan integration
   - `variance_swap_payoff`: Payoff at maturity

3. **realized_variance.ml**: Realized variance estimators
   - `compute_realized_variance`: Close-to-close variance
   - `parkinson_estimator`: High-low range estimator (5x more efficient)
   - `garman_klass_estimator`: OHLC estimator (8x more efficient)
   - `yang_zhang_estimator`: Overnight + intraday (14x more efficient)
   - `forecast_ewma`: EWMA forecasting
   - `forecast_garch`: GARCH(1,1) forecasting

4. **vrp_calculation.ml**: VRP and signal generation
   - `compute_vrp`: Calculate VRP from implied and realized variance
   - `generate_signal`: Trading signal from VRP observation
   - `backtest_vrp_strategy`: Simulate P&L from VRP signals
   - `vrp_statistics`: Mean, std, Sharpe ratio
   - `kelly_position_size`: Optimal sizing via Kelly criterion

5. **replication.ml**: Option portfolio construction
   - `build_replication_portfolio`: Construct Carr-Madan portfolio
   - `portfolio_greeks`: Delta, vega, gamma
   - `rebalance_portfolio`: Adjust weights as spot moves
   - `optimize_strike_grid`: Optimal strike selection

### Python Scripts

- **fetch_data.py**: Download market data (yfinance)
- **collect_snapshot.py**: Daily vol surface snapshot collector (cron-ready)
- **viz_vrp.py**: Visualize VRP and signals (matplotlib, Kanagawa Dragon palette)

## Output Files

### Data Files (input)
- `{TICKER}_prices.csv`: Historical OHLC data
- `{TICKER}_underlying.json`: Spot price, dividend yield
- `{TICKER}_vol_surface.json`: Calibrated SVI parameters

### Results (output)
- `{TICKER}_variance_swap.csv`: Variance swap pricing details
- `{TICKER}_vrp_{EST}_{FC}.csv`: VRP time series (e.g. `SPY_vrp_yz_garch.csv`)
- `{TICKER}_signal_{EST}_{FC}.csv`: Trading signals (e.g. `SPY_signal_cc_historical.csv`)
- `{TICKER}_replication.csv`: Replication portfolio legs
- `{TICKER}_pnl.csv`: Strategy P&L (if backtested)

### Visualizations
- `{TICKER}_vrp_{EST}_{FC}_plot.png`: VRP time series charts
- `{TICKER}_signal_{EST}_{FC}_plot.png`: Trading signals
- `{TICKER}_pnl_plot.png`: P&L and Sharpe ratio

## Strategy Interpretation

### VRP Statistics

**Typical values** (equity indices like SPY, QQQ):
- Mean VRP: +2% to +5% (positive on average)
- VRP Sharpe ratio: 1.5 to 2.0 (annualized)
- Hit rate: ~60% (wins > losses)

**Why VRP exists**:
1. **Demand for portfolio insurance**: Investors pay premium for downside protection
2. **Risk aversion**: Market participants overestimate tail risk
3. **Supply/demand imbalance**: More buyers than sellers of volatility

### Trading Signals

**Short Variance Signal** (most common):
- Trigger: VRP% > +2%
- Action: Sell variance swap (or replicate with options)
- Expectation: Realized volatility < Implied volatility
- Profit: Collect variance premium

**Long Variance Signal** (rare, but profitable):
- Trigger: VRP% < -1% (negative VRP)
- Action: Buy variance swap
- Expectation: Realized volatility > Implied volatility
- Use case: Crisis periods, IV crash after spike

### Risk Management

**Key risks**:
1. **Gamma risk**: Large spot moves can blow up short variance positions
2. **Jump risk**: Tail events (COVID, 2008) cause massive realized variance spikes
3. **Vol of vol**: Variance swaps have convexity (long gamma-of-variance)

**Mitigation**:
- Size positions conservatively (half-Kelly or less)
- Use stop-losses on P&L
- Roll positions before expiry to avoid gamma buildup
- Diversify across multiple underlyings
- Hedge tail risk with OTM puts

## Example Workflow

**Docker:**
```bash
# 1. Fetch data for SPY
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/variance_swaps/python/fetch_data.py --ticker SPY"

# 2. Price variance swap (30-day)
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec variance_swaps -- -ticker SPY -op price -horizon 30"

# 3. Compute VRP
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec variance_swaps -- -ticker SPY -op vrp -estimator yz -forecast garch"

# 4. Generate signal
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec variance_swaps -- -ticker SPY -op signal -estimator yz -forecast garch"

# 5. Build replication portfolio
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec variance_swaps -- -ticker SPY -op replicate"

# 6. Visualize
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/variance_swaps/python/viz_vrp.py \
  --vrp pricing/variance_swaps/output/SPY_vrp_yz_garch.csv \
  --signals pricing/variance_swaps/output/SPY_signal_yz_garch.csv \
  --estimator yz --forecast garch"
```

**Native:**
```bash
# 1. Fetch data for SPY
uv run pricing/variance_swaps/python/fetch_data.py --ticker SPY

# 2. Price variance swap (30-day)
eval $(opam env) && dune exec variance_swaps -- -ticker SPY -op price -horizon 30

# 3. Compute VRP
eval $(opam env) && dune exec variance_swaps -- -ticker SPY -op vrp -estimator yz -forecast garch

# 4. Generate signal
eval $(opam env) && dune exec variance_swaps -- -ticker SPY -op signal -estimator yz -forecast garch

# 5. Build replication portfolio
eval $(opam env) && dune exec variance_swaps -- -ticker SPY -op replicate

# 6. Visualize
uv run pricing/variance_swaps/python/viz_vrp.py \
  --vrp pricing/variance_swaps/output/SPY_vrp_yz_garch.csv \
  --signals pricing/variance_swaps/output/SPY_signal_yz_garch.csv \
  --estimator yz --forecast garch
```

## Daily Snapshot Collection

The backtest uses a constant ATM IV (20%) by default because historical vol surface data is expensive or unavailable. The snapshot collector builds your own implied variance history over time.

### Single Run

**Docker:**
```bash
# Collect today's snapshot for one ticker
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/variance_swaps/python/collect_snapshot.py --ticker SPY"

# Collect for multiple tickers
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/variance_swaps/python/collect_snapshot.py --tickers SPY,QQQ,IWM"
```

**Native:**
```bash
# Collect today's snapshot for one ticker
uv run pricing/variance_swaps/python/collect_snapshot.py --ticker SPY

# Collect for multiple tickers
uv run pricing/variance_swaps/python/collect_snapshot.py --tickers SPY,QQQ,IWM
```

Each run:
- Archives full SVI snapshot to `data/snapshots/{TICKER}/{YYYY-MM-DD}.json`
- Appends one row to `data/{TICKER}_iv_history.csv`
- Idempotent: skips tickers already collected today

### Automated Cron Setup

The daily pipeline has three stages: **collect** (after market close) → **scan** (after collection) → **notify** (before market open). All times below are UTC. Collectors run on Tue-Sat (for Mon-Fri market data).

**Native (uv installed on host):**

Cron runs with minimal PATH — add this line to the top of your crontab so `uv` is found:
```
PATH=/home/devusr/.local/bin:/usr/local/bin:/usr/bin:/bin
```

```bash
# 1. Collect IV snapshots for all liquid tickers
15 1 * * 2-6 cd /path/to/atemoya && uv run pricing/variance_swaps/python/collect_snapshot.py --tickers all_liquid >> /tmp/variance_collect.log 2>&1

# 2. Run signal scanner after collection completes
30 2 * * 2-6 cd /path/to/atemoya && uv run pricing/variance_swaps/python/scan_signals.py --segments --quiet --output pricing/variance_swaps/output/signal_scan.csv >> /tmp/variance_scan.log 2>&1

# 3. Send morning trade notifications (before market open)
5 9 * * 1-5 cd /path/to/atemoya && uv run pricing/variance_swaps/python/notify_signals.py >> /tmp/variance_notify.log 2>&1
```

**Docker (from host crontab):**
```bash
15 1 * * 2-6 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/variance_swaps/python/collect_snapshot.py --tickers all_liquid" >> /tmp/variance_collect.log 2>&1
30 2 * * 2-6 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/variance_swaps/python/scan_signals.py --segments --quiet --output pricing/variance_swaps/output/signal_scan.csv" >> /tmp/variance_scan.log 2>&1
5 9 * * 1-5 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/variance_swaps/python/notify_signals.py" >> /tmp/variance_notify.log 2>&1
```

Notifications require `NTFY_TOPIC` set in `.env` at the project root.

### Adding Tickers

Use `--tickers all_liquid` to automatically collect all tickers from the liquidity module. Alternatively, pass specific tickers: `--tickers SPY,QQQ,IWM`. Each ticker gets its own independent history file. New tickers start collecting from day 1; existing tickers are idempotently skipped. After enough days accumulate (60+), the backtest can use real time-varying IV instead of the constant 20% assumption.

## Future Enhancements

- Volatility swaps (with convexity adjustment)
- VIX futures trading (term structure arbitrage)
- Cross-sectional VRP (long/short across assets)
- Dynamic delta hedging simulation
- Gamma scalping strategies
- Conditional VRP (regime-dependent thresholds)

---

**Model Type**: Derivatives Pricing + Systematic Trading
**Strategy**: Variance Risk Premium Harvesting
**Expected Sharpe**: 1.5-2.0 (short variance on SPY/QQQ)
**Implementation**: OCaml (pricing) + Python (data/viz)

# Skew Trading

Trade volatility skew using risk reversals, butterflies, and other multi-leg option strategies.

## What is Volatility Skew?

**Volatility skew** (or volatility smile) refers to the pattern where implied volatility varies across option strikes. For equities, puts typically have higher IV than calls at the same expiry - this is called **put skew** or **negative skew**.

### Key Metrics

- **RR25 (25-Delta Risk Reversal)**: `IV(25Δ Call) - IV(25Δ Put)`
  - For equities: typically **negative** (-3% to -5% for SPY)
  - Measures left-right asymmetry of the volatility smile

- **BF25 (25-Delta Butterfly)**: `[IV(25Δ Call) + IV(25Δ Put)] / 2 - IV(ATM)`
  - Typically **positive** (+1% to +3%)
  - Measures curvature (smile vs flat)

- **Skew Slope**: Linear regression of IV vs log-moneyness
  - Captures overall tilt of the volatility surface

## Trading Strategy

### Mean Reversion Signal

Skew exhibits mean reversion:
- When RR25 is **less negative than usual** (e.g., -2% vs historical -4%): Skew is **cheap** → **Long skew**
- When RR25 is **more negative than usual** (e.g., -6% vs historical -4%): Skew is **rich** → **Short skew**

Signal generation:
```
z_score = (current_RR25 - historical_mean) / historical_std

if z_score > +2.0:
    Signal = LONG_SKEW (buy call, sell put)
elif z_score < -2.0:
    Signal = SHORT_SKEW (sell call, buy put)
else:
    Signal = NEUTRAL
```

### Strategies

1. **Risk Reversal**: Buy call + Sell put (or vice versa)
   - Pure skew exposure
   - Zero cost if strikes chosen correctly

2. **Butterfly**: Buy OTM put + Sell 2 ATM + Buy OTM call
   - Profits from smile flattening
   - Defined risk

3. **Ratio Spread**: Buy N options at one strike, sell M at another
   - Leveraged skew exposure

4. **Calendar Spread**: Long near-term + Short far-term
   - Exploits term structure of skew

## Quick Start

### 1. Fetch Data

**Docker:**
```bash
# Fetch underlying data (spot, dividend yield, prices)
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_trading/python/fetch/fetch_underlying.py --ticker TSLA"

# Fetch option chain and calibrate SVI surface
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_trading/python/fetch/fetch_options.py --ticker TSLA"

# Compute historical skew timeseries
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_trading/python/fetch/compute_skew_timeseries.py --ticker TSLA"
```

**Native:**
```bash
# Fetch underlying data (spot, dividend yield, prices)
uv run pricing/skew_trading/python/fetch/fetch_underlying.py --ticker TSLA

# Fetch option chain and calibrate SVI surface
uv run pricing/skew_trading/python/fetch/fetch_options.py --ticker TSLA

# Compute historical skew timeseries
uv run pricing/skew_trading/python/fetch/compute_skew_timeseries.py --ticker TSLA
```

**Outputs:**
- `data/TSLA_underlying.json` - Spot price, dividend yield
- `data/TSLA_vol_surface.json` - SVI parameters
- `data/TSLA_skew_timeseries.csv` - Historical RR25/BF25

### 2. Measure Skew

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec skew_trading -- -ticker TSLA -op measure -expiry 30"
```

**Native:**
```bash
eval $(opam env) && dune exec skew_trading -- -ticker TSLA -op measure -expiry 30
```

**Output:**
```
✓ Skew measured
  RR25: -4.23% (negative = put skew)
  BF25: +2.15% (positive = smile)
  ATM Vol: 18.50%
  25Δ Put: 19.80% @ $480.25
  25Δ Call: 17.35% @ $529.75
```

### 3. Generate Trading Signal

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec skew_trading -- -ticker TSLA -op signal"
```

**Native:**
```bash
eval $(opam env) && dune exec skew_trading -- -ticker TSLA -op signal
```

**Output:**
```
✓ Signal generated
  Signal: LONG_SKEW (buy call, sell put)
  Reason: RR25 -2.50% (z-score 2.35) above mean -4.20% - skew is cheap
  Confidence: 0.78
  Position Size: $7800.00
```

### 4. Build Skew Position

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec skew_trading -- -ticker TSLA -op position -expiry 30 -notional 10000"
```

**Native:**
```bash
eval $(opam env) && dune exec skew_trading -- -ticker TSLA -op position -expiry 30 -notional 10000
```

**Output:**
```
✓ Risk reversal position built
  Legs: 2
  Cost: $250.50
  Delta: 0.02
  Vega: 102.35
  Gamma: 0.005
```

### 5. Backtest Strategy

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec skew_trading -- -ticker TSLA -op backtest"
```

**Native:**
```bash
eval $(opam env) && dune exec skew_trading -- -ticker TSLA -op backtest
```

**Output:**
```
✓ Backtest complete
  Observations: 252
  Cumulative P&L: $4,523.50
  Sharpe Ratio: 1.25
```

### 6. Visualize Results

**Docker:**
```bash
# Volatility smile
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_trading/python/viz/plot_smile.py --ticker TSLA"

# Skew timeseries (RR25, BF25)
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_trading/python/viz/plot_skew_ts.py --ticker TSLA"

# Backtest P&L
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_trading/python/viz/plot_pnl.py --ticker TSLA"
```

**Native:**
```bash
# Volatility smile
uv run pricing/skew_trading/python/viz/plot_smile.py --ticker TSLA

# Skew timeseries (RR25, BF25)
uv run pricing/skew_trading/python/viz/plot_skew_ts.py --ticker TSLA

# Backtest P&L
uv run pricing/skew_trading/python/viz/plot_pnl.py --ticker TSLA
```

**Outputs:**
- `output/SPY_vol_smile.png` - IV surface and term structure
- `output/SPY_skew_timeseries.png` - RR25/BF25 over time with mean reversion bands
- `output/SPY_backtest_pnl.png` - Cumulative P&L, Sharpe, drawdown

### Daily Collection (Real Historical Data)

The module supports accumulating real historical skew data by running a daily collector after market close. Once enough real data is collected (60+ trading days), the synthetic timeseries is automatically replaced with real market observations.

#### Manual Collection

**Docker:**
```bash
# Collect today's vol surface snapshot for one ticker
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_trading/python/fetch/collect_snapshot.py --ticker TSLA"

# Collect for multiple tickers
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/skew_trading/python/fetch/collect_snapshot.py --tickers TSLA,AAPL,QQQ"
```

**Native:**
```bash
# Collect today's vol surface snapshot for one ticker
uv run pricing/skew_trading/python/fetch/collect_snapshot.py --ticker TSLA

# Collect for multiple tickers
uv run pricing/skew_trading/python/fetch/collect_snapshot.py --tickers TSLA,AAPL,QQQ
```

**What gets stored:**
- `data/snapshots/{TICKER}/{YYYY-MM-DD}.json` - Full SVI surface archive per day
- `data/{TICKER}_skew_history.csv` - Append-only history of daily skew metrics

#### Automated Cron Setup

The daily pipeline has three stages: **collect** (after market close) → **scan** (after collection) → **notify** (before market open). All times below are UTC.

**Native (uv installed on host):**
```bash
# 1. Collect option chain snapshots for all liquid tickers (weekday evenings)
15 22 * * 1-5 cd /path/to/atemoya && uv run pricing/skew_trading/python/fetch/collect_snapshot.py --tickers all_liquid >> /tmp/skew_collect.log 2>&1

# 2. Run signal scanner after collection completes
30 23 * * 1-5 cd /path/to/atemoya && uv run pricing/skew_trading/python/scan_signals.py --segments --quiet --output pricing/skew_trading/output/signal_scan.csv >> /tmp/skew_scan.log 2>&1

# 3. Send morning trade notifications (before market open)
0 9 * * 1-5 cd /path/to/atemoya && uv run pricing/skew_trading/python/notify_signals.py >> /tmp/skew_notify.log 2>&1
```

**Docker (from host crontab):**
```bash
15 22 * * 1-5 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/skew_trading/python/fetch/collect_snapshot.py --tickers all_liquid" >> /tmp/skew_collect.log 2>&1
30 23 * * 1-5 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/skew_trading/python/scan_signals.py --segments --quiet --output pricing/skew_trading/output/signal_scan.csv" >> /tmp/skew_scan.log 2>&1
0 9 * * 1-5 cd /path/to/atemoya && docker compose exec -w /app -T atemoya /bin/bash -c "uv run pricing/skew_trading/python/notify_signals.py" >> /tmp/skew_notify.log 2>&1
```

Notifications require `NTFY_TOPIC` set in `.env` at the project root.

Collection is idempotent -- running multiple times on the same day for the same ticker skips duplicate collection.

#### Switching from Synthetic to Real Data

Once `{TICKER}_skew_history.csv` accumulates >= 60 rows, `compute_skew_timeseries.py` automatically uses real data. The backtest and signal generation then operate on actual market observations with no OCaml code changes needed.

## Configuration

Edit `data/config.json`:

```json
{
  "rr25_mean_reversion_threshold": 2.0,     # Z-score threshold for signals
  "min_confidence": 0.5,                    # Minimum confidence to trade
  "target_vega_notional": 10000.0,          # Target vega exposure ($)
  "max_gamma_risk": 500.0,                  # Maximum gamma exposure
  "transaction_cost_bps": 5.0,              # Transaction costs (5 bps)
  "delta_hedge": true,                      # Auto delta-hedge positions
  "lookback_days": 60                       # Historical window for statistics
}
```

## Output Interpretation

### Skew Metrics

| Metric | Typical Range (SPY) | Interpretation |
|--------|---------------------|----------------|
| RR25 | -3% to -5% | Negative = put skew (fear premium) |
| BF25 | +1% to +3% | Positive = fat tails (crash risk) |
| ATM Vol | 15% to 25% | Overall volatility level |
| Skew Slope | -0.4 to -0.6 | Steeper = stronger put bias |

### Trading Signals

- **LONG_SKEW**: Buy 25Δ call, sell 25Δ put
  - Profit if RR25 increases (skew normalizes)
  - Typically when market is complacent

- **SHORT_SKEW**: Sell 25Δ call, buy 25Δ put
  - Profit if RR25 decreases (skew mean-reverts down)
  - Typically after panic spikes

- **NEUTRAL**: No strong signal
  - Skew is near historical average
  - Wait for clearer opportunity

### Greeks Summary

- **Delta**: Near-zero for risk reversals (directionally neutral)
- **Vega**: Positive for long skew, negative for short skew
- **Gamma**: Typically small for OTM strategies
- **Theta**: Time decay - negative for long positions

## Expected Performance

Based on academic literature and practitioner reports:

- **Sharpe Ratio**: 1.0 - 1.5 (mean reversion strategy)
- **Annualized Return**: 10% - 20%
- **Max Drawdown**: 15% - 25%
- **Win Rate**: 55% - 65%
- **Holding Period**: 5 - 20 days per trade

Note: Performance varies significantly by market regime and implementation details.

## Data Requirements

### Minimum Data

- Current option chain (yfinance)
- Spot price, dividend yield
- Historical prices (for vol surface calibration)

### Ideal Data (Production)

- Historical implied volatility surface (e.g., OptionMetrics, CBOE DataShop)
- Intraday option quotes for better calibration
- Corporate actions (dividends, splits)
- Interest rate term structure

## Troubleshooting

### "No valid option expiries found"

- Ticker may not have liquid options
- Try major indices: SPY, QQQ, IWM
- Adjust `--min-expiry` and `--max-expiry` flags

### "SVI calibration error high"

- Market quotes may be stale
- Filter: use only options with volume > 10
- Try shorter expiries (< 90 days) for better liquidity

### "Backtest P&L unrealistic"

- Synthetic skew timeseries is for demo only
- For production: use real historical IV data
- Transaction costs may not be included

### "Signal confidence always low"

- Increase lookback window (`lookback_days` in config)
- Check if skew is actually mean-reverting for your ticker
- Adjust `rr25_mean_reversion_threshold`

## Model Architecture

```
skew_trading/
├── ocaml/                    # Core pricing and strategy engine
│   ├── lib/
│   │   ├── types.ml          # Data structures
│   │   ├── skew_measurement.ml   # RR25, BF25, delta strike finder
│   │   ├── skew_strategies.ml    # Risk reversal, butterfly, etc.
│   │   ├── signal_generation.ml  # Mean reversion signals
│   │   └── io.ml             # CSV/JSON I/O
│   └── bin/
│       └── main.ml           # CLI
│
├── python/
│   ├── fetch/                # Data fetching
│   │   ├── fetch_underlying.py
│   │   ├── fetch_options.py  # SVI calibration
│   │   ├── compute_skew_timeseries.py
│   │   └── collect_snapshot.py  # Daily cron collector
│   └── viz/                  # Visualization
│       ├── plot_smile.py
│       ├── plot_skew_ts.py
│       └── plot_pnl.py
│
├── data/                     # Input data
│   ├── config.json
│   ├── {TICKER}_underlying.json
│   ├── {TICKER}_vol_surface.json
│   ├── {TICKER}_skew_timeseries.csv
│   ├── {TICKER}_skew_history.csv   # Real daily observations
│   └── snapshots/{TICKER}/         # Archived SVI surfaces
│
├── output/                   # Results
│   ├── {TICKER}_skew.csv
│   ├── {TICKER}_signal.csv
│   ├── {TICKER}_position.csv
│   ├── {TICKER}_backtest.csv
│   └── plots/
│
├── cron_collect.sh            # Daily collection cron wrapper
└── log/                      # Execution logs
```

## Mathematical Details

See [PLAN.md](PLAN.md) for full mathematical specification, including:
- SVI volatility surface formula
- Newton-Raphson delta strike finder
- Black-Scholes Greeks
- Mean reversion signal generation
- Backtest methodology


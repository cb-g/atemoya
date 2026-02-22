# Volatility Arbitrage Model

Exploit mispricing between implied volatility (from options) and forecasted realized volatility to generate trading signals.

---

## What It Does

Detects and exploits volatility mispricing by:

1. **Computing Realized Volatility** from historical price data using multiple estimators
2. **Forecasting Future Vol** using GARCH, EWMA, HAR, or historical models
3. **Detecting Arbitrage** opportunities (butterfly, calendar, put-call parity violations)
4. **Comparing IV vs RV** to identify overpriced/underpriced options
5. **Generating Trading Signals** for vol arbitrage strategies

**Key Difference from Options Hedging:**
- **Options Hedging**: Defensive portfolio protection (consumer of vol surface)
- **Volatility Arbitrage**: Offensive alpha generation (exploiter of vol surface)

---

## Quick Start

### Prerequisites

- **OCaml**: OPAM 2.x with Dune
- **Python**: uv package manager
- **Data source**: yfinance for historical prices

### Installation

From the atemoya root:

**Docker:**
```bash
# Build OCaml code
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build pricing/volatility_arbitrage"

# Python dependencies already installed via uv sync
```

**Native:**
```bash
# Build OCaml code
eval $(opam env) && dune build pricing/volatility_arbitrage

# Python dependencies already installed via uv sync
```

### Basic Workflow

**Step 1: Fetch Historical Data**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/volatility_arbitrage/python/fetch/fetch_historical.py --ticker AAPL"
```

**Native:**
```bash
uv run pricing/volatility_arbitrage/python/fetch/fetch_historical.py --ticker AAPL
```

**Step 2: Compute Realized Volatility**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec volatility_arbitrage -- \
  -ticker AAPL \
  -operation realized_vol \
  -estimator yang_zhang \
  -rv-window 21"
```

**Native:**
```bash
eval $(opam env) && dune exec volatility_arbitrage -- \
  -ticker AAPL \
  -operation realized_vol \
  -estimator yang_zhang \
  -rv-window 21
```

**Step 3: Forecast Volatility**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec volatility_arbitrage -- \
  -ticker AAPL \
  -operation forecast_vol \
  -forecast-method garch \
  -forecast-horizon 30"
```

**Native:**
```bash
eval $(opam env) && dune exec volatility_arbitrage -- \
  -ticker AAPL \
  -operation forecast_vol \
  -forecast-method garch \
  -forecast-horizon 30
```

**Step 4: Detect Arbitrage**

**Docker:**
```bash
# Requires vol surface from options_hedging model
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec volatility_arbitrage -- \
  -ticker AAPL \
  -operation detect_arbitrage"
```

**Native:**
```bash
# Requires vol surface from options_hedging model
eval $(opam env) && dune exec volatility_arbitrage -- \
  -ticker AAPL \
  -operation detect_arbitrage
```

**Step 5: Visualize**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/volatility_arbitrage/python/viz/plot_iv_vs_rv.py --ticker AAPL"
```

**Native:**
```bash
uv run pricing/volatility_arbitrage/python/viz/plot_iv_vs_rv.py --ticker AAPL
```

**All-in-One:**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec volatility_arbitrage -- \
  -ticker AAPL \
  -operation all"
```

**Native:**
```bash
eval $(opam env) && dune exec volatility_arbitrage -- \
  -ticker AAPL \
  -operation all
```

---

## Understanding the Model

### Realized Volatility Estimators

| Estimator | Uses | Efficiency | Bias |
|-----------|------|------------|------|
| **Close-to-Close** | Close prices | Baseline | Zero drift |
| **Parkinson** | High-Low range | 5x more efficient | Assumes no drift |
| **Garman-Klass** | Full OHLC | 7.4x more efficient | Best unbiased |
| **Rogers-Satchell** | OHLC | Drift-independent | Robust to trends |
| **Yang-Zhang** | All components | **Best overall** | Combines all |

**Recommendation**: Use **Yang-Zhang** (default) for most accurate estimates.

### Volatility Forecasting Methods

**GARCH(1,1)** - Industry standard
```
σ²_t = ω + α·r²_{t-1} + β·σ²_{t-1}

Multi-step forecast:
σ²_{t+h} = ω·(1-β^h)/(1-β) + (α+β)^h·σ²_t
```
- Pros: Captures vol clustering, mean reversion
- Cons: Requires parameter estimation

**EWMA** - RiskMetrics method
```
σ²_t = λ·σ²_{t-1} + (1-λ)·r²_{t-1}

Typically: λ = 0.94 (daily)
```
- Pros: Simple, no parameters to estimate
- Cons: No mean reversion, sensitive to λ

**HAR** - Heterogeneous Autoregressive
```
RV_t = β₀ + β_d·RV_{d} + β_w·RV_{w} + β_m·RV_{m}
```
- Pros: Uses realized vol directly, captures long memory
- Cons: Requires sufficient RV history

**Historical** - Simple average
```
σ_forecast = mean(RV_{t-window}, ..., RV_{t-1})
```
- Pros: Robust, no assumptions
- Cons: Ignores dynamics

### Arbitrage Detection

**Butterfly Arbitrage**
```
Violation: C(K₁) + C(K₃) < 2·C(K₂)

Trade: Buy butterfly (buy wings, sell body)
Profit: 2·C(K₂) - C(K₁) - C(K₃)
```

**Calendar Arbitrage**
```
Violation: C(K, T₂) < C(K, T₁) where T₂ > T₁

Trade: Buy T₂ call, sell T₁ call
Profit: Guaranteed at T₁ expiry
```

**Put-Call Parity**
```
Parity: C - P = S·e^(-qT) - K·e^(-rT)

Violation: |LHS - RHS| > tolerance

Trade: If LHS > RHS, sell call + buy put + buy stock
```

### Trading Signals

**Vol Mispricing Signal**
```
If IV > Forecast RV + threshold:
  Signal: SELL volatility (short straddle/strangle)
  Rationale: Options overpriced

If IV < Forecast RV - threshold:
  Signal: BUY volatility (long straddle/strangle)
  Rationale: Options underpriced
```

**Confidence Scoring**
- **High confidence (>0.9)**: Large arbitrage violations
- **Medium confidence (0.7-0.9)**: Moderate IV-RV spread
- **Low confidence (<0.7)**: Bid-ask based signals

---

## Output Files

**`{TICKER}_realized_vol.csv`** - Realized volatility estimates
- Columns: timestamp, estimator, volatility, window_days
- Multiple estimators for comparison

**`{TICKER}_vol_forecast.json`** - Volatility forecast
- Forecast method (GARCH/EWMA/HAR/Historical)
- Forecast vol, confidence interval, horizon

**`{TICKER}_arbitrage_signals.csv`** - Detected arbitrage opportunities
- Type (Butterfly/Calendar/PutCallParity/VerticalSpread)
- Expected profit after transaction costs
- Confidence level

**`{TICKER}_garch_params.json`** - GARCH parameters (from Python)
- ω, α, β coefficients
- Persistence, unconditional vol
- Model fit statistics (AIC, BIC)

**Plots:**
- `{TICKER}_rv_analysis.png` - RV time series and distribution
- `{TICKER}_iv_vs_rv.png` - IV vs RV comparison (future)

---

## Advanced Usage

### Custom Configuration

Create `data/params.json`:

```json
{
  "min_arbitrage_profit": 0.10,
  "min_vol_mispricing_pct": 5.0,
  "max_transaction_cost_bps": 5.0,
  "target_sharpe_ratio": 1.0,
  "rebalance_threshold_delta": 0.10,
  "garch_window_days": 252,
  "rv_window_days": 21,
  "mc_paths": 1000,
  "mc_steps_per_day": 78
}
```

### Comparing Estimators

**Docker:**
```bash
# Compute all estimators
for est in close_to_close parkinson garman_klass rogers_satchell yang_zhang; do
  docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec volatility_arbitrage -- \
    -ticker AAPL \
    -operation realized_vol \
    -estimator $est"
done
```

**Native:**
```bash
# Compute all estimators
eval $(opam env)
for est in close_to_close parkinson garman_klass rogers_satchell yang_zhang; do
  dune exec volatility_arbitrage -- \
    -ticker AAPL \
    -operation realized_vol \
    -estimator $est
done
```

### GARCH Calibration

**Docker:**
```bash
# Calibrate GARCH parameters (requires arch library)
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/volatility_arbitrage/python/calibrate_garch.py --ticker AAPL"
```

**Native:**
```bash
# Calibrate GARCH parameters (requires arch library)
uv run pricing/volatility_arbitrage/python/calibrate_garch.py --ticker AAPL
```

### Integration with Options Hedging

**Docker:**
```bash
# 1. Calibrate vol surface (from options_hedging)
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker AAPL --model svi"

# 2. Detect arbitrage
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec volatility_arbitrage -- \
  -ticker AAPL \
  -operation detect_arbitrage \
  -data-dir pricing/options_hedging/data"
```

**Native:**
```bash
# 1. Calibrate vol surface (from options_hedging)
uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker AAPL --model svi

# 2. Detect arbitrage
eval $(opam env) && dune exec volatility_arbitrage -- \
  -ticker AAPL \
  -operation detect_arbitrage \
  -data-dir pricing/options_hedging/data
```

---

## Model Specifications

### Realized Vol Formulas

**Yang-Zhang (Best Overall)**:
```
σ² = σ²_o + k·σ²_c + (1-k)·σ²_rs

where:
  σ²_o = overnight variance (close-to-open)
  σ²_c = open-to-close variance
  σ²_rs = Rogers-Satchell variance
  k = 0.34 / (1.34 + (n+1)/(n-1))
```

**Parkinson (High-Low)**:
```
σ² = (1/(4n·ln(2))) × Σ[log(H_i/L_i)]²
```

**Garman-Klass (OHLC)**:
```
σ² = (1/n) × Σ[0.5·log(H/L)² - (2·ln(2)-1)·log(C/O)²]
```

### GARCH Estimation

Uses maximum likelihood via numerical optimization:

```
L(θ) = -0.5 × Σ[log(2π) + log(σ²_t) + r²_t/σ²_t]

where θ = (ω, α, β)
```

Constraints:
- ω > 0
- α, β ≥ 0
- α + β < 1 (stationarity)

---

## Performance

- **RV computation**: ~0.1s for 252 days of data
- **GARCH calibration**: ~1-2s (Python arch library)
- **Arbitrage detection**: ~0.5s per vol surface
- **Forecast generation**: ~0.01s per method

**Total workflow**: ~10-15 seconds end-to-end

---

## Troubleshooting

### "No OHLC data found"

**Docker:**
```bash
# Fetch historical data first
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/volatility_arbitrage/python/fetch/fetch_historical.py --ticker AAPL"
```

**Native:**
```bash
# Fetch historical data first
uv run pricing/volatility_arbitrage/python/fetch/fetch_historical.py --ticker AAPL
```

### "GARCH calibration failed"
- Requires sufficient data (min 100 observations)
- Check for data quality (no NaNs, outliers)
- Fallback: Use EWMA or Historical forecast

### "No arbitrage detected"
- Vol surface may be well-calibrated (no violations)
- Try lowering `min_arbitrage_profit` threshold
- Check vol surface exists and has multiple expiries

### "arch library not installed"

**Docker:**
```bash
# Install arch for GARCH
docker compose exec -w /app atemoya /bin/bash -c "uv pip install arch"
```

**Native:**
```bash
# Install arch for GARCH
uv pip install arch
```

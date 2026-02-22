# Options Hedging Model

Portfolio protection using options strategies with multi-objective optimization.

---

## Why Use This

You own 100 shares of a stock. You want to protect against a drawdown over the next 90 days but don't want to overpay for insurance. This module:

1. **Fetches live option chains** from the market for your ticker
2. **Calibrates two volatility surfaces** (SVI and SABR) so it can price options accurately across all strikes and expiries
3. **Evaluates four hedging strategies** — protective put, collar, vertical spread, covered call — across a grid of strike/expiry combinations
4. **Generates a Pareto frontier** showing the best possible cost-vs-protection trade-offs, so you can see exactly how much protection you get for each dollar spent
5. **Recommends a balanced strategy** with full Greeks so you understand your residual exposures

For example, on BMNR (862% historical vol), it recommended a collar (buy put at $17.93, sell call at $22.34) that protects 85.5% of portfolio value at negative cost — you receive $113 net premium by selling the call, but you cap your upside at ~$22.

---

## What It Does

Finds optimal hedge strategies to protect your stock portfolio against downside risk while minimizing cost. Generates a **Pareto frontier** showing the cost vs protection trade-off across different strategies.

### Supported Strategies

1. **Protective Put** - Maximum downside protection (buy put options)
2. **Collar** - Bounded risk/reward (buy put + sell call for lower cost)
3. **Vertical Spread** - Limited protection at reduced cost (buy/sell puts at different strikes)
4. **Covered Call** - Income generation with slight protection (sell call against holdings)

### Key Features

- **Dual pricing**: Black-Scholes (analytical) + Monte Carlo (American options via Longstaff-Schwartz)
- **SVI/SABR volatility surface**: Calibrated from market data with no-arbitrage checks
- **Multi-objective optimization**: Generates Pareto-efficient strategies
- **Real option chain data**: IBKR (if available) with yfinance fallback
- **Complete Greeks**: Delta, Gamma, Vega, Theta, Rho for portfolio analysis

---

## Quick Start

### Prerequisites

- **OCaml**: OPAM 2.x with Dune
- **Python**: uv package manager
- **Data source**: yfinance for option chains

### Installation

From the atemoya root:

**Docker:**
```bash
# Build OCaml code
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build pricing/options_hedging"
```

**Native:**
```bash
# Build OCaml code
eval $(opam env) && dune build pricing/options_hedging
```

### Basic Workflow

**Step 1: Fetch Market Data**

**Docker:**
```bash
# Fetch underlying stock data (spot, dividend, volatility)
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/fetch/fetch_underlying.py --ticker AAPL"

# Fetch option chain
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/fetch/fetch_options.py --ticker AAPL"
```

**Native:**
```bash
# Fetch underlying stock data (spot, dividend, volatility)
uv run pricing/options_hedging/python/fetch/fetch_underlying.py --ticker AAPL

# Fetch option chain
uv run pricing/options_hedging/python/fetch/fetch_options.py --ticker AAPL
```

**Step 2: Calibrate Volatility Surfaces**

**Docker:**
```bash
# Calibrate both SVI and SABR models from market data
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker AAPL"
```

**Native:**
```bash
# Calibrate both SVI and SABR models from market data
uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker AAPL
```

**Step 3: Run Hedge Analysis**

**Docker:**
```bash
# Analyze hedging strategies
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec options_hedging -- \
  -ticker AAPL \
  -position 100 \
  -expiry 90 \
  -strategies protective_put,collar,covered_call,vertical_spread"
```

**Native:**
```bash
# Analyze hedging strategies
eval $(opam env) && dune exec options_hedging -- \
  -ticker AAPL \
  -position 100 \
  -expiry 90 \
  -strategies protective_put,collar,covered_call,vertical_spread
```

**Step 4: Visualize Results**

**Docker:**
```bash
# Plot payoff diagrams
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/viz/plot_payoffs.py"

# Plot Pareto frontier
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/viz/plot_frontier.py"

# Plot Greeks
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/viz/plot_greeks.py"

# Plot volatility surface
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/viz/plot_vol_surface.py --ticker AAPL"
```

**Native:**
```bash
# Plot payoff diagrams
uv run pricing/options_hedging/python/viz/plot_payoffs.py

# Plot Pareto frontier
uv run pricing/options_hedging/python/viz/plot_frontier.py

# Plot Greeks
uv run pricing/options_hedging/python/viz/plot_greeks.py

# Plot volatility surface
uv run pricing/options_hedging/python/viz/plot_vol_surface.py --ticker AAPL
```

---

## Understanding the Results

### Output Files

**`pareto_frontier.csv`** - All Pareto-efficient strategies
- Columns: strategy, expiry, contracts, cost, protection_level, delta, gamma, vega, theta, rho
- Each row is a strategy that's not dominated by any other

**`recommended_strategy.csv`** - Best balanced strategy (by default)
- Selected from Pareto frontier using normalized cost/protection score
- Represents good middle ground between cost and protection

**`optimization_result.json`** - Full results with all strategies

### Interpreting the Pareto Frontier

The Pareto frontier shows the **best possible trade-offs** between cost and protection:

- **Lower left**: Cheap hedges with less protection
- **Upper right**: Expensive hedges with maximum protection
- **No point dominates another**: Each point is optimal for some preference

**Pick based on risk tolerance:**
- **Conservative**: High protection (95%+ of portfolio value), willing to pay more
- **Moderate**: Medium protection (90-95%), balanced cost
- **Aggressive**: Lower protection (85-90%), minimize cost

### Greeks Interpretation

**Delta (Δ)** - Price sensitivity
- Call: 0 to +1, Put: -1 to 0
- Portfolio delta shows net directional exposure

**Gamma (Γ)** - Delta sensitivity (convexity)
- Always ≥ 0 for long options
- Higher gamma = larger delta changes for small price moves

**Vega (ν)** - Volatility sensitivity
- Per 1% change in implied vol
- Long options have positive vega (benefit from vol increase)

**Theta (Θ)** - Time decay (per day)
- Negative for long options (lose value over time)
- Cost of holding the hedge

**Rho (ρ)** - Interest rate sensitivity
- Per 1% change in rates
- Usually small impact for short-dated options

### Strategy Comparison

| Strategy | Cost | Protection | Delta | Best For |
|----------|------|------------|-------|----------|
| **Protective Put** | High | High | Negative | Max downside protection, willing to pay premium |
| **Collar** | Low/Zero | Medium | Near-zero | Cost-effective hedge, accept capped upside |
| **Vertical Spread** | Medium | Medium | Negative | Limited budget, defined-risk hedging |
| **Covered Call** | Negative (income) | Low | Positive | Generate income, slight downside buffer |

---

## Advanced Usage

### Custom Strike Grid

**Docker:**
```bash
# Generate custom strike range
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec options_hedging -- \
  -ticker AAPL \
  -position 1000 \
  -expiry 180 \
  -min-protection 95000 \
  -max-cost 5000"
```

**Native:**
```bash
# Generate custom strike range
eval $(opam env) && dune exec options_hedging -- \
  -ticker AAPL \
  -position 1000 \
  -expiry 180 \
  -min-protection 95000 \
  -max-cost 5000
```

### Volatility Models

Both SVI and SABR are always calibrated together. The hedge analysis uses SVI by default (more stable calibration), but both surfaces are visualized for comparison:

**Docker:**
```bash
# Calibrate both models
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker AAPL"

# Run hedge analysis with SABR instead of SVI
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec options_hedging -- -ticker AAPL -vol-model sabr"
```

**Native:**
```bash
# Calibrate both models
uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker AAPL

# Run hedge analysis with SABR instead of SVI
eval $(opam env) && dune exec options_hedging -- -ticker AAPL -vol-model sabr
```

### Multiple Expiries

The model automatically searches across expiries. You can specify preferences:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec options_hedging -- \
  -ticker AAPL \
  -expiry 30,60,90,180"  # Will search all four
```

**Native:**
```bash
eval $(opam env) && dune exec options_hedging -- \
  -ticker AAPL \
  -expiry 30,60,90,180  # Will search all four
```

---

## Model Specifications

### Pricing Methods

**Black-Scholes-Merton (Analytical)**
- European options only
- Closed-form Greeks
- Very fast computation
- Formula:
  ```
  C = S·e^(-qT)·N(d₁) - K·e^(-rT)·N(d₂)
  P = K·e^(-rT)·N(-d₂) - S·e^(-qT)·N(-d₁)
  ```

**Longstaff-Schwartz (Monte Carlo)**
- American options (early exercise)
- Path-dependent payoffs
- Uses Laguerre polynomial regression for optimal exercise boundary
- 1,000-10,000 paths, 50 time steps

### Volatility Surface Models

**SVI (Stochastic Volatility Inspired)**
- Parametric formula: `w(k) = a + b(ρ(k-m) + √((k-m)² + σ²))`
- 5 parameters per expiry
- No-arbitrage checks: butterfly & calendar conditions
- Fast, smooth Greeks

**SABR (Stochastic Alpha Beta Rho)**
- CEV model with stochastic volatility
- 4 parameters per expiry (α, β, ρ, ν)
- Hagan approximation for fast pricing
- Better for exotic options

### Optimization

**Pareto Frontier Generation**
- Enumerate all candidate strategies (strike × expiry combinations)
- Filter for Pareto efficiency (no domination)
- Sort by cost, return 20-50 efficient points

**Risk Measures**
- `MinValue`: Minimum portfolio value (95th percentile from MC)
- `CVaR`: Conditional Value at Risk
- `VaR`: Value at Risk

---

## Example Session

**Docker:**
```bash
$ # 1. Fetch AAPL data
$ docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/fetch/fetch_underlying.py --ticker AAPL"
Spot Price: $185.50
Dividend Yield: 0.52%
Historical Vol: 28.5%

$ # 2. Fetch option chain
$ docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/fetch/fetch_options.py --ticker AAPL"
Total Quotes: 847
Expiries: 8 (0.08 to 1.98 years)

$ # 3. Calibrate SVI + SABR
$ docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker AAPL"
Calibrating SVI volatility surface...
  ✓ T=0.246y: a=0.0421, b=0.1035, ρ=-0.312, m=0.015, σ=0.147
  ✓ T=0.493y: a=0.0398, b=0.0987, ρ=-0.298, m=0.008, σ=0.152
  ✓ T=0.986y: a=0.0445, b=0.0912, ρ=-0.285, m=0.003, σ=0.159
Calibrated 8 expiries successfully
Calibrating SABR volatility surface...
  ✓ T=0.246y: α=0.2850, β=0.500, ρ=-0.312, ν=0.450
  ...
Calibrated 8 expiries successfully

$ # 4. Run hedge analysis
$ docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec options_hedging -- -ticker AAPL -position 100 -expiry 90"
=== Options Hedging Analysis: AAPL ===
[1/6] Loading underlying data...
  Spot Price: $185.50
  Dividend Yield: 0.52%

[2/6] Loading volatility surface...
  Surface type: SVI
  Loaded successfully

[3/6] Setting up optimization...
  Position: 100 shares
  Expiry: 90 days (0.25 years)

[4/6] Generating Pareto frontier...
  Generated 23 Pareto-efficient strategies

[5/6] Writing results...
  === Recommended Strategy ===
  Type: Collar(Put=176.00,Call=195.00)
  Cost: $245.00
  Protection: $17,600 (94.9% of portfolio)
  Contracts: 1
  Delta: -0.0842

✓ Analysis complete for AAPL
```

**Native:**
```bash
$ # 1. Fetch AAPL data
$ uv run pricing/options_hedging/python/fetch/fetch_underlying.py --ticker AAPL

$ # 2. Fetch option chain
$ uv run pricing/options_hedging/python/fetch/fetch_options.py --ticker AAPL

$ # 3. Calibrate SVI + SABR
$ uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker AAPL

$ # 4. Run hedge analysis
$ eval $(opam env) && dune exec options_hedging -- -ticker AAPL -position 100 -expiry 90
```

---

## Troubleshooting

See [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) for common issues.

**Quick fixes:**
- **"No options data"**: Ticker may not have listed options, try AAPL, MSFT, SPY
- **"SVI calibration failed"**: Market data may be stale, check bid-ask spreads
- **"No Pareto frontier"**: Relax constraints (`-max-cost`, `-min-protection`)

---

## Mathematical Specification

See [`SPEC.md`](SPEC.md) for complete formulas and algorithms.

---

## Testing

Run unit tests:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest pricing/options_hedging"
```

**Native:**
```bash
eval $(opam env) && dune runtest pricing/options_hedging
```

**Test coverage:**
- Black-Scholes: Put-call parity, Delta bounds, Gamma non-negativity
- Vol Surface: SVI no-arbitrage, SABR validation
- Strategies: Payoff correctness, Collar bounds
- Greeks: Portfolio additivity
- Optimization: Pareto dominance

---

## Architecture

**OCaml (Computation)**
- `types.ml` - Core data structures
- `black_scholes.ml` - Analytical pricing & Greeks
- `greeks.ml` - Portfolio Greeks
- `vol_surface.ml` - SVI/SABR modeling
- `monte_carlo.ml` - Longstaff-Schwartz algorithm
- `strategies.ml` - 4 hedge strategies
- `optimization.ml` - Pareto frontier
- `io.ml` - CSV/JSON I/O

**Python (Data & Viz)**
- `fetch/fetch_underlying.py` - Stock data
- `fetch/fetch_options.py` - Option chains
- `calibrate_vol_surface.py` - SVI/SABR calibration
- `viz/plot_payoffs.py` - Payoff diagrams
- `viz/plot_frontier.py` - Pareto frontier
- `viz/plot_greeks.py` - Greeks surfaces
- `viz/plot_vol_surface.py` - IV surface visualization

---

## Performance

- **Fetch data**: ~5-10 seconds
- **Calibrate vol surface**: ~10-30 seconds (8 expiries)
- **Generate Pareto frontier**: ~30-60 seconds (20 points)
- **Visualizations**: ~5 seconds per plot

**Total workflow**: ~1-2 minutes end-to-end

---

## Future Extensions

- **Exotic options**: Barriers, Asians, lookbacks
- **Delta hedging simulation**: Dynamic rebalancing
- **Multi-asset hedging**: Portfolio-level optimization
- **Greeks hedging**: Delta-gamma-vega neutral portfolios
- **Alternative vol models**: Local vol, Heston stochastic vol
- **Machine learning**: Neural SDE for vol surface

---

## License

Part of the Atemoya quantitative finance platform.

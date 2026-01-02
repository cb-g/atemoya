# Regime-Aware Benchmark-Relative Downside Optimization

Portfolio optimization model that beats the S&P 500 while controlling downside risk through regime-aware LP optimization.

**Status:** ✅ Complete

**Quick Start:** Run `./quickstart.sh` → Pricing → Regime Downside → Run Full Workflow

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Understanding the Gap](#understanding-the-gap)
- [Production Usage](#production-usage)
- [Specification & Compliance](#specification--compliance)
- [Configuration](#configuration)
- [Performance](#performance)

---

## Overview

### What It Does

The regime-aware downside optimization model:
- **Evaluates portfolios daily** but trades only when justified
- **Minimizes persistent underperformance** (LPM1 - Lower Partial Moment)
- **Controls tail risk** using Conditional Value at Risk (CVaR)
- **Detects volatility regimes** and compresses beta in stress periods
- **Maintains ~30% annual turnover** through transaction cost penalties
- **Provides full audit trail** through detailed logging

### Philosophy

*"Keep up with the S&P 500 during normal times, but take your foot off the gas when volatility spikes."*

Instead of maximizing return or minimizing variance, this model:
- Is **benchmark-relative**: Focused on not falling behind the S&P 500
- Is **regime-aware**: Gets defensive automatically when markets get risky
- Tolerates small, noisy underperformance
- Actively avoids cumulative relative "bleeding"
- Prioritizes stability and interpretability over theoretical optimality

### Key Innovation

**Dual Portfolio Optimization:**
1. **Constrained (Actionable)**: Includes transaction costs, path-dependent
2. **Frictionless (Aspirational)**: No turnover penalty, shows model's pure preference

The **gap** between them tells you how much friction constrains you.

---

## Quick Start

### Prerequisites

```bash
# OCaml (via OPAM)
opam install . --deps-only

# Python (via UV)
uv sync
```

### Basic Usage

```bash
# Interactive menu (recommended)
./quickstart.sh
# → Run (3) → Pricing (1) → Regime Downside (1)

# Or manually
opam exec -- dune exec regime_downside -- \
  -tickers AAPL,GOOGL,MSFT,NVDA \
  -start 1500 \
  -lookback 252
```

**Options:**
- `-tickers`: Comma-separated tickers (required)
- `-start`: Start index for backtest (days to skip at beginning)
- `-lookback`: Rolling window size for optimization (default: 252 days = 1 year)

### Output

The model produces:
1. **CSV**: `output/optimization_results.csv` - Full time series of weights and metrics
2. **Logs**: `log/` - Detailed execution logs
3. **Visualizations** (run plot script):
   ```bash
   uv run pricing/regime_downside/python/viz/plot_results.py
   ```
   - `portfolio_weights.png` - Allocation timeline (constrained vs frictionless)
   - `risk_metrics.png` - LPM1, CVaR, Beta, Turnover evolution
   - `gap_analysis.png` - Convergence tracking

---

## How It Works

### The Optimization Problem

At each rebalancing date, we solve a **Linear Program (LP)**:

```
minimize    λ₁·LPM1 + λ₂·CVaR + κ·Turnover + λ_β·s·|β - β_target|

subject to  Σw_i + w_cash = 1    (fully invested)
            w_i ≥ 0               (no short selling)
            w_cash ≥ 0            (no borrowing)
```

**Where:**
- `LPM1`: Lower Partial Moment (downside deviation from benchmark)
- `CVaR`: Conditional Value at Risk (tail risk)
- `Turnover`: Transaction costs (L1 norm of weight changes)
- `β`: Portfolio beta relative to S&P 500
- `s`: Stress weight (higher during volatile regimes)

This is a **convex problem** with guaranteed global optimum.

### Risk Measures

#### 1. LPM1 (Primary): Lower Partial Moment of Order 1

Penalizes persistent small underperformance:

```
LPM1 = E[max(τ - a_t, 0)]

where:
  a_t = active return (portfolio - benchmark)
  τ = threshold (typically -0.001)
```

**Why LPM1?**
- Asymmetric: doesn't penalize upside
- Focuses on cumulative underperformance, not occasional dips
- Linear (fits in LP)

#### 2. CVaR (Secondary): Conditional Value at Risk

Guards against catastrophic tail events:

```
CVaR_95 = average loss in worst 5% of scenarios
```

**Implementation:**
```
CVaR = η + 1/((1-α)T) Σ max(-a_t - η, 0)

where:
  η = VaR threshold (optimized)
  α = confidence level (0.05 for 95%)
```

#### 3. Beta Control (Regime-Dependent)

Compresses market exposure during stress:

```
Portfolio Beta: β = Σw_i·β_i

Penalty: λ_β · s · |β - β_target|

where:
  s = stress weight (0 in calm, >0 in stress)
  β_target = 0.65 (reduces to 65% market exposure)
```

**Behavior:**
- **Calm markets (s=0)**: Beta floats freely, no constraint
- **Stress markets (s>0)**: Penalty enforces β ≈ 0.65
- **Continuous transition**: Smooth ramp, no cliff effects

### Regime Detection

**Volatility-based classification:**

1. Calculate 20-day realized volatility of S&P 500 (annualized)
2. Compare to percentiles of 3-5 year distribution
3. Stress regime: volatility > 70-75th percentile

**Stress weight formula:**
```
s = max(0, (σ_t - σ_calm) / (σ_stress - σ_calm))

where:
  σ_calm = 15%  (calm threshold)
  σ_stress = 30% (stress threshold)
```

**Example:**
- Vol = 12% → s = 0 (fully calm, beta unconstrained)
- Vol = 22% → s = 0.47 (moderate stress, soft beta penalty)
- Vol = 35% → s = 1.33 (high stress, strong beta penalty)

### Transaction Costs & Turnover

```
Cost = κ·Σ|w_i - w_i_prev|

where κ = c + γ
  c = transaction cost (e.g., 5 bps = 0.0005)
  γ = turnover penalty (e.g., 0.1 for stability)
```

**Purpose:**
- `c` = actual trading costs (spreads, commissions)
- `γ` = behavioral stabilizer (prevents overfitting to noise)

### Rebalancing Logic

**Trade only when justified:**

```
if J(current) - J(proposed) ≥ δ:
    rebalance
else:
    stay put
```

**Where:**
- `J` = objective value
- `δ` = improvement threshold (e.g., 0.0001)

**Consequences:**
- Most days: no trade
- Trades cluster around regime shifts or material changes
- Turnover remains controlled (~30% annually)

### Weekly Scenarios

Instead of daily returns, we use **weekly scenarios**:
- Compound 5-day periods
- Reduces noise, improves solver stability
- ~50 scenarios per optimization (for 252-day lookback)

---

## Understanding the Gap

### The Core Issue

Transaction-cost-aware optimization creates **path dependency**:
- Your recommended portfolio depends on where you start
- Two users with identical objectives but different current holdings get different recommendations

**Why?** The turnover penalty:
```
minimize  LPM1 + CVaR + κ·||w - w_current|| + Beta_Penalty
                        ↑
                  Makes it path-dependent
```

### The Solution: Dual Optimization

We solve **twice**:

#### 1. Frictionless Optimal (κ = 0)
```
minimize  LPM1 + CVaR + Beta_Penalty
```

**Shows:** Where the model thinks you should be, ignoring costs

**Properties:**
- ✓ Globally optimal for pure objective
- ✓ Independent of current holdings
- ✓ Comparable across users
- ✗ Not actionable if far from current (would cost too much)
- ✗ Moves every day with new data (not stable)

#### 2. Constrained Optimal (κ > 0)
```
minimize  LPM1 + CVaR + κ·||w - w_current|| + Beta_Penalty
```

**Shows:** Where you should move to, given costs

**Properties:**
- ✓ Globally optimal for constrained objective
- ✓ Actionable (balances benefit vs cost)
- ✓ Respects real-world frictions
- ✗ Path-dependent (depends on w_current)

### The Gap

```
Gap = Distance between constrained and frictionless optimal
```

**What the gap tells you:**
- How much turnover penalty constrains you
- Cost of your starting position (path history)
- How long convergence will take (at current κ)

**What the gap does NOT tell you:**
- "Distance from truth" (both are model-dependent)
- Whether frictionless is better (model may be wrong)

### Practical Use

**If gap is small (<20%):**
- Normal operation
- Follow constrained optimal

**If gap is large (>50%):**
- Consider increasing turnover budget
- Or accept slower convergence
- Or cold-start (ignore previous holdings once)

**If gap keeps growing:**
- Model and market may be diverging
- Review parameters
- Consider regime shift

### Key Insights

1. **Convexity guarantees**: LP solver finds global optimum for both (no local minima)
2. **Model dependence**: Both assume LPM1/CVaR are "right" - they may not be
3. **Moving target**: Tomorrow's frictionless optimal will differ from today's
4. **Gap is about friction, not truth**: Measures cost of path history, not distance to optimal

**The gap is about transparency, not truth.**

---

## Production Usage

### From Backtest to Production

The backtest serves three purposes:

#### 1. Parameter Tuning & Strategy Validation

Prove the strategy works before trusting it with real money:
- Test parameter combinations (λ₁, λ₂, κ, etc.)
- Verify out-of-sample performance
- Evaluate Sharpe ratio, max drawdown, win rate vs benchmark

**If the strategy failed historically, why trust it going forward?**

#### 2. Understanding Optimizer Behavior

Learn the strategy's personality:
- How does it behave during crashes (2020), bear markets (2022), bull runs?
- Average turnover, rebalancing frequency
- Cash allocation tendencies
- Beta management aggressiveness

**Gain intuition to prevent surprises.**

#### 3. Risk Expectations

Set realistic forward expectations:
- **Drawdowns**: Expect similar or worse
- **Volatility**: Historical active return vol informs risk budgets
- **Tracking error**: How much deviation from benchmark?
- **Downside risk**: LPM1, CVaR baseline

**Replace hypothetical "what if" with empirical "what happened."**

### The Critical Component: Last Optimization

**The final day of your backtest produces an allocation based on the most recent data.**

**That allocation IS your recommended portfolio for the next period.**

**Example:**
```
Historical Data: Jan 2020 ──────────────────► Dec 15, 2025
                                              ↑
                                      Last optimization
                                      uses 252 days ending here

Portfolio for Dec 16, 2025 → Based on this optimization
```

**This is not prediction—it's optimization under current conditions.**

### Production Workflow

#### Step 1: Validate (One-Time or Periodic)

```bash
# Run full backtest
./quickstart.sh → Pricing → Regime Downside → Run Optimization

# Parameters:
- Tickers: Your universe
- Start: 500 (save recent data for testing)
- Lookback: 252

# Review: Performance, risk metrics, turnover
```

**Outcome:** Confidence + validated parameters

#### Step 2: Generate Today's Allocation

```bash
# Optimize through most recent data
./quickstart.sh → Pricing → Regime Downside → Run Optimization

# Parameters:
- Start: 252 (just enough for one lookback)
- Lookback: 252

# This gives ONE optimization using most recent year
```

**Outcome:** Today's recommended allocation

#### Step 3: Ongoing Process (Daily/Weekly)

**Each period:**

1. **Fetch latest data:**
   ```bash
   ./quickstart.sh → Pricing → Regime Downside → Fetch Asset Data
   ```

2. **Run optimization:**
   ```bash
   ./quickstart.sh → Pricing → Regime Downside → Run Optimization
   ```

3. **Rebalance decision:**
   - Optimizer compares current vs proposed
   - If improvement > threshold, rebalance
   - Else stay put

4. **Execute trades** and update current portfolio

5. **Log and monitor** actual vs expected

### What the Backtest Doesn't Do

**Important limitations:**
- Does NOT predict future returns (optimization ≠ forecasting)
- Does NOT guarantee future performance
- Does NOT account for model risk (model itself might be wrong)
- Does NOT handle regime shifts (new market structure may invalidate patterns)

**What it DOES do:**
- Provides evidence the framework has skill
- Calibrates expectations
- Delivers disciplined, repeatable process
- Gives defensible allocation decision

---

## Specification & Compliance

### Full LP Formulation

**Decision variables:**
- Primary: `w` (asset weights), `w_c` (cash weight)
- Slacks: `s_lpm[t]`, `η`, `u[t]`, `z[i]`, `v`

**Objective:**
```
minimize  λ₁·(1/T)·Σs_lpm[t]                     [LPM1]
        + λ₂·(η + 1/((1-α)T)·Σu[t])              [CVaR]
        + κ·Σz[i]                                 [Turnover]
        + λ_β·s·v                                 [Beta Penalty]
```

**Constraints:**
```
(1) Σw[i] + w_c = 1                              [Full investment]
(2) s_lpm[t] ≥ τ - a[t],  s_lpm[t] ≥ 0          [LPM1 slack]
(3) u[t] ≥ -a[t] - η,     u[t] ≥ 0              [CVaR slack]
(4) z[i] ≥ w[i] - w_prev[i],  z[i] ≥ 0          [Turnover slack]
(5) z[i] ≥ -(w[i] - w_prev[i])
(6) v ≥ β - β_target,  v ≥ -(β - β_target),  v ≥ 0  [Beta slack]
(7) w[i] ≥ 0,  w_c ≥ 0                           [No shorting]

where:
  a[t] = Σw[i]·r[i,t] + w_c·r_cash - b[t]        [Active return]
  β = Σw[i]·β[i]                                 [Portfolio beta]
```

### Compliance Status

✅ **Fully Compliant** with authoritative LP specification

**Checklist:**
- [x] Weekly scenarios (not daily) - 5-day compounding
- [x] All slack variables per specification
- [x] Long-only constraints
- [x] Full investment constraint
- [x] LPM1, CVaR, turnover, beta penalties
- [x] Proper LP solver (CVXPY with CLARABEL/SCS/OSQP)
- [x] Trade trigger enforced
- [x] Regime ramping (not binary)
- [x] Logging mandatory
- [x] NO random search

**Solver:**
- CVXPY with CLARABEL (preferred), SCS, OSQP (fallbacks)
- Deterministic polynomial-time solution
- Typical solve: <1 second per evaluation

### Implementation Architecture

**OCaml Modules:**
```
ocaml/lib/
├── scenarios.ml         - Weekly scenario generation
├── lp_formulation.ml    - LP problem builder
├── optimization.ml      - Solver interface
├── risk.ml              - LPM1, CVaR calculations
├── regime.ml            - Volatility-based regime detection
├── beta.ml              - Exponentially weighted beta estimation
└── io.ml                - Data I/O, logging
```

**Python Solver:**
```
python/solve_lp.py       - CVXPY LP solver
```

**Data Flow:**
1. OCaml: Daily returns → Weekly scenarios
2. OCaml: Build LP with all slacks
3. OCaml → Python: Export to `/tmp/lp_problem.json`
4. Python: Solve LP with CVXPY
5. Python → OCaml: Import from `/tmp/lp_solution.json`
6. OCaml: Trade trigger decision + logging

---

## Configuration

### Parameters (`data/params.json`)

```json
{
  "lambda_lpm1": 1.0,           // LPM1 weight
  "lambda_cvar": 0.5,           // CVaR weight
  "transaction_cost_bps": 5.0,  // Trading costs (bps)
  "turnover_penalty": 0.1,      // Stability penalty (γ)
  "beta_penalty": 1.0,          // Beta targeting weight (λ_β)
  "target_beta": 0.65,          // Stress regime target
  "lpm1_threshold": -0.001,     // Weekly threshold (τ)
  "rebalance_threshold": 0.0001 // Improvement threshold (δ)
}
```

### Parameter Effects

| Parameter | Range | Effect | Typical |
|-----------|-------|--------|---------|
| `lambda_lpm1` | 0.5-2.0 | Higher → more conservative | 1.0 |
| `lambda_cvar` | 0.1-1.0 | Higher → avoid tail risk | 0.5 |
| `beta_penalty` | 0.5-2.0 | Higher → stricter beta targeting | 1.0 |
| `turnover_penalty` | 0.01-0.2 | Higher → less trading | 0.1 |
| `lpm1_threshold` | -0.005 to 0 | Lower → only penalize bigger losses | -0.001 |
| `target_beta` | 0.5-0.8 | Lower → more defensive in stress | 0.65 |

### Tuning Process

Use walk-forward testing:

```bash
# Grid search over parameters
for lambda_lpm1 in 0.5 1.0 1.5; do
    for lambda_cvar in 0.3 0.5 0.7; do
        for kappa in 0.05 0.1 0.15; do
            # Run backtest with these parameters
            # Evaluate: Sharpe, max drawdown, downside dev, win rate
        done
    done
done
```

**Once selected, parameters are frozen.** Re-tune only after structural changes (universe, costs, benchmark).

---

## Performance

### Execution Time

| Workload | Assets | Lookback | Backtest | Time | Notes |
|----------|--------|----------|----------|------|-------|
| Small | 5 | 1 year | 250 days | 2-5s | Quick test |
| Medium | 10 | 2 years | 500 days | 5-10s | Typical usage |
| Large | 20 | 3 years | 750 days | 15-30s | Full universe |

**Breakdown per step:**
- Scenario generation: <1s
- LP solver: 0.5-1s
- Risk/beta calculations: <0.5s
- I/O and logging: <0.5s

### Memory Usage

| Assets | History | Memory | Peak |
|--------|---------|--------|------|
| 5 | 1 year | 50MB | 80MB |
| 10 | 2 years | 100MB | 150MB |
| 20 | 3 years | 200MB | 300MB |

**Notes:**
- Python (CVXPY) dominates memory
- OCaml runtime lightweight (<50MB)

### Data Requirements

**Minimum:**
- 60 trading days (volatility calculation)
- 2+ assets (need variance for portfolio)

**Recommended:**
- 250+ trading days (1 year) for robust statistics
- 5-20 assets for meaningful diversification
- S&P 500 benchmark data (same timeframe)

**Optimal:**
- 750 days (3 years) captures full market cycle
- 10-30 assets balances diversification vs complexity

### Typical Behavior

**Calm Market (vol < 15%):**
- Equity allocation: 80-95%
- Cash: 5-20%
- Portfolio beta: 0.95-1.05
- Turnover: 10-25%

**Stress Market (vol > 20%):**
- Equity allocation: 50-70% (beta compression)
- Cash: 30-50%
- Portfolio beta: 0.70-0.90
- Turnover: 25-40% (defensive repositioning)

**Risk Metrics:**
- LPM1: 0.001-0.005 (0.1-0.5% expected shortfall)
- CVaR (95%): 0.01-0.03 (1-3% tail risk)

### Bottlenecks

**Slowest component:** LP solver (50-80% of runtime)

**Optimization strategies:**
1. Reduce assets (pre-screen to top 20 by liquidity)
2. Shorten lookback (fewer weeks = smaller LP)
3. Cache covariance matrix (update incrementally)

**Scaling limits:**

| Dimension | Soft Limit | Hard Limit | Notes |
|-----------|------------|------------|-------|
| Assets | 50 | 200 | O(n³) solver complexity |
| History | 1500 days | 5000 days | Memory linear |

**Production recommendations:**
- 10-30 assets (sweet spot)
- 500-1000 trading days (2-4 years)
- Rebalance monthly or when conditions change

---

## See Also

- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions
- **[Root README](../../README.md)** - Project overview

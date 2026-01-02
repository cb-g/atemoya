# DCF Probabilistic Valuation

**Monte Carlo Simulation | Uncertainty Quantification**

Advanced DCF valuation with Monte Carlo simulation for probability distributions, uncertainty quantification, and portfolio frontier analysis.

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Understanding Results](#understanding-results)
- [Portfolio Frontier Analysis](#portfolio-frontier-analysis)
- [How It Works](#how-it-works)
- [Configuration](#configuration)
- [Performance](#performance)

---

## Overview

### What It Does

Extends deterministic DCF with Monte Carlo simulation to:
- Generate probability distributions of intrinsic values (not just point estimates)
- Quantify valuation uncertainty through statistical analysis
- Calculate probability metrics (P(undervalued), confidence intervals)
- Build multi-asset portfolio efficient frontiers

### Key Features

✅ **Monte Carlo Simulation** (100-10,000 iterations)
- Samples financial metrics from historical distributions
- Produces full distribution of intrinsic values
- Quantifies estimation uncertainty

✅ **Stochastic Discount Rates**
- Samples RFR, beta, and ERP each iteration
- Recomputes cost of equity and WACC per simulation
- Captures discount rate uncertainty
- Significantly increases realism

✅ **Time-Varying Growth Rates**
- Exponential mean reversion model: `g_t = g_LT + (g_0 - g_LT) × exp(-λt)`
- Initial growth decays toward terminal rate
- More conservative than constant growth
- Prevents unrealistic perpetual high growth

✅ **Bayesian Priors**
- Beta distribution priors for ROE, ROIC, retention ratio
- Smooths extreme empirical values toward industry norms
- Reduces overfitting to short time series
- Configurable prior weight (0-1)

✅ **Distribution Statistics**
- Mean, median, std dev, min, max
- Percentiles (P5, P10, P25, P50, P75, P90, P95)
- Probability of undervaluation: P(IVPS > Price)
- Skewness, kurtosis metrics

✅ **Portfolio Efficient Frontier**
- Multi-asset optimization (2+ tickers)
- Risk-return frontier (mean return vs std dev)
- Tail risk frontier (mean return vs P(loss))
- Identifies optimal portfolios (min variance, max Sharpe, min P(loss))
- Visualizes 1K-10K random portfolios

✅ **Comprehensive Visualization**
- KDE plots (kernel density estimate of distributions)
- Surplus distributions (IVPS - Price)
- Efficient frontier plots (2 types)
- Market price comparisons

### Status

**✅ Complete**
- 23 unit tests, all passing
- Complete documentation
- Integrated with quickstart menu
- Full visualization suite
- Advanced features fully implemented

---

## Quick Start

### Prerequisites

```bash
# OCaml dependencies
opam install . --deps-only --with-test --yes

# Python dependencies (including scipy for KDE)
uv sync

# Verify build
opam exec -- dune build
```

### Interactive Menu (Recommended)

```bash
./quickstart.sh
# → Run (3) → Valuation (2) → DCF Probabilistic (2) → Do Everything (5)
```

This will:
1. Fetch 4-year time series data (yfinance)
2. Run Monte Carlo simulation
3. Generate visualizations (KDE, surplus, frontier)
4. Display results

### Manual Execution

```bash
# Single ticker (default: 1000 simulations)
opam exec -- dune exec dcf_probabilistic -- -ticker AAPL

# Custom simulation count
opam exec -- dune exec dcf_probabilistic -- -ticker GOOGL -num-sims 5000

# Multiple tickers (for portfolio frontier)
opam exec -- dune exec dcf_probabilistic -- -ticker AAPL
opam exec -- dune exec dcf_probabilistic -- -ticker MSFT
opam exec -- dune exec dcf_probabilistic -- -ticker GOOGL

# Generate visualizations
uv run valuation/dcf_probabilistic/python/viz/plot_results.py --ticker AAPL --method fcfe

# Generate portfolio frontier (requires 2+ tickers already run)
uv run valuation/dcf_probabilistic/python/viz/plot_frontier.py --method fcfe --num-portfolios 5000
```

### Output

**Log files:** `valuation/dcf_probabilistic/log/dcf_prob_TICKER_YYYYMMDD_HHMMSS.log`

**CSV files:** `valuation/dcf_probabilistic/output/`
- `probabilistic_summary.csv` - Statistics for all tickers
- `simulations_fcfe.csv` - Full simulation matrix (FCFE)
- `simulations_fcff.csv` - Full simulation matrix (FCFF)
- `market_prices.csv` - Market prices for all tickers

**Visualizations:** `valuation/dcf_probabilistic/output/`
- `kde_TICKER_fcfe.png` - Intrinsic value distribution (FCFE)
- `kde_TICKER_fcff.png` - Intrinsic value distribution (FCFF)
- `surplus_TICKER_fcfe.png` - Surplus distribution (IVPS - Price, FCFE)
- `surplus_TICKER_fcff.png` - Surplus distribution (FCFF)
- `efficient_frontier_risk_return_fcfe.png` - Risk-return frontier
- `efficient_frontier_tail_risk_fcfe.png` - Tail risk frontier

**Example output:**
```
========================================
Probabilistic DCF Valuation: GOOGL
========================================

[FCFE Statistics]
  Mean IVPS: $178.25
  Std Dev: $24.50
  Min: $122.30
  P10: $148.60
  P25: $162.80
  P50 (Median): $176.90
  P75: $192.40
  P90: $209.50
  Max: $255.80

[FCFF Statistics]
  Mean IVPS: $182.10
  Std Dev: $26.30
  P50 (Median): $180.50
  P90: $215.80

[Probability Metrics]
  P(FCFE > Price): 71.2%
  P(FCFF > Price): 75.8%

[Current Market]
  Price: $165.40

[Investment Signal]
  Signal: StrongBuy
  Confidence: High (71-76% probability undervalued)
========================================
```

---

## Understanding Results

### Key Metrics Explained

**Mean IVPS**: Average intrinsic value across all simulations
- Influenced by extreme values (outliers)
- May be pulled up/down by tail scenarios
- **Use**: Expected value if all scenarios equally likely

**Std Dev (Standard Deviation)**: Measure of uncertainty/volatility
- Higher std dev = wider distribution = more uncertainty
- **Use**: Risk metric, shows valuation uncertainty

**Percentiles (P10, P25, P50, P75, P90)**:
- **P10**: 10% of simulations below this value (pessimistic)
- **P25**: 25% below (conservative)
- **P50 (Median)**: 50% below, 50% above (middle scenario)
- **P75**: 75% below (optimistic)
- **P90**: 90% below (very optimistic)
- **Use**: Scenario planning, risk assessment

**P(FCFE > Price)**: Probability intrinsic value exceeds market price
- >50%: More likely undervalued than overvalued
- <50%: More likely overvalued
- **Use**: Conviction metric for buy/sell decision

### Distribution Shapes

#### **Normal (Symmetric)**
```
Characteristics:
- Mean ≈ Median
- Balanced upside/downside
- Most common outcome near mean

Interpretation: Predictable, low skew
Example: Mature utility with stable cash flows
```

#### **Right-Skewed (Positive Skew)**
```
Characteristics:
- Mean > Median (pulled right by tail)
- Long right tail (upside potential)
- More common lower values, rare extreme highs

Interpretation: Asymmetric upside (lottery-like payoff)
Example: Biotech (failures common, blockbuster rare)
```

#### **Left-Skewed (Negative Skew)**
```
Characteristics:
- Mean < Median (pulled left by tail)
- Long left tail (downside risk)
- More common higher values, rare crashes

Interpretation: Downside risk, but usually OK
Example: High-quality dividend stock (stable, but recession risk)
```

**How to identify:**
- Mean > Median + 10%: Right-skewed (upside potential)
- Mean ≈ Median (±5%): Symmetric (balanced)
- Mean < Median - 10%: Left-skewed (downside risk)

### Probability Interpretation

| P(Undervalued) | Interpretation | Action | Confidence |
|----------------|----------------|--------|------------|
| **90-100%** | Very high conviction undervalued | Strong buy | Very High |
| **70-90%** | High conviction undervalued | Buy | High |
| **60-70%** | Moderate undervaluation | Buy on dips | Moderate |
| **50-60%** | Slight undervaluation | Hold or small buy | Low |
| **40-50%** | Fairly valued (coin flip) | Hold | Neutral |
| **30-40%** | Slight overvaluation | Hold or trim | Low |
| **10-30%** | Moderate overvaluation | Sell | Moderate |
| **0-10%** | Very high conviction overvalued | Strong sell | Very High |

### Distribution Width - Uncertainty Metric

**Narrow Distribution (P90/P10 < 1.5)**
```
Example: P10 = $90, P90 = $120, Ratio = 1.33

Interpretation:
- Low uncertainty
- Tight range of outcomes
- High predictability

Business Type: Mature, stable (utilities, consumer staples)
Action: Trust valuation, narrow bands
```

**Moderate Distribution (P90/P10 = 1.5-2.0)**
```
Example: P10 = $80, P90 = $140, Ratio = 1.75

Interpretation:
- Moderate uncertainty
- Typical for most companies
- Room for upside/downside

Business Type: Established growth (tech, industrials)
Action: Use P25-P75 band for valuation range
```

**Wide Distribution (P90/P10 > 2.0)**
```
Example: P10 = $50, P90 = $150, Ratio = 3.0

Interpretation:
- High uncertainty
- Wide range of outcomes
- Difficult to predict

Business Type: Early-stage, cyclical, distressed
Action: Require higher margin of safety, use scenario analysis
```

### Mean vs Median vs Percentiles

#### **Use Median (P50) as Primary Estimate**

**Why Median?**
- Robust to outliers
- 50% of scenarios above, 50% below
- Less affected by extreme tail events
- Better represents "typical" outcome

**Example:**
```
Simulations: [$80, $90, $100, $110, $500]
Mean: $176 (pulled up by $500 outlier)
Median: $100 (middle value)

→ Use Median ($100) as base-case valuation
```

#### **Use Mean for Expected Value Calculations**

**When to prefer Mean:**
- Tail scenarios are important (biotech, venture)
- Calculating portfolio expected returns
- Academic/theoretical analysis

#### **Use Percentiles for Scenario Planning**

**Valuation Range Approach:**
```
Conservative Value: P25 = $160
Base Case Value: P50 = $180
Optimistic Value: P75 = $205

Market Price: $170

Analysis:
- Below base case → Undervalued
- Within P25-P75 range → Reasonable valuation
- Above conservative case → Margin of safety

Action: Buy if Price < P50, Hold if P25 < Price < P75
```

### Coefficient of Variation (CV)

**Formula**: CV = (Std Dev / Mean) × 100%

**Interpretation:**
- **Low CV (<15%)**: Low relative uncertainty, stable
- **Moderate CV (15-30%)**: Normal uncertainty
- **High CV (>30%)**: High relative uncertainty, risky

**Example:**
```
Stock A: Mean = $200, Std Dev = $20, CV = 10%
Stock B: Mean = $50, Std Dev = $20, CV = 40%

Even though both have same $20 std dev:
- Stock A: More predictable (10% CV)
- Stock B: More uncertain (40% CV)
```

### Comparing to Deterministic DCF

**When They Agree (±10%)**
```
Deterministic IVPS: $180
Probabilistic P50: $178

Interpretation:
- Both models agree
- Uncertainty is symmetric around deterministic estimate
- High confidence in valuation

Action: Trust valuation, use deterministic for simplicity
```

**When Probabilistic is Higher (P50 > Deterministic)**
```
Deterministic IVPS: $150
Probabilistic P50: $175

Root Causes:
- Bayesian priors boosting low empirical values
- Lognormal sampling creating positive skew
- Time-varying growth starting high then reverting

Interpretation:
- Probabilistic captures upside scenarios
- Deterministic may be too conservative

Action: Use probabilistic estimate, deterministic as floor
```

**Large Disagreement (>20%)**
```
Interpretation: RED FLAG
- Models using different assumptions
- Check configuration (priors, stochastic flags)
- Verify input data consistency

Action:
- Debug both models
- Compare to peer valuations
- Use range with caution
```

### Decision Framework

**Conservative (P25):**
```
If Price < P25:
  → High confidence undervalued → Strong Buy

If P25 ≤ Price ≤ P50:
  → Moderate undervaluation → Buy

If P50 < Price < P75:
  → Fairly valued to slightly overvalued → Hold

If Price > P75:
  → High confidence overvalued → Sell
```

**Aggressive (P50):**
```
If Price < P50:
  → More likely undervalued (>50%) → Buy

If Price ≈ P50 (±5%):
  → Fairly valued → Hold

If Price > P50:
  → More likely overvalued (>50%) → Sell
```

**Probabilistic:**
```
If P(IVPS > Price) > 70%:
  → High probability undervalued → Strong Buy

If 55% < P(IVPS > Price) < 70%:
  → Moderate probability undervalued → Buy

If 45% ≤ P(IVPS > Price) ≤ 55%:
  → Coin flip (no edge) → Hold

If P(IVPS > Price) < 30%:
  → High probability overvalued → Strong Sell
```

---

## Portfolio Frontier Analysis

### Two Frontiers

The probabilistic DCF model generates two distinct portfolio frontiers:

#### **Risk-Return Frontier** (Traditional Markowitz)

**Axes:**
- X-axis: Portfolio standard deviation (σ_p)
- Y-axis: Expected return (E[R_p])

**Shape:** Hyperbolic curve (convex)

**Mathematical Form:**
```
E[R_p] = Σ w_i × E[R_i]
σ_p = √(w' Σ w)

Diversification reduces variance through correlation:
σ_p² = Σ w_i² σ_i² + 2 Σ Σ w_i w_j ρ_ij σ_i σ_j
```

**Key Portfolios:**

1. **Min Variance Portfolio**
   - Lowest risk portfolio
   - Conservative allocation
   - Emphasizes stable stocks
   - Use Case: Risk-averse investors, retirees

2. **Max Sharpe Ratio Portfolio**
   - Best risk-adjusted returns
   - Balanced allocation
   - Optimal trade-off
   - Use Case: Most investors (maximize Sharpe)

3. **Max Return Portfolio**
   - Highest expected return
   - Concentrated in high-growth
   - High risk tolerance required
   - Use Case: Growth investors, long time horizon

#### **Tail Risk Frontier** (Valuation-Based)

**Axes:**
- X-axis: Probability of Loss = P(Portfolio_IV < Portfolio_Price)
- Y-axis: Expected return (E[R_p])

**Shape:** Nearly linear, downward-sloping

**Mathematical Form:**
```
E[R_p] = Σ w_i × (mean_IV_i - price_i) / price_i
P(Loss) = P(Σ w_i × IV_i < Σ w_i × Price_i)
```

**Key Property:** Strong correlation between expected return and tail safety.

**Why Linear?**

For valuation-based investing, **safety and return align**:
```
Asset is undervalued:
  → mean_IV > price
  → High expected return
  → Most simulations have IV > price
  → Low P(Loss)

Asset is overvalued:
  → mean_IV < price
  → Negative expected return
  → Most simulations have IV < price
  → High P(Loss)
```

**There's no tradeoff between maximizing return and minimizing tail risk!**

**Key Portfolios:**

1. **Min P(Loss) Portfolio**
   - Minimizes downside probability
   - Heavy in stable, undervalued stocks
   - Low growth allocation
   - Use Case: Capital preservation, low risk tolerance

**Important:** In tail risk space, **Min P(Loss) ≈ Max Return** (same portfolio)!

Unlike traditional mean-variance where these are different portfolios at opposite ends, for valuation-based investing they coincide because fundamental undervaluation provides both safety and return.

### Comparison Table

| Aspect | Mean-Variance Frontier | Tail Risk Frontier |
|--------|----------------------|-------------------|
| **X-axis** | Standard deviation (σ) | Probability of loss P(IV < Price) |
| **Shape** | Hyperbolic/curved | Nearly linear |
| **Mechanism** | Covariance diversification | Valuation fundamentals |
| **Min Risk Portfolio** | Diversified, moderate return | Concentrated in undervalued |
| **Max Return Portfolio** | Concentrated, high variance | Same as min risk! |
| **Tradeoff** | Return vs. volatility | No tradeoff (aligned) |
| **Diversification Benefit** | Significant (ρ < 1) | Limited for P(Loss) |
| **Optimal Portfolio** | Interior solution | Extreme point (top-left) |

### Practical Implications

**1. No Greed-Fear Conflict**

Traditional investing wisdom says "higher return requires higher risk." The tail risk frontier shows this is **false for valuation-based investing**:

```
Buying undervalued assets:
  ✓ Maximizes expected return
  ✓ Minimizes probability of loss
  ✓ No tradeoff needed
```

**2. Portfolio Dominance**

Portfolios in the **top-left** of the tail risk frontier strictly dominate those in the bottom-right:
- Higher expected return
- Lower probability of loss

**3. Value Investing Vindication**

This frontier mathematically validates the value investing principle:

> "Margin of safety provides both upside potential and downside protection."
> — Benjamin Graham

The linear shape proves that **fundamental undervaluation** provides both simultaneously.

**4. When Diversification Helps**

Diversification still helps for:
1. **Estimation risk**: If you're uncertain about which stocks are truly undervalued
2. **Idiosyncratic shocks**: Company-specific events (fraud, product failure)
3. **Model risk**: DCF assumptions might be wrong

But it doesn't help in the theoretical case where your valuations are accurate.

### Which Frontier to Use?

**Use Risk-Return Frontier when:**
- You care about volatility (leveraged strategies, short-term horizon)
- You want Sharpe ratio maximization
- You face margin calls or drawdown constraints

**Use Tail Risk Frontier when:**
- You're a long-term value investor
- You care about fundamental mispricing, not volatility
- You can tolerate price fluctuations as long as intrinsic value is safe

**Best Practice:** Use both!
- Tail risk frontier for strategic allocation (which assets?)
- Risk-return frontier for tactical sizing (how much?)

---

## How It Works

### Architecture

**Modular Decomposition:**
```
ocaml/lib/
├── types.ml[i]              - Distribution types, priors, stats
├── sampling.ml[i]           - Monte Carlo sampling (Box-Muller, Beta, lognormal)
├── monte_carlo.ml[i]        - Simulation engine (FCFE/FCFF)
├── statistics.ml[i]         - Statistical analysis, signal generation
└── io.ml[i]                 - JSON I/O, CSV writing, logging

ocaml/bin/
└── main.ml                  - Main entry point

python/fetch/
└── fetch_financials_ts.py   - 4-year time series data fetcher

python/viz/
├── plot_results.py          - KDE and surplus distributions
└── plot_frontier.py         - Portfolio efficient frontiers
```

**Total:** ~1800 lines of OCaml, ~400 lines of Python

### Monte Carlo Process

**1. Data Preparation**
```
Fetch 4-year time series:
- Net Income, Book Equity, FCFE (for FCFE method)
- EBIT, Invested Capital, FCFF (for FCFF method)
- CapEx, Depreciation, Working Capital
```

**2. Sampling**
```
For each simulation (i = 1 to N):

  # Sample financial metrics
  ROE_i ~ LogNormal(μ_ROE, σ_ROE)  # From 4-year history
  Retention_i ~ Beta(α_RR, β_RR)   # Bayesian smoothed
  ROIC_i ~ LogNormal(μ_ROIC, σ_ROIC)
  Reinvestment_i ~ Normal(μ_RI, σ_RI)

  # Sample discount rate components (if stochastic enabled)
  RFR_i ~ Normal(RFR_base, σ_RFR)
  Beta_i ~ Normal(Beta_base, σ_Beta)
  ERP_i ~ Normal(ERP_base, σ_ERP)

  # Calculate growth rates
  g_FCFE_i = ROE_i × Retention_i  (clamped)
  g_FCFF_i = ROIC_i × Reinvestment_i  (clamped)

  # Apply time-varying growth (if enabled)
  For t in 1..T:
    g_FCFE_t = g_term + (g_FCFE_i - g_term) × exp(-λ × t)
    g_FCFF_t = g_term + (g_FCFF_i - g_term) × exp(-λ × t)

  # Calculate discount rates
  CE_i = RFR_i + Beta_i × ERP_i
  WACC_i = ... (using sampled values)

  # Project cash flows and value
  IVPS_FCFE_i = DCF_valuation(FCFE, CE_i, g_FCFE_t)
  IVPS_FCFF_i = DCF_valuation(FCFF, WACC_i, g_FCFF_t)
```

**3. Statistical Analysis**
```
After N simulations:

  mean_FCFE = mean(IVPS_FCFE_1...N)
  std_FCFE = std(IVPS_FCFE_1...N)
  percentiles = [P5, P10, P25, P50, P75, P90, P95]

  P(undervalued) = count(IVPS_FCFE_i > Price) / N

  Signal = classify(mean_FCFE, mean_FCFF, Price)
```

### Bayesian Prior Integration

**Purpose:** Smooth extreme empirical values toward industry norms.

**Formula:**
```
Smoothed = (1 - w) × Empirical + w × Prior

Where:
- w = prior_weight (0-1, default 0.5)
- Empirical = historical average
- Prior = Beta distribution from config
```

**Example:**
```
Empirical ROE: 35% (very high, from 2-year sample)
Prior ROE: Beta(5, 5) → mean ≈ 15%
Prior weight: 0.5

Smoothed ROE ~ mixture:
  50% from empirical distribution (μ=35%, σ=10%)
  50% from prior Beta(5, 5)

Result: More conservative, prevents overfitting
```

### Stochastic Discount Rates

**Configurable in `params_probabilistic.json`:**
```json
{
  "use_stochastic_discount_rates": true,
  "rfr_volatility": 0.005,  // ±50 bps
  "beta_volatility": 0.10,  // ±0.1
  "erp_volatility": 0.01    // ±1%
}
```

**Impact:**
- Adds uncertainty in cost of capital
- Widens distribution of IVPS
- More realistic uncertainty quantification

**Example:** AAPL with stochastic discount rates
- Std dev increased from $253 to $786
- P(undervalued) decreased from 92% to 78% (more conservative)

### Time-Varying Growth Rates

**Model:** Exponential mean reversion
```
g_t = g_term + (g_0 - g_term) × exp(-λ × t)

Where:
- g_0: Initial growth rate (sampled)
- g_term: Terminal growth rate (2.5%)
- λ: Mean reversion speed (default 0.3)
- t: Year (1, 2, 3, ...)
```

**Effect:**
- Growth starts high, decays exponentially toward terminal rate
- More conservative than constant high growth
- Prevents unrealistic perpetual growth

**Example:** GOOGL with time-varying growth
- Year 1: 12% → Year 5: 4.5% → Terminal: 2.5%
- Mean IVPS dropped from $1,816 to $405 (more realistic)

---

## Configuration

### Data Files (in `valuation/dcf_probabilistic/data/`)

**`params_probabilistic.json`** - Simulation parameters
```json
{
  "num_simulations": 1000,
  "projection_years": 5,
  "terminal_growth_rate": 0.025,
  "growth_clamp_lower": -0.20,
  "growth_clamp_upper": 0.50,

  "use_bayesian_priors": true,
  "prior_weight": 0.5,

  "use_stochastic_discount_rates": true,
  "rfr_volatility": 0.005,
  "beta_volatility": 0.10,
  "erp_volatility": 0.01,

  "use_time_varying_growth": true,
  "growth_mean_reversion_speed": 0.3
}
```

**`bayesian_priors.json`** - Beta distribution priors
```json
{
  "roe": {
    "alpha": 5.0,
    "beta": 5.0,
    "lower_bound": 0.05,
    "upper_bound": 0.30
  },
  "retention_ratio": {
    "alpha": 3.0,
    "beta": 2.0,
    "lower_bound": 0.20,
    "upper_bound": 0.80
  },
  "roic": {
    "alpha": 5.0,
    "beta": 5.0,
    "lower_bound": 0.05,
    "upper_bound": 0.25
  }
}
```

**Shared configs** (symlinked to DCF Deterministic):
- `risk_free_rates.json`
- `equity_risk_premiums.json`
- `industry_betas.json`
- `tax_rates.json`

### Parameter Effects

**`num_simulations`** (default: 1000)
- More simulations = smoother distributions, lower sampling error
- Typical: 1000-5000 for single ticker, 100-1000 for quick analysis
- Trade-off: Accuracy vs execution time

**`use_bayesian_priors`** (default: true)
- Enables Bayesian prior smoothing
- Reduces overfitting to short time series
- More conservative estimates

**`prior_weight`** (default: 0.5)
- Weight given to prior vs empirical data
- 0.0 = ignore priors (pure empirical)
- 1.0 = ignore data (pure prior)
- 0.5 = equal weight

**`use_stochastic_discount_rates`** (default: true)
- Enables sampling of RFR, beta, ERP
- Adds discount rate uncertainty
- Widens distributions significantly

**`use_time_varying_growth`** (default: true)
- Enables exponential mean reversion
- More conservative than constant growth
- Prevents unrealistic projections

**`growth_mean_reversion_speed`** (default: 0.3)
- λ parameter in exponential decay
- 0.0 = no reversion (constant growth)
- 1.0 = fast reversion (converges quickly)
- 0.3 = moderate reversion (recommended)

---

## Performance

**Build Time:** < 5 seconds

**Single Valuation:**
- 100 simulations: ~2 seconds
- 1000 simulations: ~10-30 seconds
- 5000 simulations: ~60-120 seconds
- 10,000 simulations: ~3-5 minutes

**Multi-Ticker:**
- 3 tickers × 1000 sims: ~60 seconds
- 10 tickers × 1000 sims: ~5 minutes

**Visualization:**
- KDE plots: ~2 seconds per ticker
- Efficient frontier: ~3-5 seconds (5000 portfolios)

**Memory Usage:**
- 1000 sims × 10 tickers: ~100MB
- 10,000 sims × 50 tickers: ~5GB

**Dependencies:**
- OCaml: yojson, ppx_deriving, unix, owl (for distributions)
- Python: yfinance, pandas, numpy, matplotlib, seaborn, scipy (for KDE)

**Performance Tips:**
- Use 1000 simulations for routine analysis
- Use 5000+ for high-precision distributions
- Process tickers sequentially to avoid memory issues
- Generate visualizations in batch after all valuations complete

---

## See Also

- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions
- **[Root README](../../README.md)** - Project overview, model comparison

**Related Models:**
- **[DCF Deterministic](../dcf_deterministic/README.md)** - Traditional DCF for point estimates
- **[Regime Downside](../../pricing/regime_downside/README.md)** - Portfolio optimization

---

## Advanced Features

### Feature Implementation Status

**✅ Core Features (100% Complete)**
- Monte Carlo simulation engine
- Bayesian prior integration
- Statistical analysis with comprehensive metrics
- KDE visualizations
- CSV data accumulation for multi-ticker

**✅ Advanced Features (100% Complete)**
- Stochastic discount rates (RFR, beta, ERP sampling)
- Time-varying growth rates (exponential mean reversion)
- Portfolio efficient frontier (risk-return and tail risk)
- Multi-asset portfolio optimization

**🔜 Optional Future Enhancements**
- Correlation modeling between assets
- Scenario analysis (bull/base/bear)
- GPU acceleration for 10,000+ simulations
- Parallelization using OCaml Domains

### Design Principles

**Statistical Rigor:**
- Box-Muller transform for Gaussian sampling
- Beta distribution for bounded priors (ROE, retention)
- Lognormal distribution for multiplicative metrics
- Kernel Density Estimation for smooth visualizations

**Robustness:**
- Cleans outliers from time series (zeros, infinities)
- Caps extreme sampled values to prevent numerical overflow
- Bayesian priors prevent overfitting to short histories
- Time-varying growth prevents unrealistic projections

**Modularity:**
- Sampling module independent of valuation logic
- Statistics module reusable for any distribution
- Visualization scripts work with any simulation output

---

**Final Rule:** Probabilistic DCF quantifies uncertainty. Use distributions to understand risk, percentiles for scenario planning, and probabilities for conviction levels. Combine with qualitative analysis for robust decisions.

# DCF Deterministic Valuation

**Traditional Discounted Cash Flow | Equity Valuation**

Deterministic DCF valuation using Free Cash Flow to Equity (FCFE) and Free Cash Flow to Firm (FCFF) methods with dual-method cross-validation and 9-category investment signals.

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Understanding Results](#understanding-results)
- [Sensitivity Analysis](#sensitivity-analysis)
- [How It Works](#how-it-works)
- [Configuration](#configuration)
- [Performance](#performance)

---

## Overview

### What It Does

Calculates intrinsic value per share using two complementary DCF methods:
- **FCFE (Free Cash Flow to Equity)**: Cash flows to equity holders after debt service
- **FCFF (Free Cash Flow to Firm)**: Cash flows to all investors before debt payments

Compares both valuations to market price and generates actionable investment signals.

### Key Features

✅ **Dual Valuation** (FCFE + FCFF)
- Cross-validation between equity and firm methods
- Leverage effect analysis
- Identifies capital structure risks

✅ **9-Category Investment Signals**
- Strong Buy, Buy, Buy (Equity Upside)
- Caution (Long), Hold, Caution (Leverage)
- Speculative (High Leverage), Speculative (Execution Risk), Avoid
- Based on comparing both methods vs market price

✅ **Implied Growth Rate Solver**
- Newton-Raphson method with bisection fallback
- Reverse-engineers what growth rate the market is pricing in
- Reality check for market expectations

✅ **Growth Rate Clamping**
- Prevents unrealistic projections (default: -20% to +50%)
- Flags when clamping occurs
- Protects against extreme assumptions

✅ **Special Bank Handling**
- PPNR-based EBIT calculations for financial institutions
- Automatic industry detection
- Handles different income statement structures

✅ **Multi-Country Support**
- Country-specific risk-free rates, ERPs, tax rates
- 20+ countries supported
- Industry-specific unlevered betas (Damodaran data)

✅ **Comprehensive Visualization**
- Waterfall chart (Market → Surplus → Intrinsic Value)
- Sensitivity analysis (4-panel: growth, discount, terminal, tornado)
- FCFE vs FCFF comparison bar chart
- Cost of capital breakdown (equity components + WACC pie)

### Status

**✅ Complete**
- 15 unit tests, all passing
- Complete documentation
- Integrated with quickstart menu
- Full visualization suite

---

## Quick Start

### Prerequisites

```bash
# OCaml dependencies
opam install . --deps-only --with-test --yes

# Python dependencies
uv sync

# Verify build
opam exec -- dune build
```

### Interactive Menu (Recommended)

```bash
./quickstart.sh
# → Run (3) → Valuation (2) → DCF Deterministic (1) → Do Everything (5)
```

This will:
1. Fetch financial data (yfinance)
2. Run DCF valuation
3. Generate visualizations
4. Display results

### Manual Execution

```bash
# Single ticker
opam exec -- dune exec dcf_deterministic -- -ticker AAPL

# With custom paths
opam exec -- dune exec dcf_deterministic -- \
  -ticker MSFT \
  -data-dir valuation/dcf_deterministic/data \
  -log-dir valuation/dcf_deterministic/log

# Run sensitivity analysis
opam exec -- dune exec dcf_sensitivity -- -ticker AAPL

# Generate visualizations
uv run valuation/dcf_deterministic/python/viz/plot_results.py --ticker AAPL
```

### Output

**Log files:** `valuation/dcf_deterministic/log/dcf_TICKER_YYYYMMDD_HHMMSS.log`

**Visualizations:** `valuation/dcf_deterministic/output/`
- `dcf_comparison_all.png` - Multi-ticker comparison
- `dcf_sensitivity_TICKER.png` - 4-panel sensitivity analysis
- `dcf_waterfall_TICKER.png` - Value decomposition
- `cost_of_capital_TICKER.png` - CAPM and WACC breakdown

**Example output:**
```
========================================
DCF Valuation: AAPL
========================================

Market Data:
  Current Price: $271.84

Cost of Capital:
  Risk-Free Rate: 4.15%
  Equity Risk Premium: 4.33%
  Leveraged Beta: 0.92
  Cost of Equity: 8.13%
  WACC: 7.91%

Growth Rates:
  FCFE Growth Rate: 0.00%
  FCFF Growth Rate: 3.91%

Valuation Results:
  FCFE Method:
    Intrinsic Value per Share: $117.36
    Margin of Safety: -56.83%

  FCFF Method:
    Intrinsic Value per Share: $120.75
    Margin of Safety: -55.58%

Investment Signal: Avoid/Sell
  Both valuations below market price.
  Insufficient cash flows to justify current valuation.
```

---

## Understanding Results

### Reading the Valuation Summary

**FCFE IVPS (Intrinsic Value Per Share - Equity Method)**
- Cash flows to equity holders after debt payments
- Uses Cost of Equity (CAPM) as discount rate
- Best for: Companies with stable capital structure

**FCFF IVPS (Intrinsic Value Per Share - Firm Method)**
- Cash flows to all investors (debt + equity) before debt payments
- Uses WACC (Weighted Average Cost of Capital) as discount rate
- Subtracts net debt to get equity value
- Best for: Companies with changing leverage

**Margin of Safety (MoS)**
- Formula: `(IVPS - Price) / Price × 100%`
- Positive: Stock is undervalued (IVPS > Price)
- Negative: Stock is overvalued (IVPS < Price)
- Zero: Stock is fairly valued (IVPS ≈ Price)

### FCFE vs FCFF Agreement

#### When They Agree (FCFE ≈ FCFF)

**Example:** FCFE = $100, FCFF = $102

```
✓ High confidence valuation
- Both methods produce similar result
- Capital structure effects are minimal
- Reliable estimate of intrinsic value

Action: Trust the valuation, use average as point estimate
```

**Conditions for Agreement:**
- Low debt (debt/equity < 0.5)
- Similar ROE and ROIC
- Stable capital structure

#### When FCFE > FCFF (Equity Method Higher)

**Example:** FCFE = $120, FCFF = $95

```
⚠️ Negative net debt or tax shield benefit
- Company has more cash than debt (net debt < 0)
- Common in: Tech companies (AAPL, GOOGL, MSFT)

Root Cause:
- Net Debt = Total Debt - Cash < 0
- Company is net lender (excess cash)

Action: Use FCFE as primary estimate
Signal: BuyEquityUpside (equity holders benefit from cash reserves)
```

#### When FCFE < FCFF (Firm Method Higher)

**Example:** FCFE = $80, FCFF = $120

```
⚠️ High leverage or debt burden
- Significant debt load
- Interest expense reduces equity cash flows
- FCFF shows enterprise value, debt claims come first

Root Cause:
- Debt/Equity > 1.0 (highly leveraged)
- Interest Coverage < 3× (vulnerable to rate increases)
- Common in: Utilities, REITs, capital-intensive industries

Action: Use FCFF as primary (shows firm value before leverage)
Signal: CautionLong (firm is valuable but equity is risky)
```

#### Extreme Disagreement (>30% difference)

**Example:** FCFE = $50, FCFF = $150 (3× difference!)

```
🚨 Red flag - investigate before trusting valuation

Possible Causes:
1. Financial distress (FCFE << FCFF)
   - Debt exceeds sustainable level
   - Risk of equity wipeout
   - Signal: Avoid or SpeculativeHighLeverage

2. Data quality issue
   - Incorrect debt value
   - Stale financial data

Action:
- Re-check input data
- Compare to industry peers
- Use scenario analysis or probabilistic DCF
```

### Investment Signal Classification

| Signal | FCFE vs Price | FCFF vs Price | Interpretation | Action |
|--------|---------------|---------------|----------------|--------|
| **StrongBuy** | Undervalued | Undervalued | High conviction buy | Accumulate |
| **Buy** | Fair | Undervalued | Moderate buy, firm value good | Buy on dips |
| **BuyEquityUpside** | Undervalued | Fair | Equity has excess cash | Buy for cash yield |
| **CautionLong** | Overvalued | Undervalued | Firm good, equity risky | Monitor leverage |
| **Hold** | Fair | Fair | Fairly valued | Hold current position |
| **CautionLeverage** | Undervalued | Overvalued | Equity cheap but firm overvalued | Caution - leverage risk |
| **SpeculativeHighLeverage** | Overvalued | Fair | High debt, speculative | Avoid or hedge |
| **SpeculativeExecutionRisk** | Fair | Overvalued | Execution/business model risk | Avoid or short |
| **Avoid/Sell** | Overvalued | Overvalued | High conviction avoid | Sell or avoid |

**Signal Thresholds:**
```
Undervalued: IVPS > Price × 1.05  // >5% upside
Fair: Price × 0.95 ≤ IVPS ≤ Price × 1.05  // ±5% range
Overvalued: IVPS < Price × 0.95  // >5% downside
```

### Interpreting Margin of Safety

**Large Positive MoS (>30%)**
- Significant undervaluation OR market pricing in serious risks OR DCF too optimistic
- Action: Verify assumptions, research hidden risks, compare to peers

**Moderate Positive MoS (+10% to +30%)**
- Stock undervalued with reasonable margin
- Typical for quality companies during corrections
- Action: Suitable for value investing, build position gradually

**Small Positive MoS (+5% to +10%)**
- Fairly valued with slight upside
- Within normal valuation noise
- Action: Hold if owned, buy only with high conviction

**Near Zero MoS (-5% to +5%)**
- Fairly valued, market and DCF agree
- Signal: Hold
- Action: No action required, monitor fundamentals

**Negative MoS (<-10%)**
- Overvalued by DCF standards
- Market more optimistic than DCF
- Action: Avoid new positions, consider reducing if held

### Cost of Capital

**Cost of Equity (CE) - CAPM Formula:**
```
CE = RFR + β_L × ERP

Example: CE = 4.0% + 1.15 × 5.5% = 10.33%
```

**Typical CE Ranges:**
- Low risk (utilities, staples): 7-9%
- Medium risk (industrials, financials): 9-12%
- High risk (tech, biotech, small-cap): 12-18%
- Very high risk (distressed, speculative): >18%

**WACC (Weighted Average Cost of Capital):**
```
WACC = (E/(E+D)) × CE + (D/(E+D)) × CB × (1 - tax_rate)

Key Relationships:
- WACC < CE (always, debt is cheaper than equity)
- Higher debt/equity → lower WACC (up to a point)
- But: Higher leverage → higher β_L → higher CE (offsetting effect)
```

### Growth Rates

**FCFE Growth: ROE-Based**
```
g_FCFE = ROE × Retention Ratio

Where:
- ROE = Net Income / Book Value of Equity
- Retention Ratio = 1 - (FCFE / Net Income)
```

**Interpreting FCFE Growth:**
- High growth (>12%): Growth companies reinvesting heavily
- Moderate growth (6-12%): Mature companies, balanced allocation
- Low growth (2-6%): Mature, slow-growth industries
- Negative growth (<0%): Declining or returning excess cash

**FCFF Growth: ROIC-Based**
```
g_FCFF = ROIC × Reinvestment Rate

Where:
- ROIC = NOPAT / Invested Capital
- Reinvestment Rate = (CapEx + ΔWC - Depreciation) / NOPAT
```

**ROIC Benchmarks:**
- Excellent (>15%): High moat, pricing power
- Good (10-15%): Above cost of capital, value-creating
- Fair (7-10%): Around WACC, break-even on value
- Poor (<7%): Below WACC, value-destroying

**Growth Rate Clamping:**
- Prevents unrealistic perpetual growth (e.g., 18% forever)
- Default bounds: -20% to +50%
- Terminal growth: 2-3% (GDP + inflation)
- If clamped: Consider scenario analysis or probabilistic DCF

### Implied Growth Rates

The growth rate that makes DCF IVPS equal to current market price.

**Implied < Actual:**
```
Actual Growth: 12%
Implied Growth: 10%

Interpretation: Market is more conservative than DCF
Signal: Bullish (stock undervalued if 12% growth materializes)
```

**Implied > Actual:**
```
Actual Growth: 8%
Implied Growth: 14%

Interpretation: Market is more optimistic than DCF
Signal: Bearish (market expectations may be too high)
```

**Implied ≈ Actual:**
```
Actual Growth: 10%
Implied Growth: 10.2%

Interpretation: Market and DCF agree
Signal: Neutral (fairly valued)
```

### When to Trust (or Question) the DCF

**Trust the DCF When:**
- ✅ Input data is high quality (recent, audited)
- ✅ Business is mature and predictable
- ✅ FCFE and FCFF agree (within 10%)
- ✅ Growth assumptions are reasonable (ROE/ROIC < 25%)
- ✅ Discount rate is appropriate (CE: 8-15%)
- ✅ Valuation matches peer analysis

**Question the DCF When:**
- ❌ Extreme valuation gap (IVPS is 3× or 0.3× price)
- ❌ High-growth/early-stage company (biotech, IPO < 2 years)
- ❌ Cyclical business at peak/trough (commodities)
- ❌ Financial distress (negative equity, interest coverage < 2×)
- ❌ Significant intangibles not captured (brand, network effects, IP)
- ❌ Structural change expected (M&A, regulation, disruption)

---

## Sensitivity Analysis

The sensitivity analysis shows how changes in key assumptions affect intrinsic value. Generated via `dcf_sensitivity` executable.

### The Four Panels

#### 1. Sensitivity to Growth Rate (Top-Left)

**What it shows:** How intrinsic value changes with different near-term growth rate assumptions.

**How to read it:**
- X-axis: Growth rate from -2% to +6%
- Y-axis: Resulting IVPS
- Gray line: Your base case assumption
- Red line: Current market price

**Interpretation:**
- **Steep slope** = Highly sensitive to growth. Small errors create large valuation swings.
- **Flat slope** = Relatively insensitive to growth.
- **Lines cross market price** = Break-even growth rate (what growth justifies current price?)

**Example:** If FCFE crosses market price at 4% but base case is 2.5%, market is pricing in significantly higher growth.

#### 2. Sensitivity to Discount Rate (Top-Right)

**What it shows:** How intrinsic value changes with different cost of capital assumptions.

**How to read it:**
- X-axis: Discount rate from 6% to 12%
- Y-axis: Resulting IVPS
- Gray line: Your cost of equity estimate
- Red line: Current market price
- **Inverse relationship:** Higher discount rate → lower valuation

**Interpretation:**
- **Steep downward slope** = Very sensitive to cost of capital.
- **Lines cross market price** = Implied discount rate (what rate justifies current price?)

**Example:** If your CE is 9% but market price intersects at 7%, market may be using lower risk premium.

#### 3. Sensitivity to Terminal Growth (Bottom-Left)

**What it shows:** How intrinsic value changes with different perpetual growth assumptions.

**Why it matters:** Terminal value typically represents 50-80% of total DCF value.

**How to read it:**
- X-axis: Terminal growth from 1% to 4%
- Y-axis: Resulting IVPS
- Gray line: Base case terminal growth (~2.5%)
- Red line: Current market price

**Interpretation:**
- **Very steep slope** = Terminal value dominates valuation. Red flag for reliability.
- **Moderate slope** = More balanced between near-term and terminal value.

**Economic constraints:**
- Terminal growth cannot exceed nominal GDP growth long-term (~3-4%)
- Terminal growth > 3.5% implies company eventually becomes entire economy (impossible)

#### 4. Tornado Diagram (FCFE) (Bottom-Right)

**What it shows:** Comparative sensitivity across all four key assumptions in a single view.

**How to read it:**
- Y-axis: Four assumptions (Growth Rate, Discount Rate, Terminal Growth, Beta)
- X-axis: Change in FCFE IVPS (dollars)
- Red bars (left): Downside scenario (pessimistic)
- Green bars (right): Upside scenario (optimistic)
- Black vertical line: Base case

**Bar width = sensitivity magnitude.** Wider bars = more sensitive.

**Interpretation:** Ranks assumptions by impact. Focus research on widest bars.

**Example ranking:**
```
Terminal Growth  ████████████████████ (widest)  → Focus research here
Discount Rate    ████████████████              → Second priority
Growth Rate      ██████████                    → Less critical
Beta             ████                          → Least sensitive
```

**Decision rule:**
- If combined upside (all green bars) is below market price → Even optimistic assumptions can't justify valuation → **Avoid**
- If combined downside (all red bars) is above market price → Even pessimistic assumptions justify valuation → **Strong Buy**

### Common Sensitivity Patterns

**Pattern 1: "Discount Rate Dominated"**
- Discount rate sensitivity dwarfs everything else
- Implication: Most uncertainty from cost of capital estimation
- Action: Focus on refining beta, risk premium, capital structure

**Pattern 2: "Terminal Value Dominated"**
- Terminal growth sensitivity is extreme
- Implication: Valuation mostly driven by perpetual cash flows
- Warning: High terminal value dependence reduces reliability
- Action: Consider extending explicit forecast period to 10+ years

**Pattern 3: "Growth Rate Insensitive"**
- Growth rate has minimal impact
- Implication: Mature stage, low growth contribution to value
- Action: Focus accuracy on margins and capital efficiency

**Pattern 4: "Market Price at Extremes"**
- Market price only intersects at extreme assumptions (e.g., 6% terminal growth)
- Implication: Market pricing in assumptions outside reasonable ranges
- Signal: Potential overvaluation or model missing key value drivers

### Practical Usage

1. **Identify most sensitive assumption** (tornado diagram - widest bar)
2. **Cross-check with detailed panel** (see full sensitivity curve)
3. **Compare to market price** (which assumptions reconcile the difference?)
4. **Assess robustness**:
   - Narrow sensitivity range → High confidence
   - Wide sensitivity range → Low confidence, margin of safety required

---

## How It Works

### Architecture

**Modular Decomposition** (Functional, Single-Responsibility):
```
ocaml/lib/
├── types.ml[i]              - Rich domain types
├── capital_structure.ml[i]  - CAPM, WACC, leveraged beta
├── cash_flow.ml[i]          - FCFE/FCFF calculations
├── growth.ml[i]             - ROE/ROIC growth estimation
├── projection.ml[i]         - Multi-year projections
├── valuation.ml[i]          - PV calculations, terminal values
├── solver.ml[i]             - Implied growth solver
├── signal.ml[i]             - Investment signal classification
└── io.ml[i]                 - JSON I/O, logging

ocaml/bin/
├── main.ml                  - Main valuation entry point
├── sensitivity_main.ml      - Sensitivity analysis
└── scenarios_main.ml        - Scenario analysis (bull/base/bear)
```

**Total:** ~1500 lines of OCaml, ~200 lines of Python (fetch + viz)

### DCF Formulas

**Free Cash Flow to Equity (FCFE):**
```
FCFE = Net Income
       - (CapEx - Depreciation)
       - ΔWorking Capital
       + Net Borrowing

Growth Rate:
g_FCFE = ROE × Retention Ratio
  where Retention = 1 - (FCFE / Net Income)

Valuation:
IVPS_FCFE = Σ(FCFE_t / (1 + CE)^t) + Terminal Value
  where Terminal Value = FCFE_n × (1 + g_term) / (CE - g_term)
  and CE = RFR + β_L × ERP  (CAPM)
```

**Free Cash Flow to Firm (FCFF):**
```
FCFF = EBIT × (1 - tax_rate)
       + Depreciation
       - CapEx
       - ΔWorking Capital

Also: FCFF = NOPAT - Net Investment
  where NOPAT = Net Operating Profit After Tax

Growth Rate:
g_FCFF = ROIC × Reinvestment Rate
  where ROIC = NOPAT / Invested Capital
  and Reinvestment Rate = (CapEx + ΔWC - Depreciation) / NOPAT

Valuation:
Enterprise Value = Σ(FCFF_t / (1 + WACC)^t) + Terminal Value
  where Terminal Value = FCFF_n × (1 + g_term) / (WACC - g_term)

Equity Value = Enterprise Value - Net Debt
IVPS_FCFF = Equity Value / Shares Outstanding

WACC = (E/(E+D)) × CE + (D/(E+D)) × CB × (1 - tax)
```

**Leveraged Beta (Hamada Formula):**
```
β_L = β_U × [1 + (1 - tax_rate) × (D/E)]

Where:
- β_L = Leveraged beta (equity beta)
- β_U = Unlevered beta (industry beta)
- D/E = Market debt-to-equity ratio
```

### Implied Growth Solver

**Newton-Raphson Method:**
```
Objective: Find g such that IVPS(g) = Market Price

Iteration:
g_new = g_old - f(g_old) / f'(g_old)

Where:
f(g) = IVPS(g) - Price
f'(g) ≈ ∂IVPS/∂g (numerical derivative)

Fallback: Bisection search if Newton-Raphson fails to converge
Max iterations: 100
Tolerance: $0.01
```

### Special Bank Handling

**Financial institutions** use different income statement structure:
```
EBIT (for banks) = PPNR (Pre-Provision Net Revenue)
  = Net Interest Income
    + Non-Interest Income
    - Operating Expenses

Avoids: Loan loss provisions (non-cash, volatile)
```

Auto-detected via industry classification or `is_bank` flag.

### Data Pipeline

**Integrated OCaml-Python Workflow:**
1. OCaml calls `uv run valuation/dcf_deterministic/python/fetch_financials.py`
2. Python fetches data via yfinance API
3. Python writes JSON to `/tmp/dcf_market_data_TICKER.json` and `/tmp/dcf_financial_data_TICKER.json`
4. OCaml reads JSON, performs valuation, writes log to `log/dcf_TICKER_TIMESTAMP.log`
5. (Optional) Visualization reads logs, generates PNG to `output/`

**Data Caching:** 1-day cache in `/tmp/` to avoid rate limits.

---

## Configuration

### Data Files (in `valuation/dcf_deterministic/data/`)

**`risk_free_rates.json`** - Government bond yields by country (1y, 3y, 5y, 7y, 10y)
- Source: Central banks, treasuries
- Update: Monthly (if change >25 bps)
- Countries: USA, Canada, Germany, UK, Japan, China, India, and more

**`equity_risk_premiums.json`** - Country-specific ERPs
- Source: Aswath Damodaran (NYU Stern)
- URL: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html
- Update: Annually (January)

**`industry_betas.json`** - Unlevered betas by industry sector
- Source: Aswath Damodaran (NYU Stern)
- URL: http://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/Betas.html
- Update: Annually (January)

**`tax_rates.json`** - Corporate tax rates by country
- Source: OECD, PwC, KPMG
- Update: Annually (when laws change)

**`params.json`** - Model parameters
```json
{
  "projection_years": 5,
  "terminal_growth_rate": 0.025,
  "growth_clamp_lower": -0.20,
  "growth_clamp_upper": 0.50,
  "mos_tolerance": 0.05
}
```

**See `data/DATA_SOURCES.md`** for comprehensive documentation of all data sources, update frequencies, and validation checklists.

### Format

All configuration files use JSON with decimal representations:
- **Rates:** Decimal (e.g., 0.0425 = 4.25%)
- **Percentages:** Decimal (e.g., 0.21 = 21%)
- **Country names:** Match yfinance conventions (e.g., "United States" not "US")

### Parameter Effects

**`projection_years`** (default: 5)
- More years = more explicit forecast, less terminal value weight
- Typical: 5-10 years
- Trade-off: Accuracy vs. uncertainty in long-term forecasts

**`terminal_growth_rate`** (default: 0.025 = 2.5%)
- Perpetual growth rate after explicit forecast period
- **Must be < discount rate** (otherwise infinite value)
- **Must be ≤ GDP growth** (3-4% for developed markets)
- Valuation is very sensitive to this parameter (see sensitivity analysis)

**`growth_clamp_lower`** (default: -0.20 = -20%)
- Minimum allowed growth rate
- Prevents extreme decline assumptions
- Typical: -20% to 0%

**`growth_clamp_upper`** (default: 0.50 = 50%)
- Maximum allowed growth rate
- Prevents unrealistic perpetual growth
- Typical: 10% to 50% (narrower for mature companies)

**`mos_tolerance`** (default: 0.05 = 5%)
- Threshold for "fairly valued" classification
- IVPS within ±5% of price → Hold signal
- Outside range → Buy or Avoid signal

---

## Performance

**Build Time:** < 5 seconds

**Single Valuation:** < 3 seconds (including data fetch)

**Sensitivity Analysis:** < 5 seconds (50 parameter sweeps)

**Visualization:** < 3 seconds (4-panel plots)

**Memory Usage:** < 50MB

**Batch Processing:** ~3 seconds per ticker (sequential)

**Dependencies:**
- OCaml: yojson >= 2.0, ppx_deriving >= 5.2, unix (stdlib)
- Python: yfinance >= 0.2.50, pandas, numpy, matplotlib, seaborn

**Typical Execution Time:**
- 1 ticker (full workflow): 10 seconds
- 10 tickers (full workflow): 60 seconds
- 50 tickers (batch): 5 minutes

**Performance Tips:**
- Use cached data (1-day cache in `/tmp/`)
- Process tickers sequentially to avoid API rate limits
- Generate visualizations in batch after all valuations complete

---

## See Also

- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions
- **[data/DATA_SOURCES.md](data/DATA_SOURCES.md)** - Data sources reference
- **[Root README](../../README.md)** - Project overview, model comparison

**Related Models:**
- **[DCF Probabilistic](../dcf_probabilistic/README.md)** - Monte Carlo simulation for uncertainty quantification
- **[Regime Downside](../../pricing/regime_downside/README.md)** - Portfolio optimization

---

## Design Principles

**Type-Driven Design:**
- All types defined in `types.ml[i]` with ppx_deriving
- Rich domain types encode constraints upfront
- Explicit over implicit (e.g., `is_bank` flag)

**Functional Purity:**
- No global state, all parameters passed explicitly
- Pure functions enable easy testing and reasoning
- Option types for failure cases (e.g., terminal value validation)

**Robustness:**
- JSON parsing handles both int and float types
- Comprehensive error handling with meaningful messages
- Guards against invalid terminal growth rates (TGR >= discount rate)

**Extensibility:**
- Easy to add new countries (update JSON files)
- Easy to add new industries (update betas)
- Modular design allows feature additions without breaking changes

---

**Final Rule:** DCF is a tool, not truth. Combine with qualitative analysis, peer comparison, and market context for informed decisions.

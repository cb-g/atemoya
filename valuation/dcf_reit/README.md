# DCF REIT - Real Estate Investment Trust Valuation

Specialized valuation model for REITs using industry-standard metrics: FFO/AFFO, NAV, and Dividend Discount Models.

## Why a Separate REIT Model?

Traditional DCF models don't work well for REITs because:

1. **Depreciation is non-economic**: Real estate typically appreciates, not depreciates
2. **Mandatory distributions**: REITs must pay out 90%+ of taxable income as dividends
3. **Growth comes externally**: REITs grow through debt/equity issuance, not retained earnings
4. **NAV matters**: Property values (NOI/cap rate) are often more relevant than cash flow projections

## Valuation Methods

This model uses four complementary approaches:

### 1. FFO/AFFO Analysis
- **FFO** (Funds From Operations) = Net Income + Depreciation + Amortization - Gains on Sales
- **AFFO** (Adjusted FFO) = FFO - Maintenance CapEx - Straight-line Rent Adjustments
- AFFO is the best proxy for sustainable cash flow

### 2. NAV Valuation
- Property Value = NOI / Cap Rate
- NAV = Property Value + Cash - Debt
- Compares market price to underlying asset value

### 3. P/FFO & P/AFFO Multiples
- Relative valuation vs sector averages
- Quality-adjusted targets (premium REITs deserve higher multiples)

### 4. Dividend Discount Model
- Gordon Growth: P = D / (ke - g)
- Two-stage DDM for high-growth REITs
- Particularly relevant given mandatory high payouts

## Property Sectors

Each sector has different risk/return characteristics:

| Sector | Default Cap Rate | Avg P/FFO | Risk Profile |
|--------|-----------------|-----------|--------------|
| Industrial | 5.0% | 22x | Low - Strong demand, limited supply |
| Data Center | 5.5% | 20x | Low-Med - Tech-driven secular growth |
| Residential | 5.0% | 20x | Low - Housing shortage support |
| Self Storage | 5.5% | 18x | Low - Fragmented, sticky customers |
| Healthcare | 6.5% | 14x | Medium - Aging demographics |
| Office | 7.0% | 12x | High - WFH headwinds |
| Retail | 7.0% | 13x | High - E-commerce disruption |
| Hotel | 8.0% | 10x | High - Cyclical, volatile |

## Quality Scoring

The model scores REITs on five dimensions (0-1 scale):

1. **Occupancy** (15%): >95% = excellent, <85% = poor
2. **Lease Quality** (15%): WALT and near-term expirations
3. **Balance Sheet** (25%): Debt/Cap, Debt/NOI ratios
4. **Growth** (20%): Same-store NOI growth
5. **Dividend Safety** (25%): AFFO payout ratio

## Quick Start

```bash
# Fetch REIT data
cd valuation/dcf_reit
uv run python/fetch/fetch_reit_data.py -t PLD O EQIX -o data

# Run valuation
dune exec ocaml/bin/main.exe -- -d data -o output/data

# Generate visualization
uv run python/viz/plot_reit_valuation.py -i output/data/PLD_valuation.json -o output/plots
```

## Input Data Format

```json
{
  "market": {
    "ticker": "PLD",
    "price": 115.50,
    "shares_outstanding": 927000000,
    "market_cap": 107066500000,
    "dividend_yield": 0.033,
    "dividend_per_share": 3.80,
    "currency": "USD",
    "sector": "industrial"
  },
  "financial": {
    "revenue": 8300000000,
    "net_income": 3100000000,
    "depreciation": 2200000000,
    "amortization": 50000000,
    "gains_on_sales": 450000000,
    "impairments": 0,
    "straight_line_rent_adj": 120000000,
    "stock_compensation": 180000000,
    "maintenance_capex": 400000000,
    "development_capex": 2500000000,
    "total_debt": 28000000000,
    "cash": 800000000,
    "total_assets": 95000000000,
    "total_equity": 52000000000,
    "noi": 6800000000,
    "occupancy_rate": 0.97,
    "same_store_noi_growth": 0.045,
    "weighted_avg_lease_term": 5.2,
    "lease_expiration_1yr": 0.08
  }
}
```

## Output

### JSON Valuation Result
```json
{
  "ticker": "PLD",
  "price": 115.50,
  "fair_value": 120.51,
  "upside_potential": 0.043,
  "signal": "HOLD",
  "ffo_metrics": {
    "ffo_per_share": 5.29,
    "affo_per_share": 4.53,
    "affo_payout_ratio": 0.84
  },
  "nav": {
    "nav_per_share": 117.37,
    "premium_discount": -0.016
  },
  "quality": {
    "overall_quality": 0.88
  }
}
```

### Investment Signals

| Signal | Criteria |
|--------|----------|
| **STRONG BUY** | >30% upside, quality >= 0.45 |
| **BUY** | 15-30% upside, quality >= 0.45 |
| **HOLD** | -10% to +15% |
| **SELL** | 10-25% overvalued |
| **STRONG SELL** | >25% overvalued |
| **CAUTION** | Quality < 0.45 (elevated risk) |

## Interpreting Results

### Key Metrics to Watch

1. **AFFO Payout Ratio**
   - <75%: Very safe, room for dividend growth
   - 75-85%: Healthy
   - 85-95%: Tight, limited growth capacity
   - >100%: Unsustainable, dividend at risk

2. **NAV Premium/Discount**
   - >+20% premium: Expensive unless exceptional quality
   - +10% to +20%: Fair for high-quality REITs
   - -10% to +10%: Fairly valued
   - <-10% discount: Potential value (or quality concerns)

3. **P/FFO vs Sector**
   - Below sector + high quality = attractive
   - Above sector + average quality = expensive
   - Check if premium is justified by growth/quality

4. **Quality Score**
   - >0.85: Premium quality, deserves premium valuation
   - 0.70-0.85: Good quality
   - 0.55-0.70: Average
   - <0.55: Below average, requires larger margin of safety

## Directory Structure

```
valuation/dcf_reit/
├── ocaml/
│   ├── lib/
│   │   ├── types.ml       # REIT-specific data types
│   │   ├── ffo.ml         # FFO/AFFO calculations
│   │   ├── nav.ml         # NAV valuation
│   │   ├── ddm.ml         # Dividend discount models
│   │   ├── quality.ml     # Quality scoring
│   │   ├── valuation.ml   # Combined valuation
│   │   └── io.ml          # JSON I/O
│   ├── bin/main.ml        # CLI executable
│   └── test/              # Unit tests
├── python/
│   ├── fetch/fetch_reit_data.py    # Yahoo Finance fetcher
│   └── viz/plot_reit_valuation.py  # Visualization
├── data/                  # Sample REIT data
└── output/
    ├── data/              # JSON results
    └── plots/             # Visualizations
```

## Sample REITs Included

| Ticker | Sector | Description |
|--------|--------|-------------|
| PLD | Industrial | Prologis - Largest industrial REIT |
| O | Retail | Realty Income - "Monthly Dividend Company" |
| EQIX | Data Center | Equinix - Global data center leader |

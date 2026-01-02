# Troubleshooting Guide: DCF Probabilistic Valuation (Monte Carlo)

This guide helps resolve common issues when using the probabilistic discounted cash flow (DCF) valuation model with Monte Carlo simulation.

---

## Installation Issues

### Problem: `opam` or `uv` not found
**Solution**: See [DCF Deterministic TROUBLESHOOTING.md](../dcf_deterministic/TROUBLESHOOTING.md#installation-issues) - same steps apply.

---

### Problem: `scipy` not installed
**Symptom**: Visualization fails with "No module named 'scipy'"

**Cause**: SciPy (required for KDE plots) not in environment

**Solution**:
```bash
uv sync  # Installs all dependencies including scipy

# Verify installation
uv run python -c "import scipy; print(scipy.__version__)"
```

---

## Runtime Errors

### Problem: "Time series data not found for ticker X"
**Symptom**: Simulation fails immediately with missing data error

**Cause**: Historical time series (4-year) not fetched

**Solution**:
```bash
# Fetch 4-year time series data (from project root: atemoya/)
uv run valuation/dcf_probabilistic/python/fetch/fetch_financials_ts.py --ticker AAPL --years 4

# Output will be in /tmp/dcf_prob_time_series_AAPL.json
```

**Requirement**: Probabilistic DCF requires 4 years of historical data for statistical estimation.

---

### Problem: "Insufficient data points for sampling"
**Symptom**: Simulation fails with "Array too small for statistics"

**Cause**: Time series has <4 years of data (e.g., recent IPO)

**Solution**:
1. **Skip ticker**: Cannot value with <4 years history
2. **Use deterministic DCF** instead (single-year data)
3. **Pad with industry averages** (advanced, not recommended)

**Minimum**: 4 annual data points required for lognormal sampling.

---

### Problem: Simulation is very slow (>2 minutes for 1000 iterations)
**Symptom**: Monte Carlo taking excessive time

**Cause**:
1. **Too many simulations** (10,000+ iterations)
2. **Too many tickers** (batch processing 50+ stocks)
3. **Complex calculations** per iteration

**Solution**:
1. **Reduce simulations** in `data/params_probabilistic.json`:
   ```json
   {
     "num_simulations": 1000  // Reduce from 10000
   }
   ```

2. **Process tickers sequentially** instead of batch

3. **Use haiku model** for faster execution (if using LLM features)

**Benchmark**:
- 1000 simulations: ~10-30 seconds per ticker
- 5000 simulations: ~60-120 seconds per ticker
- 10000 simulations: ~3-5 minutes per ticker

---

### Problem: "NaN in simulation results"
**Symptom**: Output CSV contains NaN values

**Cause**:
1. **Division by zero** (zero equity, zero capital)
2. **Infinite growth rates** (ROE or ROIC = infinity)
3. **Numerical overflow** (very large intermediate values)

**Diagnosis**:
```bash
# Check time series data
cat /tmp/dcf_prob_time_series_TICKER.json | grep "0.0"

# Check for NaN/Inf in output
grep -i "nan\|inf" valuation/dcf_probabilistic/output/*.csv
```

**Solution**:
1. **Data cleaning**: Sampling module should handle this with `clean_array`
2. **Re-fetch data**: May be temporary API issue
3. **Skip problematic ticker**: If fundamentally has data issues

**Prevention**: Use `sample_financial_metric` with capping to prevent extreme outliers.

---

### Problem: Simulation results have extreme outliers
**Symptom**: Some IVPS values are $10,000 while median is $100

**Cause**: Lognormal sampling with high variance can produce extreme tails

**Diagnosis**:
```bash
# Check simulation matrix
cat output/simulations_fcfe.csv | sort -n | tail -10  # See max values
```

**Solution**:
1. **Increase squashing threshold** in sampling:
   ```ocaml
   (* In sampling.ml *)
   let squash ~value ~threshold:200.0  // Cap extreme values at 200% of median
   ```

2. **Use robust statistics** (median instead of mean):
   - P50 (median) less sensitive to outliers than mean
   - Use P10-P90 range for valuation band

3. **Increase Bayesian prior weight** (smooths extreme empirical values):
   ```json
   {
     "prior_weight": 0.7  // Increase from 0.5 (more regularization)
   }
   ```

**Interpretation**: Extreme outliers in probabilistic model reflect uncertainty. Use percentiles (P10, P50, P90) instead of mean.

---

### Problem: "Probability of undervaluation is 0% or 100%"
**Symptom**: P(IV > Price) = 0.0 or 1.0 exactly

**Cause**:
1. **All simulations** agree (very high conviction signal)
2. **Too few simulations** (discrete probabilities)
3. **Extreme market price** relative to distribution

**Diagnosis**:
- 0%: All simulations < market price → Strong Avoid signal
- 100%: All simulations > market price → Strong Buy signal

**Solution**:
1. **Increase simulations** for finer probability resolution:
   ```json
   {
     "num_simulations": 5000  // Increase from 1000
   }
   ```

2. **Verify not a data error**: Check if market price is realistic

**Interpretation**: 0% or 100% probability is a strong signal, not necessarily an error.

---

## Configuration Issues

### Problem: "Bayesian priors not found"
**Symptom**: Simulation runs but ignores priors

**Cause**: `data/bayesian_priors.json` missing or malformed

**Solution**:
1. **Check file exists**:
   ```bash
   cat valuation/dcf_probabilistic/data/bayesian_priors.json
   ```

2. **Verify structure**:
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

3. **Disable priors** if needed:
   ```json
   {
     "use_bayesian_priors": false  // In params_probabilistic.json
   }
   ```

---

### Problem: "Stochastic discount rates disabled but wanted"
**Symptom**: All simulations use same cost of capital

**Cause**: Feature flag disabled in config

**Solution**: Enable in `data/params_probabilistic.json`:
```json
{
  "use_stochastic_discount_rates": true,
  "rfr_volatility": 0.005,  // ±50 bps
  "beta_volatility": 0.10,  // ±0.1
  "erp_volatility": 0.01    // ±1%
}
```

**Impact**: Adds uncertainty in discount rates, widening distribution of IVPS.

---

### Problem: "Time-varying growth rates seem constant"
**Symptom**: Growth rates don't change over projection years

**Cause**: Time-varying growth feature disabled

**Solution**: Enable in `data/params_probabilistic.json`:
```json
{
  "use_time_varying_growth": true,
  "growth_mean_reversion_speed": 0.2  // λ parameter, 0-1
}
```

**Model**: Exponential mean reversion toward terminal growth rate:
```
g_t = g_term + (g_0 - g_term) × exp(-λ × t)
```

---

## Data Quality Issues

### Problem: Time series has zeros in financial metrics
**Symptom**: EBIT or net income is zero for some years

**Cause**:
1. **Startup phase** (no earnings yet)
2. **Data error** (missing quarter in annual aggregation)
3. **Restructuring year** (one-time charges)

**Solution**:
1. **Clean array** (zeros removed automatically by `clean_array`)
2. **Skip ticker** if too many zeros (<2 valid years)
3. **Use FCFF** if FCFE problematic (net income issues)

**Impact**: Sampling ignores zero values, uses only positive data points.

---

### Problem: Huge variance in time series (std > 5× mean)
**Symptom**: Simulation produces very wide distribution

**Cause**: Volatile company (e.g., early-stage biotech, cyclical commodity)

**Diagnosis**: This reflects **real business risk**, not an error

**Solution**:
1. **Accept wide distribution**: High uncertainty is informative
2. **Use Bayesian priors** to regularize toward industry norms
3. **Focus on percentile ranges**: P10-P90 band shows plausible outcomes

**Interpretation**: Wide distribution → High uncertainty → Use caution, require higher margin of safety.

---

## Output Interpretation

### Problem: "Mean IVPS very different from median (P50)"
**Symptom**: Mean = $150, Median = $100

**Cause**: **Skewed distribution** (lognormal produces right skew)

**Diagnosis**: Mean > Median indicates positive skew (long right tail)

**Solution**: Use **median (P50)** as primary valuation metric:
- Median is robust to outliers
- Mean is pulled up by extreme right-tail scenarios

**Interpretation**:
- Mean > P50: Positive skew (upside potential)
- Mean < P50: Negative skew (downside risk)

Use P50 for base-case valuation, P10-P90 for range.

---

### Problem: "Why is P(Undervalued) = 30% but signal is Avoid?"
**Symptom**: Probability seems bullish but signal bearish

**Cause**: Signal uses **mean IVPS**, not probability

**Diagnosis**:
```
If P(IV > Price) = 30%:
- 30% chance undervalued
- 70% chance overvalued
- Mean IVPS likely < Price (since tail is thin)

Signal logic:
- Mean FCFE < Price → FCFE Overvalued
- Mean FCFF < Price → FCFF Overvalued
- Both overvalued → Avoid signal
```

**Solution**: Look at both metrics:
- **Probability**: Likelihood of undervaluation
- **Mean/Median**: Central tendency estimate

**Interpretation**: P(Undervalued) < 50% → More likely overvalued → Avoid.

---

### Problem: "FCFE distribution very different from FCFF"
**Symptom**: FCFE mean = $50, FCFF mean = $120

**Cause**: Leverage effect + different growth rates

**Diagnosis**:
- High debt → FCFE reduced by interest expense
- ROE ≠ ROIC due to capital structure
- Debt magnifies differences between methods

**Interpretation**: See [DCF Deterministic INTERPRETATION.md](../dcf_deterministic/INTERPRETATION.md) for leverage effect explanation.

**Action**: Check signal classification considers both methods.

---

### Problem: Efficient frontier has only 5 points instead of 5000
**Symptom**: Portfolio visualization shows sparse frontier

**Cause**:
1. **Insufficient ticker diversity** (only 2-3 stocks)
2. **Simulation failed** for some tickers
3. **Filtering removed** invalid portfolios

**Solution**:
1. **Increase number of tickers**: Need 5+ for meaningful frontier
2. **Check simulation logs** for failed tickers
3. **Verify CSV outputs** have data for all tickers

**Minimum**: 4+ tickers required for portfolio frontier analysis.

---

## Visualization Issues

### Problem: KDE plot is blocky/jagged
**Symptom**: Kernel density estimate looks rough, not smooth

**Cause**: Too few simulation points (e.g., 100 simulations)

**Solution**: Increase simulations:
```json
{
  "num_simulations": 5000  // Minimum for smooth KDE
}
```

**Note**: KDE needs 1000+ points for smooth visualization.

---

### Problem: Frontier plot has overlapping labels
**Symptom**: Can't read portfolio labels

**Solution**: Reduce number of random portfolios in `plot_frontier.py`:
```python
num_portfolios = 1000  # Reduce from 5000 for clearer plot
```

Or increase figure size:
```python
fig, ax = plt.subplots(figsize=(14, 10))  # Larger canvas
```

---

### Problem: "No output PNG files generated"
**Symptom**: Visualization script succeeds but no images

**Cause**: Output directory path issue

**Solution**:
```bash
# Check output directory exists
ls valuation/dcf_probabilistic/output/

# Run visualization with explicit path (from project root: atemoya/)
uv run valuation/dcf_probabilistic/python/viz/plot_results.py \
  --output-dir valuation/dcf_probabilistic/output \
  --viz-dir valuation/dcf_probabilistic/output
```

---

## Performance Issues

### Problem: Memory usage >8GB for 10,000 simulations
**Symptom**: System runs out of RAM

**Cause**: Large simulation matrices held in memory

**Solution**:
1. **Reduce simulations**:
   ```json
   {
     "num_simulations": 1000  // Reduce from 10000
   }
   ```

2. **Process tickers individually** instead of batch

3. **Stream to CSV** instead of accumulating in memory

**Benchmark**: 1000 simulations × 10 tickers ≈ 100MB RAM. 10,000 × 50 ≈ 5GB.

---

### Problem: Parallelization not working
**Symptom**: All simulations run sequentially

**Cause**: OCaml Domains not configured (feature not yet implemented)

**Status**: Parallelization is planned enhancement. Currently sequential.

**Workaround**: Run multiple tickers in parallel using shell:
```bash
# Run 4 tickers in parallel (from project root: atemoya/)
for ticker in AAPL GOOGL MSFT AMZN; do
  opam exec -- dune exec dcf_probabilistic -- -ticker $ticker &
done
wait
```

---

## Debugging Tips

### View simulation summary
```bash
# Check CSV output
head output/probabilistic_summary.csv

# Should show: ticker, mean_fcfe, std_fcfe, p10_fcfe, p50_fcfe, p90_fcfe, prob_undervalued_fcfe, ...
```

### Verify simulation distribution
```bash
# Quick histogram in terminal
cat output/simulations_fcfe.csv | cut -d',' -f2 | sort -n | uniq -c | head -20
```

### Check parameter configuration
```bash
# Verify all advanced features enabled
cat data/params_probabilistic.json | jq '.'
```

### Test with minimal config
```json
{
  "num_simulations": 100,
  "projection_years": 3,
  "use_bayesian_priors": false,
  "use_stochastic_discount_rates": false,
  "use_time_varying_growth": false
}
```

Run with simplest config first, then add complexity.

---

## Common Warnings (Not Errors)

### "Bayesian smoothing applied"
**Meaning**: Empirical value mixed with prior for regularization

**Action**: None. This improves robustness.

---

### "Growth rate sampled outside clamp bounds, clamped"
**Meaning**: Sampled growth > 15%, clamped for realism

**Action**: None. Prevents unrealistic scenarios.

---

### "Simulation produced negative IVPS, excluded from statistics"
**Meaning**: Some simulations resulted in negative valuation, filtered out

**Action**: Check if >10% of simulations are negative (may indicate distressed company).

---

### "Portfolio has negative weight, setting to zero"
**Meaning**: Optimization attempted short position, constrained to long-only

**Action**: None. Long-only constraint enforced.

---

## Advanced Troubleshooting

### Problem: Correlations between tickers seem wrong
**Symptom**: Uncorrelated stocks show 0.9 correlation in results

**Cause**: Sampling methodology assumes independence

**Status**: Correlation modeling planned enhancement (nice-to-have feature).

**Workaround**: Use deterministic DCF for individual tickers. Portfolio frontier currently ignores correlations.

---

### Problem: Bayesian priors don't seem to affect results
**Symptom**: Results identical with/without priors

**Cause**: Prior weight too low (e.g., 0.1)

**Solution**: Increase prior weight:
```json
{
  "prior_weight": 0.5  // Equal weight to empirical and prior
}
```

**Test**: Use extreme prior (e.g., ROE = 50%) with high weight → should see impact.

---

### Problem: Time-varying growth has no effect
**Symptom**: Terminal growth = Year 1 growth

**Cause**: Mean reversion speed = 0 (disabled)

**Solution**: Set reversion speed:
```json
{
  "growth_mean_reversion_speed": 0.2  // Moderate reversion
}
```

**Test**: Use λ = 1.0 (fast reversion) → growth converges to terminal rate by year 3-4.

---

## Getting Help

If issues persist:

1. **Check simulation logs** in `valuation/dcf_probabilistic/log/`
2. **Inspect CSV outputs** in `output/simulations_*.csv`
3. **Verify config** in `data/params_probabilistic.json`
4. **Review time series** in `/tmp/dcf_prob_time_series_*.json`
5. **Consult documentation**:
   - `README.md` - Probabilistic DCF overview
   - `IMPLEMENTATION_STATUS.md` - Feature implementation status
   - `../dcf_deterministic/INTERPRETATION.md` - Valuation interpretation

6. **File an issue** with:
   - Ticker symbol
   - Error message or unexpected behavior
   - Config file (params_probabilistic.json)
   - Simulation summary (first 5 rows of CSV)
   - Number of simulations attempted

# Troubleshooting Guide: Regime-Aware Downside Optimization

This guide helps resolve common issues when using the regime-downside portfolio optimizer.

---

## Installation Issues

### Problem: `opam` command not found
**Symptom**: Running `opam install` fails with "command not found"

**Cause**: OPAM (OCaml Package Manager) not installed

**Solution**:
```bash
# Install OPAM
curl -fsSL https://raw.githubusercontent.com/ocaml/opam/master/shell/install.sh | sh

# Initialize OPAM
opam init

# Load environment
eval $(opam env)
```

---

### Problem: `uv` command not found
**Symptom**: Running `uv sync` fails with "command not found"

**Cause**: UV (Python package manager) not installed

**Solution**:
```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH (add to ~/.bashrc or ~/.zshrc for persistence)
export PATH="$HOME/.local/bin:$PATH"
```

---

### Problem: Dependency conflicts during `opam install`
**Symptom**: `opam install . --deps-only` fails with version conflicts

**Cause**: Incompatible package versions

**Solution**:
```bash
# Update OPAM repository
opam update

# Upgrade packages
opam upgrade

# Try installation again
opam install . --deps-only --yes
```

---

### Problem: Build fails with "Library owl not found"
**Symptom**: `dune build` fails complaining about missing owl library

**Cause**: OCaml dependencies not installed

**Solution**:
```bash
# Install all OCaml dependencies
cd pricing/regime_downside/ocaml
opam install . --deps-only --with-test --yes

# Verify owl is installed
opam list | grep owl
```

---

## Runtime Errors

### Problem: "No returns data found for ticker X"
**Symptom**: Optimization fails immediately with missing data error

**Cause**: Historical returns CSV files not fetched

**Solution**:
```bash
# Fetch returns data for all tickers (from project root: atemoya/)
uv run pricing/regime_downside/python/fetch/fetch_assets.py AAPL,GOOGL,MSFT,TSLA,AMZN

# Fetch benchmark (S&P 500) returns
uv run pricing/regime_downside/python/fetch/fetch_benchmark.py
```

**Prevention**: Always run data fetch step before optimization.

---

### Problem: "Optimization infeasible" or "LP solver failed"
**Symptom**: CVXPY solver returns status "infeasible" or "unbounded"

**Cause**: Constraints are too restrictive or conflicting

**Solution**:
1. **Relax LPM1 penalty** (`λ₁_lpm1`):
   ```json
   {
     "lambda_lpm1": 1.0  // Try reducing from 5.0 to 1.0
   }
   ```

2. **Relax CVaR penalty** (`λ₂_cvar`):
   ```json
   {
     "lambda_cvar": 0.1  // Try reducing from 0.5 to 0.1
   }
   ```

3. **Increase beta tolerance**:
   ```json
   {
     "beta_target": 1.0,
     "beta_tolerance": 0.3  // Increase from 0.15 to 0.30
   }
   ```

4. **Reduce turnover penalty**:
   ```json
   {
     "lambda_turnover": 0.01  // Reduce from 0.1
   }
   ```

**Diagnostic**: Run frictionless optimization first (set `lambda_turnover` to 0) to verify problem feasibility.

---

### Problem: Optimization returns all-cash portfolio
**Symptom**: Portfolio weights are 100% cash, 0% equities

**Cause**: Risk penalties are too high relative to expected returns

**Solution**:
1. **Check if assets have negative expected returns**:
   - View mean returns in output CSV
   - If all returns are negative, consider longer lookback period

2. **Reduce risk penalties**:
   ```json
   {
     "lambda_lpm1": 1.0,   // Reduce from 5.0
     "lambda_cvar": 0.05   // Reduce from 0.5
   }
   ```

3. **Lower LPM1 threshold**:
   ```json
   {
     "lpm1_threshold": -0.02  // Lower from -0.01 (less strict)
   }
   ```

4. **Check regime detection**:
   - High-stress regime causes aggressive beta compression
   - View `realized_vol` in logs to verify regime

**Diagnosis**: If frictionless optimization also returns all-cash, problem is with risk/return trade-off, not turnover.

---

### Problem: Turnover exceeds target despite penalty
**Symptom**: Actual turnover is 50% when target is 20%

**Cause**: Regime shift or large market move requires rebalancing

**Solution**:
1. **Increase turnover penalty**:
   ```json
   {
     "lambda_turnover": 0.5  // Increase from 0.1
   }
   ```

2. **Use wider rebalancing bands**:
   ```json
   {
     "rebalance_threshold": 0.15  // Increase from 0.05 (rebalance less frequently)
   }
   ```

3. **Check if regime shifted**:
   - View `regime_weight` in logs
   - Stress regime (weight > 0.5) triggers defensive positioning
   - Consider if large turnover is appropriate response

**Note**: High turnover during regime shifts is by design. The optimizer prioritizes downside protection over turnover minimization.

---

## Data Quality Issues

### Problem: "Insufficient data for volatility calculation"
**Symptom**: Regime detection fails with insufficient data error

**Cause**: Less than 60 days of historical data

**Solution**:
```bash
# Fetch longer history (from project root: atemoya/)
uv run pricing/regime_downside/python/fetch/fetch_assets.py AAPL,GOOGL
```

**Requirement**: Regime detection requires at least 60 days for rolling volatility calculation.

---

### Problem: Returns data has gaps or missing days
**Symptom**: Optimization works but results seem unstable

**Cause**: Missing trading days or data quality issues

**Solution**:
1. **Re-fetch data** from clean source:
   ```bash
   rm data/*_returns.csv  # Remove old data
   uv run python fetch/fetch_assets.py --tickers AAPL  # Re-fetch
   ```

2. **Check data/log** for warnings about missing dates

3. **Use fill-forward** for minor gaps (already handled by yfinance)

**Prevention**: Use reputable data sources (yfinance uses Yahoo Finance, generally reliable).

---

### Problem: Extreme outliers in returns data
**Symptom**: Single day has 500% return

**Cause**: Stock split, dividend, or data error

**Solution**:
1. **Manually inspect** `data/TICKER_returns.csv`

2. **Remove outlier days** or **adjust for splits**:
   ```python
   # In Python, manually clean data
   import pandas as pd
   df = pd.read_csv('data/AAPL_returns.csv')
   df = df[df['return'].abs() < 0.30]  # Remove |return| > 30%
   df.to_csv('data/AAPL_returns.csv', index=False)
   ```

3. **Use adjusted close** (already default in yfinance)

**Note**: yfinance uses adjusted close by default, which handles splits/dividends. Extreme outliers are rare.

---

## Output Interpretation

### Problem: "Why did my allocation change so much?"
**Symptom**: Portfolio shifted from 60% equities to 20% equities

**Cause**: Likely regime shift from calm → stress

**Diagnosis**:
1. Check `regime_weight` in logs:
   - `regime_weight < 0.2`: Calm regime (low compression)
   - `regime_weight > 0.8`: Stress regime (high compression)

2. Check `realized_vol`:
   - Vol > `stress_vol_threshold` (default 20%) triggers regime shift

3. Check `compressed_betas`:
   - Stress regime compresses betas toward cash (0.0)

**Interpretation**: High regime shift + compressed betas → defensive allocation

---

### Problem: "Frictionless and constrained portfolios very different"
**Symptom**: Frictionless: 80% AAPL. Constrained: 20% AAPL.

**Cause**: This is the gap identified in UNDERSTANDING_THE_GAP.md

**Solution**: This is expected behavior, not a bug.

1. **Frictionless** shows pure risk/return trade-off
2. **Constrained** adds:
   - Turnover costs (realistic)
   - Transaction limits (prevents churn)

**Interpretation**:
- Large gap → high turnover costs prevent optimal positioning
- Small gap → current portfolio close to optimal
- Use constrained portfolio for actual trading decisions

---

### Problem: "Beta target not achieved"
**Symptom**: Target beta = 1.0, actual = 0.85

**Cause**: Soft constraint with tolerance, not hard constraint

**Solution**:
1. **Check if within tolerance**:
   ```
   |actual_beta - target_beta| ≤ beta_tolerance
   ```
   Default tolerance: ±0.15

2. **Tighten tolerance** if needed:
   ```json
   {
     "beta_tolerance": 0.05  // Stricter ±5% instead of ±15%
   }
   ```

3. **Check log for beta penalty**:
   - High penalty → optimizer struggling with beta constraint
   - May need to relax other constraints

**Note**: In stress regime, beta compression overrides target. Actual beta may be < target to protect downside.

---

## Performance Issues

### Problem: Optimization takes too long (>30 seconds)
**Symptom**: `solve_lp.py` runs for minutes

**Cause**: Large number of assets or complex constraints

**Solution**:
1. **Reduce number of assets**:
   - Optimize over 10-20 assets max
   - Pre-screen universe before optimization

2. **Use faster solver**:
   ```python
   # In solve_lp.py, try different CVXPY solver
   prob.solve(solver=cp.ECOS)  # Instead of default
   ```

3. **Simplify constraints**:
   - Remove sector constraints if not needed
   - Use wider tolerances

**Benchmark**: 10 assets should solve in <5 seconds. 50 assets may take 30+ seconds.

---

### Problem: High memory usage
**Symptom**: Python process uses >4GB RAM

**Cause**: Large historical data or many simulations

**Solution**:
1. **Reduce lookback period**:
   ```bash
   # Fetch 1 year instead of 5 years
   --lookback-years 1
   ```

2. **Limit data in memory**:
   - Process tickers sequentially instead of batch
   - Clear cache after each run

**Benchmark**: 20 assets × 3 years ≈ 500MB. Should be manageable on modern systems.

---

## Debugging Tips

### Enable verbose logging
```bash
# In OCaml code, logs are written to log/ directory automatically
# View latest log
tail -f pricing/regime_downside/log/latest.log
```

### Check intermediate outputs
```bash
# LP problem specification (saved to /tmp/)
cat /tmp/lp_problem.json

# Solver solution output
cat /tmp/lp_solution.json
```

### Verify data integrity
```bash
# Check returns data has expected structure
head data/AAPL_returns.csv
# Should have: date, return columns

# Check for NaN or inf
grep -i "nan\|inf" data/*.csv
```

### Test with minimal example
```bash
# Run with just 2 assets (from project root: atemoya/)
uv run pricing/regime_downside/python/fetch/fetch_assets.py AAPL,GOOGL

# Run optimization with minimal backtest
opam exec -- dune exec regime_downside -- -tickers AAPL,GOOGL -start 500 -lookback 252
```

---

## Common Warnings (Not Errors)

### "Realized volatility below calm threshold"
**Meaning**: Market is very calm (low vol)

**Action**: None. Regime weight will be low (calm regime dominant).

---

### "Beta compression applied"
**Meaning**: Stress regime detected, compressing risky asset betas

**Action**: None. This is by design for downside protection.

---

### "Turnover exceeds rebalance threshold"
**Meaning**: Proposed changes are large enough to trigger rebalancing

**Action**: None. Optimizer will apply turnover penalty.

---

### "Using default parameters"
**Meaning**: `params.json` not found, using hardcoded defaults

**Action**: Create `data/params.json` for custom parameters:
```json
{
  "lambda_lpm1": 5.0,
  "lambda_cvar": 0.5,
  "lambda_turnover": 0.1,
  "lpm1_threshold": -0.01,
  "beta_target": 1.0,
  "beta_tolerance": 0.15,
  "calm_vol_threshold": 0.10,
  "stress_vol_threshold": 0.20,
  "vol_lookback_days": 60
}
```

---

## Getting Help

If issues persist:

1. **Check logs** in `pricing/regime_downside/log/`
2. **Verify data** in `pricing/regime_downside/data/`
3. **Review parameters** in `data/params.json`
4. **Consult documentation**:
   - `README.md` - Overview and usage
   - `HOW_THE_OPTIMIZER_WORKS.md` - Technical details
   - `UNDERSTANDING_THE_GAP.md` - Interpretation guide
   - `QUICKSTART.md` - Step-by-step setup

5. **File an issue** at GitHub repository with:
   - Error message
   - Relevant log excerpt
   - Parameter configuration
   - Data characteristics (# tickers, date range)

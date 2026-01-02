# Troubleshooting Guide: DCF Deterministic Valuation

This guide helps resolve common issues when using the deterministic discounted cash flow (DCF) valuation model.

---

## Installation Issues

### Problem: `opam` or `uv` not found
**Solution**: See [Regime Downside TROUBLESHOOTING.md](../../pricing/regime_downside/TROUBLESHOOTING.md#installation-issues) - same installation steps apply.

---

### Problem: Build fails with "Library yojson not found"
**Symptom**: `dune build` fails complaining about missing yojson

**Cause**: OCaml JSON library not installed

**Solution**:
```bash
cd valuation/dcf_deterministic/ocaml
opam install . --deps-only --with-test --yes

# Verify installation
opam list | grep yojson
```

---

## Runtime Errors

### Problem: "Financial data not found for ticker X"
**Symptom**: Valuation fails immediately with missing data error

**Cause**: Financial data not fetched from API

**Solution**:
```bash
# Fetch financial data for ticker (from project root: atemoya/)
uv run valuation/dcf_deterministic/python/fetch_financials.py --ticker AAPL

# Output will be in /tmp/dcf_market_data_AAPL.json and /tmp/dcf_financial_data_AAPL.json
```

**Note**: Data is fetched to `/tmp/` directory with 1-day cache to avoid rate limits.

---

### Problem: "Risk-free rate not found for country X"
**Symptom**: Valuation fails with missing RFR error

**Cause**: Country not in `data/risk_free_rates.json` configuration

**Solution**:
1. **Check supported countries**:
   ```bash
   cat data/risk_free_rates.json
   ```

2. **Add missing country** (edit `data/risk_free_rates.json`):
   ```json
   {
     "USA": [
       {"duration": 7, "rate": 0.045},
       {"duration": 10, "rate": 0.048}
     ],
     "GBR": [  // Add new country
       {"duration": 7, "rate": 0.040},
       {"duration": 10, "rate": 0.043}
     ]
   }
   ```

3. **Use default country** as fallback (modify Python fetcher to map to USA)

---

### Problem: "Industry beta not found for industry X"
**Symptom**: Cost of capital calculation fails

**Cause**: Industry not in `data/industry_betas.json`

**Solution**:
1. **Check industry name** in error message

2. **Add industry beta** (edit `data/industry_betas.json`):
   ```json
   {
     "Technology": 1.15,
     "Healthcare": 0.95,
     "Your Industry": 1.00  // Add with appropriate unlevered beta
   }
   ```

**Source**: Use Damodaran's industry betas: http://pages.stern.nyu.edu/~adamodar/

**Fallback**: Use market beta of 1.0 for unknown industries.

---

### Problem: "IVPS is negative"
**Symptom**: Intrinsic value per share is negative

**Cause**: Several possibilities:
1. **Negative cash flows** - Company is burning cash
2. **Debt > Enterprise Value** - Highly leveraged distressed company
3. **Extreme growth rate** - Very high discount rate or negative growth

**Diagnosis**:
```bash
# Check log file for details
cat valuation/dcf_deterministic/log/dcf_TICKER_*.log

# Look for:
# - FCFE/FCFF values (negative?)
# - Cost of capital (>30%? unreasonably high?)
# - Growth rates (negative? clamped?)
```

**Interpretation**:
- **FCFE < 0, FCFF > 0**: High leverage, equity may be worthless
- **Both < 0**: Company destroying value, avoid
- **IVPS slightly negative**: Debt slightly exceeds firm value

**Action**: If fundamentally distressed, negative IVPS is correct signal to avoid.

---

### Problem: "Solver failed to converge" (implied growth)
**Symptom**: Newton-Raphson solver fails to find implied growth rate

**Cause**:
1. **Market price too high** - Implies impossible growth rate (>100%)
2. **Market price too low** - Implies extreme decline
3. **Numerical instability** - Edge case in solver

**Diagnosis**:
```bash
# Check log for:
# - "Solver exceeded max iterations"
# - "Bisection fallback failed"
```

**Solution**: Widen growth rate bounds in `data/params.json`:
```json
{
  "growth_clamp_lower": -0.50,  // Allow up to -50% decline
  "growth_clamp_upper": 0.50    // Allow up to +50% growth
}
```

**Interpretation**: If solver still fails, market price implies growth outside realistic bounds. Signal: `Unknown` or `SpeculativeExecutionRisk`.

---

### Problem: "Growth rate clamped" warning
**Symptom**: Log shows "FCFE growth rate clamped to X%"

**Cause**: Calculated growth rate (ROE × retention) exceeds bounds

**Diagnosis**:
- **Clamped to upper** (e.g., 15%): Company has very high ROE and low payout → aggressive growth
- **Clamped to lower** (e.g., 0%): Company has negative ROE or high payout → declining

**Solution**:
1. **Expected behavior** - Clamping prevents unrealistic perpetual growth
2. **Adjust bounds** if needed (see above)

**Interpretation**:
- Clamping suggests using DCF **probabilistic** model for better uncertainty quantification
- Deterministic DCF is sensitive to growth assumptions

---

## Data Quality Issues

### Problem: "Book value of equity is zero or negative"
**Symptom**: ROE calculation fails or is infinite

**Cause**: Company has negative equity (liabilities > assets)

**Diagnosis**: Check balance sheet - is company insolvent?

**Solution**:
1. **Distressed company**: Avoid valuation, or use liquidation value instead of DCF
2. **Data error**: Re-fetch financial data
3. **Growth company**: Use FCFF method (avoids equity book value)

**Workaround**: Rely on FCFF valuation, which uses invested capital instead of equity book value.

---

### Problem: "Interest expense is zero"
**Symptom**: Cost of borrowing is infinite or undefined

**Cause**: Company has no debt or data quality issue

**Solution**:
1. **Check debt level**: If MVB (market value of debt) = 0, company is debt-free
2. **Default cost of borrowing**: Use risk-free rate as proxy
3. **Re-fetch data**: May be temporary API issue

**Impact**: Low impact if company is primarily equity-financed. WACC ≈ CE.

---

### Problem: "CapEx or depreciation is zero"
**Symptom**: FCFF calculation yields unexpected results

**Cause**:
1. **Financial company** (banks don't have significant CapEx)
2. **Data quality** issue
3. **Steady-state** assumption (CapEx = Depreciation)

**Solution**:
1. **For banks**: Ensure `is_bank` flag is set (uses PPNR-based valuation)
2. **For industrials**: Verify data via financial statements
3. **Assumption**: CapEx = Depreciation for mature companies (acceptable)

---

## Output Interpretation

### Problem: "FCFE and FCFF valuations very different"
**Symptom**: FCFE IVPS = $50, FCFF IVPS = $100

**Cause**:
1. **Leverage effect**: High debt magnifies differences
2. **Different growth rates**: ROE ≠ ROIC due to capital structure
3. **Interest expense**: FCFE deducts interest, FCFF does not

**Diagnosis**:
```
If FCFE < FCFF:
- High debt burden
- Interest expense reducing equity cash flow
- Signal: CautionLong or CautionLeverage

If FCFE > FCFF:
- Negative net debt (more cash than debt)
- Or tax shields benefiting equity holders
- Signal: BuyEquityUpside
```

**Interpretation**: See `INTERPRETATION.md` for detailed guidance on FCFE vs FCFF disagreement.

---

### Problem: "Investment signal is 'Hold' but price seems low"
**Symptom**: Market price = $80, IVPS = $85, but signal is Hold

**Cause**: Margin of safety within tolerance (default ±5%)

**Calculation**:
```
MoS = (IVPS - Price) / Price = (85 - 80) / 80 = 6.25%

Since MoS < tolerance (typically 10%), classified as FairlyValued → Hold
```

**Solution**: Adjust tolerance in signal classification logic if needed.

**Interpretation**: "Hold" means fairly valued. Not overvalued, not undervalued. Consider other factors (momentum, quality, etc.).

---

### Problem: "Terminal value dominates (>80% of IVPS)"
**Symptom**: Log shows "Terminal value contributes 85% to total value"

**Cause**: **This is normal for DCF models**

**Explanation**:
- DCF assumes perpetual cash flows
- Most value comes from years 6+ (terminal value)
- Explicit forecast period (years 1-5) contributes less

**Implication**:
- Valuation is **very sensitive** to terminal growth rate
- Use **probabilistic DCF** for uncertainty quantification
- Stress-test with ±1% terminal growth changes

**Not a bug**: This is fundamental to DCF methodology.

---

### Problem: "Cost of equity seems too high (>20%)"
**Symptom**: CE = 25%, seems unrealistic

**Cause**:
1. **High leveraged beta** (β_L > 2.0 for highly leveraged firms)
2. **High equity risk premium** (emerging markets: ERP = 10%)
3. **Industry beta misconfiguration**

**Diagnosis**:
```bash
# Check log for cost of capital breakdown
grep "Cost of Equity" log/dcf_TICKER_*.log
grep "Leveraged Beta" log/dcf_TICKER_*.log
```

**Solution**:
1. **Verify inputs**:
   - RFR: 3-5% (developed), 6-10% (emerging)
   - ERP: 5-7% (developed), 8-12% (emerging)
   - Unlevered beta: 0.8-1.5 for most industries

2. **Check debt/equity ratio**: Very high leverage → high β_L → high CE

**Interpretation**: High CE is appropriate for risky companies. Leads to lower valuation (correct).

---

### Problem: "Margin of safety is very negative (-50%)"
**Symptom**: IVPS = $50, Market Price = $100, MoS = -50%

**Cause**: Market values company at 2× DCF valuation

**Interpretation**:
1. **DCF is conservative**: May be missing intangibles (brand value, network effects)
2. **Market is optimistic**: Pricing in high growth not captured by ROE/ROIC
3. **DCF is correct**: Market may be overvalued (bubble, momentum, hype)

**Action**:
- Compare to peers (P/E, P/B, EV/EBITDA)
- Use probabilistic DCF for range of outcomes
- Consider qualitative factors (moat, management, market position)

**Signal**: `Avoid` or `SpeculativeExecutionRisk` - proceed with caution.

---

## Visualization Issues

### Problem: Visualization script fails with "No log files found"
**Symptom**: `plot_results.py` exits with error

**Cause**: DCF valuation not run yet

**Solution**:
```bash
# Run valuation first (from project root: atemoya/)
opam exec -- dune exec dcf_deterministic -- -ticker AAPL

# Then generate visualizations
uv run valuation/dcf_deterministic/python/viz/plot_results.py --ticker AAPL
```

---

### Problem: Sensitivity analysis plots show flat lines
**Symptom**: Changing growth rate doesn't affect valuation in plot

**Cause**: Sensitivity analysis uses **linear approximation**, not actual re-valuation

**Note**: This is a simplification for speed. For actual sensitivity, re-run valuation with different parameters.

**Enhancement**: Planned for scenario analysis feature (bull/base/bear cases with actual re-valuation).

---

### Problem: Waterfall chart has overlapping labels
**Symptom**: Value labels overlap and are unreadable

**Cause**: Extreme value ranges (e.g., IVPS = $5, Price = $500)

**Solution**: Adjust figure size in `plot_results.py`:
```python
fig, ax = plt.subplots(figsize=(16, 9))  # Increase from (12, 7)
```

---

## Performance Issues

### Problem: Valuation takes too long (>10 seconds)
**Symptom**: Single ticker valuation exceeds 10 seconds

**Cause**:
1. **Solver iterations** (implied growth calculation)
2. **Large projection horizon** (100 years instead of 10)

**Solution**:
1. **Reduce projection years** in `data/params.json`:
   ```json
   {
     "projection_years": 5  // Reduce from 10
   }
   ```

2. **Check solver convergence**: May be stuck in Newton-Raphson loop

**Benchmark**: Single ticker should complete in <2 seconds on modern hardware.

---

### Problem: Memory usage high when batch-processing
**Symptom**: RAM usage >2GB for 10 tickers

**Cause**: All results held in memory before writing

**Solution**:
1. **Process sequentially** instead of batch
2. **Write results incrementally** to CSV
3. **Clear cache** between tickers

---

## Debugging Tips

### View detailed logs
```bash
# Latest valuation log
ls -t valuation/dcf_deterministic/log/dcf_*.log | head -1 | xargs cat

# Search for specific ticker
grep -l "AAPL" log/*.log | head -1 | xargs cat
```

### Verify configuration files
```bash
# Check all config files exist
ls data/*.json

# Validate JSON syntax
for f in data/*.json; do
    echo "Checking $f"
    python3 -m json.tool $f > /dev/null && echo "✓ Valid" || echo "✗ Invalid"
done
```

### Test with known-good ticker
```bash
# Use large-cap stock with complete data (from project root: atemoya/)
opam exec -- dune exec dcf_deterministic -- -ticker AAPL

# Avoid:
# - Small caps (incomplete data)
# - Recent IPOs (<3 years history)
# - Foreign stocks (currency/country issues)
```

### Compare to market consensus
```bash
# Check if DCF valuation is in ballpark of analyst estimates
# Example: AAPL market price $150, analyst target $160
# If DCF gives $50 or $500, investigate assumptions
```

---

## Common Warnings (Not Errors)

### "Using interpolated risk-free rate"
**Meaning**: Exact duration not found, interpolating between available tenors

**Action**: None. Interpolation is standard practice.

---

### "FCFE growth clamped to 15%"
**Meaning**: Calculated growth exceeds upper bound, clamped for realism

**Action**: None. Prevents unrealistic perpetual growth assumptions.

---

### "Negative working capital change"
**Meaning**: ΔWC < 0, which increases cash flow

**Action**: None. Normal for companies releasing working capital.

---

### "Tax rate not found, using default"
**Meaning**: Country tax rate not in config, using 21% (US rate)

**Action**: Add country to `data/tax_rates.json` for accuracy.

---

## Getting Help

If issues persist:

1. **Check logs** in `valuation/dcf_deterministic/log/`
2. **Verify config** files in `data/*.json`
3. **Validate data** in `/tmp/dcf_*_TICKER.json`
4. **Consult documentation**:
   - `README.md` - Overview and methodology
   - `INTERPRETATION.md` - How to interpret results
   - `QUICKSTART_INTEGRATION.md` - Quickstart menu usage

5. **File an issue** with:
   - Ticker symbol
   - Error message
   - Relevant log excerpt
   - Configuration files (params.json, etc.)

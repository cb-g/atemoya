# Troubleshooting Guide

Common issues and solutions for the Options Hedging model.

---

## Data Fetching Issues

### Error: "No options data available for ticker"

**Problem:** Ticker may not have listed options

**Solutions:**
1. Verify ticker has options: Check on broker platform or Yahoo Finance
2. Try major stocks with active options: `AAPL`, `MSFT`, `SPY`, `QQQ`, `GOOGL`, `TSLA`
3. Check yfinance version:
   - **Docker:** `docker compose exec -w /app atemoya /bin/bash -c "uv run -c 'import yfinance; print(yfinance.__version__)'"`
   - **Native:** `uv run -c 'import yfinance; print(yfinance.__version__)'`
4. Update yfinance if needed:
   - **Docker:** `docker compose exec -w /app atemoya /bin/bash -c "uv sync"`
   - **Native:** `uv sync`

### Error: "Option chain incomplete/missing expiries"

**Problem:** Some expiries may be illiquid or data temporarily unavailable

**Solutions:**
1. Filter by expiry range: Use `--min-days 14 --max-days 365` to skip very short/long dated
2. Retry fetch after a few minutes (API rate limiting)
3. Use different time of day (market hours vs after-hours may differ)

### Error: "Underlying data file not found"

**Problem:** Haven't fetched underlying data yet

**Solution:**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/fetch/fetch_underlying.py --ticker YOUR_TICKER"
```

**Native:**
```bash
uv run pricing/options_hedging/python/fetch/fetch_underlying.py --ticker YOUR_TICKER
```

---

## Calibration Issues

### Error: "SVI calibration failed for all expiries"

**Causes:**
1. Market quotes are stale (wide bid-ask spreads)
2. Not enough valid quotes per expiry
3. Extreme volatility skew

**Solutions:**

**Check data quality:**
```bash
# View option chain
head -20 pricing/options_hedging/data/AAPL_options.csv

# Filter for quality
# Should have: bid > 0, ask > bid, volume > 0, IV > 0
```

**Reduce strike range:**
```python
# Edit fetch_options.py to filter strikes closer to ATM
df = df[(df['strike'] >= 0.85 * spot) & (df['strike'] <= 1.15 * spot)]
```

**Try SABR instead:**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker AAPL --model sabr"
```

**Native:**
```bash
uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker AAPL --model sabr
```

### Error: "SVI no-arbitrage violation"

**Problem:** Calibrated parameters violate butterfly arbitrage condition: `b/σ >= |ρ|`

**Debug:**
```python
# Check calibrated parameters
import json
with open('pricing/options_hedging/data/AAPL_vol_surface.json') as f:
    surf = json.load(f)

for p in surf['params']:
    ratio = p['b'] / p['sigma']
    print(f"T={p['expiry']:.2f}: b/σ={ratio:.3f}, |ρ|={abs(p['rho']):.3f}")
    # Should have: ratio >= |rho|
```

**Solutions:**
1. Add tighter bounds in calibration (edit `calibrate_vol_surface.py`)
2. Use fewer strikes (remove far OTM)
3. Weight ATM quotes more heavily

### Warning: "SABR parameters out of bounds"

**Problem:** `β` not in [0,1], or `ρ` not in [-1,1]

**Solution:**
Check bounds in differential evolution:
```python
# In calibrate_sabr_single_expiry()
bounds = [
    (0.01, 2.0),    # alpha > 0
    (0.0, 1.0),     # 0 <= beta <= 1  <- CHECK THIS
    (-0.99, 0.99),  # -1 < rho < 1
    (0.01, 2.0)     # nu > 0
]
```

---

## Pricing Issues

### Error: "BS price negative or > spot"

**Problem:** Invalid inputs to Black-Scholes

**Check:**
```bash
# In OCaml, add debug print before pricing
Printf.printf "S=%.2f K=%.2f T=%.4f r=%.4f q=%.4f σ=%.4f\n"
  spot strike expiry rate dividend volatility;
```

**Common causes:**
- `σ <= 0` (zero/negative volatility)
- `T <= 0` (expired option)
- `S <= 0` (invalid spot)

**Solution:** Add validation in data pipeline

### Error: "Monte Carlo prices unstable"

**Problem:** High variance in MC estimates

**Solutions:**

**Increase sample size:**
```bash
# In main.ml, increase paths
let config = {
  num_mc_paths = 10000;  (* was 1000 *)
  ...
}
```

**Increase time steps:**
```bash
# In monte_carlo.ml
let num_steps = 100  (* was 50 *)
```

**Use antithetic variates:**
```ocaml
(* In simulate_price_paths *)
let z = normal_random () in
let z_anti = -. z in
(* Generate two paths per random draw *)
```

### Numerical precision: "NaN in Greeks"

**Problem:** Division by zero or sqrt(negative)

**Debug:**
```ocaml
(* Add guards *)
if expiry <= 0.0 then
  failwith "expiry must be positive";
if volatility <= 0.0 then
  failwith "volatility must be positive";
```

---

## Optimization Issues

### Error: "No Pareto frontier generated"

**Problem:** All strategies violate constraints

**Solutions:**

**Relax constraints:**

**Docker:**
```bash
# Remove or increase max_cost
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec options_hedging -- \
  -ticker AAPL \
  -position 100 \
  -expiry 90"
  # (no -max-cost flag)
```

**Native:**
```bash
# Remove or increase max_cost
eval $(opam env) && dune exec options_hedging -- \
  -ticker AAPL \
  -position 100 \
  -expiry 90
  # (no -max-cost flag)
```

**Expand strike grid:**
```bash
# In main.ml, increase strikes
let num_strikes = 30  (* was 20 *)
```

**Use multiple expiries:**
```bash
# Try 30, 60, 90 days
let expiries = [| 30.0/.365.0; 60.0/.365.0; 90.0/.365.0 |]
```

### Error: "All strategies have similar cost/protection"

**Problem:** Volatility surface is too flat, or strike range too narrow

**Solutions:**
1. Check vol surface:
   - **Docker:** `docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/viz/plot_vol_surface.py --ticker AAPL"`
   - **Native:** `uv run pricing/options_hedging/python/viz/plot_vol_surface.py --ticker AAPL`
2. Expand moneyness range: 70%-130% instead of 80%-120%
3. Try different expiries
4. Use different strategy types (protective put vs collar have different profiles)

### Warning: "Recommended strategy is None"

**Problem:** Pareto frontier is empty

**Solution:** See "No Pareto frontier generated" above

---

## Greeks Issues

### Error: "Delta not in valid range"

**Problem:** Call delta not in [0,1] or put delta not in [-1,0]

**Debug:**
```ocaml
let delta = Black_scholes.delta option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility in

if option_type = Call && (delta < 0.0 || delta > 1.0) then
  Printf.eprintf "Invalid call delta: %.6f\n" delta;

if option_type = Put && (delta < -1.0 || delta > 0.0) then
  Printf.eprintf "Invalid put delta: %.6f\n" delta;
```

**Common causes:**
- `expiry <= 0` (expired option)
- `volatility <= 0` (invalid vol)

**Solution:** Add input validation

### Error: "Gamma negative"

**Problem:** Gamma should always be ≥ 0 for long options

**Check:**
```ocaml
let gamma = Black_scholes.gamma ~spot ~strike ~expiry ~rate ~dividend ~volatility in
assert (gamma >= 0.0);
```

**Cause:** Usually sign error in formula

**Formula check:**
```
Γ = e^(-qT) · n(d₁) / (S·σ·√T)

All terms should be positive
```

### Warning: "Portfolio not delta-neutral"

**Not an error**, but informational

**To achieve delta-neutrality:**
1. Add opposite-signed position
2. Adjust number of contracts
3. Use delta-hedging (buy/sell underlying)

---

## Performance Issues

### Problem: "Calibration is slow (> 2 minutes)"

**Solutions:**

**Use fewer strikes:**
```python
# In fetch_options.py, filter to top N liquid strikes
df = df.sort_values('volume', ascending=False).head(100)
```

**Reduce expiries:**
```python
# In calibrate_vol_surface.py, skip illiquid expiries
if len(df_expiry) < 10:  # was 5
    continue
```

**Use faster optimizer:**
```python
# In calibrate_svi_single_expiry()
# Skip differential_evolution, go straight to L-BFGS-B
result = minimize(objective, x0, bounds=bounds, method='L-BFGS-B')
```

### Problem: "Pareto frontier generation is slow (> 5 minutes)"

**Solutions:**

**Reduce Monte Carlo paths:**
```bash
# In main.ml
let config = {
  num_mc_paths = 500;  (* was 1000 *)
  ...
}
```

**Reduce strike grid:**
```bash
let num_strikes = 10  (* was 20 *)
```

**Parallelize (future work):**
```ocaml
(* Use Parmap or Lwt for parallel strategy evaluation *)
```

---

## Visualization Issues

### Error: "ModuleNotFoundError: No module named 'matplotlib'"

**Problem:** Python dependencies not installed

**Solution:**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv sync"
```

**Native:**
```bash
uv sync
```

### Error: "Strategy file not found"

**Problem:** Need to run OCaml hedge analysis first

**Solution:**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec options_hedging -- -ticker AAPL -position 100 -expiry 90"
```

**Native:**
```bash
eval $(opam env) && dune exec options_hedging -- -ticker AAPL -position 100 -expiry 90
```

### Plot looks wrong: "Payoff diagram doesn't show protection"

**Debug checklist:**
1. Check spot price is loaded correctly
2. Verify strategy strikes are parsed correctly
3. Check position size matches
4. Ensure cost is included in P&L plot

**Example fix:**
```python
# In plot_payoffs.py
print(f"Spot: {spot}")
print(f"Strategy: {strategy_type}, {params}")
print(f"Cost: {cost}")
```

### Dark mode issues: "Plot is unreadable"

**Problem:** Color palette conflicts with environment

**Solution:**
Edit color scheme in viz scripts:
```python
# In plot_*.py
COLORS = {
    'bg': '#ffffff',  # White background
    'fg': '#000000',  # Black text
    ...
}
```

---

## Data Quality Issues

### Warning: "Wide bid-ask spreads"

**Impact:** Poor calibration, unreliable prices

**Filter:**
```python
# In fetch_options.py
df = df[(df['ask'] - df['bid']) / df['bid'] < 0.20]  # Max 20% spread
```

### Warning: "Low option volume"

**Impact:** Stale quotes, may not reflect true market

**Filter:**
```python
df = df[df['volume'] > 10]  # Min 10 contracts traded
df = df[df['open_interest'] > 50]  # Min 50 open interest
```

---

## Testing Issues

### Test failure: "Put-call parity violated"

**Tolerance too tight:**
```ocaml
(* In test_options_hedging.ml *)
Alcotest.(check (float 0.10)) "put-call parity" parity_lhs parity_rhs
(* Increase tolerance from 0.01 to 0.10 for discrete dividends *)
```

### Test failure: "SVI no-arbitrage check failed"

**Problem:** Test uses invalid parameters

**Fix:**
```ocaml
(* Ensure b/σ >= |ρ| *)
let valid_params = {
  a = 0.04;
  b = 0.15;      (* Increase b *)
  rho = -0.3;
  m = 0.0;
  sigma = 0.20;  (* Or increase σ *)
}
(* Now: 0.15/0.20 = 0.75 >= 0.3 ✓ *)
```

---

## Common Patterns

### Pattern: "Works for AAPL but not for XYZ"

**Diagnosis:**
1. Check if XYZ has listed options
2. Check liquidity (volume, open interest)
3. Check implied volatility range (extreme values indicate data issues)

### Pattern: "Works in morning but fails in afternoon"

**Diagnosis:**
1. Market data API rate limiting
2. Post-market vs intramarket data differences
3. Add retry logic or cache data

### Pattern: "First run fails, second run succeeds"

**Diagnosis:**
1. Directory creation race condition
2. File locking issues
3. Add `mkdir -p` before writes

---

## Getting Help

**Debug workflow:**
1. Check log files in `pricing/options_hedging/log/`
2. Run with verbose output (add `Printf.printf` debug statements)
3. Verify data files exist and have valid contents
4. Check intermediate outputs (CSV files)

**Minimal reproducible example:**

**Docker:**
```bash
# Fetch smallest test case
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/fetch/fetch_underlying.py --ticker SPY"
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/fetch/fetch_options.py --ticker SPY --min-days 30 --max-days 60"
docker compose exec -w /app atemoya /bin/bash -c "uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker SPY --model svi"

# Run hedge with simple params
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec options_hedging -- -ticker SPY -position 100 -expiry 30"
```

**Native:**
```bash
# Fetch smallest test case
uv run pricing/options_hedging/python/fetch/fetch_underlying.py --ticker SPY
uv run pricing/options_hedging/python/fetch/fetch_options.py --ticker SPY --min-days 30 --max-days 60
uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker SPY --model svi

# Run hedge with simple params
eval $(opam env) && dune exec options_hedging -- -ticker SPY -position 100 -expiry 30
```

**Check versions:**

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && ocaml --version"
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && opam --version"
docker compose exec -w /app atemoya /bin/bash -c "uv --version"
docker compose exec -w /app atemoya /bin/bash -c "uv run --version"
docker compose exec -w /app atemoya /bin/bash -c "uv run -c 'import yfinance; print(yfinance.__version__)'"
```

**Native:**
```bash
eval $(opam env) && ocaml --version
eval $(opam env) && opam --version
uv --version
uv run --version
uv run -c 'import yfinance; print(yfinance.__version__)'
```

---

## FAQ

**Q: Why does calibration sometimes fail?**
A: Market data quality varies. Wide spreads, low volume, or stale quotes can cause issues. Filter for liquid options only.

**Q: Should I use SVI or SABR?**
A: SVI is faster and more stable. Use SABR for more accurate smile dynamics (especially for exotics).

**Q: How accurate are the protection levels?**
A: They're estimates based on Monte Carlo (95th percentile). Real protection depends on execution, transaction costs, and realized volatility.

**Q: Can I use this for production trading?**
A: This is a research/educational model. For production, add: real-time data, transaction costs, bid-ask spread modeling, position limits, risk management.

**Q: Why is Monte Carlo slower than Black-Scholes?**
A: MC simulates thousands of paths. Use BS for European options when possible. MC is needed for American exercise and exotic payoffs.

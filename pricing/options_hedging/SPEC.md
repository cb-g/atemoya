# Options Hedging - Mathematical Specification

Complete formulas and algorithms for the options hedging model.

---

## 1. Black-Scholes-Merton Pricing

### European Call and Put Prices

**Call:**
```
C(S, K, T, r, q, σ) = S·e^(-qT)·N(d₁) - K·e^(-rT)·N(d₂)
```

**Put:**
```
P(S, K, T, r, q, σ) = K·e^(-rT)·N(-d₂) - S·e^(-qT)·N(-d₁)
```

Where:
```
d₁ = [ln(S/K) + (r - q + σ²/2)T] / (σ√T)
d₂ = d₁ - σ√T

S = spot price
K = strike price
T = time to expiry (years)
r = risk-free rate
q = dividend yield
σ = volatility
N(·) = standard normal CDF
```

### Put-Call Parity

```
C - P = S·e^(-qT) - K·e^(-rT)
```

### Standard Normal CDF

Approximation (Abramowitz & Stegun):
```
N(x) = 0.5 · (1 + erf(x/√2))

erf(x) ≈ 1 - (a₁t + a₂t² + a₃t³ + a₄t⁴ + a₅t⁵)·e^(-x²)

where:
  t = 1 / (1 + px)
  p = 0.3275911
  a₁ = 0.254829592
  a₂ = -0.284496736
  a₃ = 1.421413741
  a₄ = -1.453152027
  a₅ = 1.061405429
```

---

## 2. Greeks

### Delta (Δ)

**Call:**
```
Δ_call = e^(-qT)·N(d₁)
```

**Put:**
```
Δ_put = -e^(-qT)·N(-d₁) = e^(-qT)·(N(d₁) - 1)
```

**Interpretation:**
- Call: 0 ≤ Δ ≤ 1
- Put: -1 ≤ Δ ≤ 0
- Hedge ratio for delta-neutral portfolio

### Gamma (Γ)

```
Γ = e^(-qT)·n(d₁) / (S·σ·√T)

where n(·) = standard normal PDF = (1/√(2π))·e^(-x²/2)
```

**Properties:**
- Same for calls and puts
- Always Γ ≥ 0 for long options
- Maximum at ATM
- Measures convexity / delta sensitivity

### Vega (ν)

```
ν = S·e^(-qT)·n(d₁)·√T

(per 1% change in volatility)
```

**Properties:**
- Same for calls and puts
- Always ν ≥ 0 for long options
- Maximum at ATM
- Long-dated options have higher vega

### Theta (Θ)

**Call:**
```
Θ_call = -S·n(d₁)·σ·e^(-qT)/(2√T) - r·K·e^(-rT)·N(d₂) + q·S·e^(-qT)·N(d₁)
```

**Put:**
```
Θ_put = -S·n(d₁)·σ·e^(-qT)/(2√T) + r·K·e^(-rT)·N(-d₂) - q·S·e^(-qT)·N(-d₁)
```

**Units:** Per day (divide annual theta by 365)

**Interpretation:**
- Usually Θ < 0 for long options (time decay)
- Short options benefit from time decay (Θ > 0)

### Rho (ρ)

**Call:**
```
ρ_call = K·T·e^(-rT)·N(d₂)
```

**Put:**
```
ρ_put = -K·T·e^(-rT)·N(-d₂)
```

**Units:** Per 1% change in interest rate

---

## 3. SVI Volatility Model

### Total Variance Formula

```
w(k; θ) = a + b·{ρ(k - m) + √[(k - m)² + σ²]}

where:
  k = ln(K/F) = log-moneyness
  θ = (a, b, ρ, m, σ) = SVI parameters
    a = vertical translation (≥ 0)
    b = slope (≥ 0)
    ρ = rotation ∈ [-1, 1]
    m = horizontal translation
    σ = vol of vol (> 0)
```

### Implied Volatility

```
IV(k, T) = √[w(k; θ) / T]
```

### No-Arbitrage Conditions

**Butterfly Arbitrage:**
```
∂²C/∂K² ≥ 0

SVI condition: b/σ ≥ |ρ|
```

**Calendar Arbitrage:**
```
∂w/∂T ≥ 0

Requires: a ≥ 0 (total variance increasing with time)
```

### Calibration

Minimize sum of squared errors:
```
min Σᵢ [w(kᵢ; θ) - w_market(kᵢ)]²

subject to:
  a ≥ 0
  b ≥ 0
  -1 ≤ ρ ≤ 1
  σ > 0
  b/σ ≥ |ρ|  (no arbitrage)
```

Method: Differential evolution (global optimizer) with fallback to L-BFGS-B

---

## 4. SABR Volatility Model

### Implied Volatility (Hagan Approximation)

**ATM (F ≈ K):**
```
σ_SABR(K, F) = α / F^(1-β) · [1 + T·(...corrections...)]
```

**General case:**
```
σ_SABR(K, F) = (α / (FK)^((1-β)/2)) · (z/χ(z)) · [1 + T·(...corrections...)]

where:
  z = (ν/α)·(FK)^((1-β)/2)·ln(F/K)

  χ(z) = ln[(√(1 - 2ρz + z²) + z - ρ) / (1 - ρ)]

  Time corrections:
    (1-β)²·α² / (24·F^(2(1-β)))
    + 0.25·ρ·β·ν·α / F^(1-β)
    + (2 - 3ρ²)·ν² / 24
```

### Parameters

```
α = initial volatility (> 0)
β = CEV exponent ∈ [0, 1]
    β = 0: Normal model
    β = 0.5: Common choice
    β = 1: Lognormal model
ρ = correlation ∈ [-1, 1]
ν = vol of vol (> 0)
```

### Calibration

Same as SVI, minimize squared errors with bounds:
```
0.01 ≤ α ≤ 2.0
0.0 ≤ β ≤ 1.0
-0.99 ≤ ρ ≤ 0.99
0.01 ≤ ν ≤ 2.0
```

---

## 5. Longstaff-Schwartz Algorithm

For pricing American options via Monte Carlo.

### Step 1: Simulate Price Paths

Geometric Brownian Motion:
```
dS = (r - q)S dt + σS dW

Discretized:
S(t+Δt) = S(t)·exp[(r - q - σ²/2)Δt + σ√Δt·Z]

where Z ~ N(0,1)
```

Generate M paths, N time steps:
```
S[i,t] = stock price for path i at time t
```

### Step 2: Initialize Payoffs at Expiry

```
V[i,N] = max(K - S[i,N], 0)  (for put)
V[i,N] = max(S[i,N] - K, 0)  (for call)
```

### Step 3: Backward Induction

For each time step t = N-1, N-2, ..., 1:

1. **Compute exercise value:**
   ```
   h(S[i,t]) = max(K - S[i,t], 0)  (put)
   ```

2. **Identify ITM paths:**
   Find paths where h(S[i,t]) > 0

3. **Regression for continuation value:**
   ```
   C(S) = E[e^(-rΔt)·V[t+1] | S[t]]
        ≈ β₀·L₀(S) + β₁·L₁(S) + β₂·L₂(S) + ...

   where L_n = Laguerre polynomials
   ```

4. **Laguerre polynomials:**
   ```
   L₀(x) = 1
   L₁(x) = 1 - x
   L₂(x) = (2 - 4x + x²) / 2
   L₃(x) = (6 - 18x + 9x² - x³) / 6

   Recurrence:
   L_{n+1}(x) = [(2n+1-x)·L_n(x) - n·L_{n-1}(x)] / (n+1)
   ```

5. **Exercise decision:**
   ```
   If h(S[i,t]) > C(S[i,t]):
       Exercise now: V[i,t] = h(S[i,t])
       V[i,t+1:N] = 0  (no future cash flows)
   Else:
       Don't exercise: V[i,t] = 0
       Keep V[i,t+1]
   ```

### Step 4: Average Discounted Cash Flows

```
Option_Price = (1/M) Σᵢ e^(-r·T_exercise[i])·V[i,T_exercise[i]]
```

---

## 6. Hedge Strategy Payoffs

### Protective Put

```
Payoff = position_size · max(S_T, K_put)

where:
  S_T = spot at expiry
  K_put = put strike
```

**Cost:** Put premium

**Protection:** Downside floored at K_put

### Collar

```
Payoff = position_size · clamp(S_T, K_put, K_call)

where:
  clamp(x, a, b) = max(a, min(x, b))
  K_put < K_call
```

**Cost:** Put premium - Call premium (can be ≤ 0)

**Protection:** Bounded between K_put and K_call

### Vertical Put Spread

```
Payoff = position_size · S_T + position_size · [Put_long - Put_short]

where:
  Put_long = max(0, K_long - S_T)
  Put_short = max(0, K_short - S_T)
  K_long > K_short
```

**Cost:** Premium(K_long) - Premium(K_short)

**Protection:** Limited to K_long - K_short

### Covered Call

```
Payoff = position_size · S_T - position_size · max(0, S_T - K_call)
       = position_size · min(S_T, K_call)
```

**Cost:** Negative (income from call premium)

**Protection:** None (upside capped)

---

## 7. Multi-Objective Optimization

### Pareto Efficiency

Point (c*, p*) is Pareto efficient if there exists no point (c, p) such that:
```
c ≤ c*  AND  p ≥ p*

with at least one strict inequality
```

**Interpretation:** Cannot improve one objective without worsening the other

### Pareto Dominance

Point A dominates point B if:
```
cost(A) ≤ cost(B)  AND  protection(A) ≥ protection(B)

with at least one strict inequality
```

### Frontier Generation Algorithm

```
1. Generate candidate strategies:
   For each expiry T:
     For each strike K in grid:
       Generate: ProtectivePut(K), CoveredCall(K)
       For each strike K' in grid:
         If K' > K:
           Generate: Collar(K, K')
         If K' < K:
           Generate: VerticalSpread(K, K')

2. Price each strategy:
   cost = option_premium × contracts × 100
   protection = 5th percentile of payoff distribution (MC)

3. Filter for Pareto efficiency:
   Keep only non-dominated points

4. Sort by cost (ascending)

5. Return frontier
```

### Recommendation Selection

**Balanced (default):**
```
Normalize cost and protection to [0, 1]:

norm_cost = (cost - cost_min) / (cost_max - cost_min)
norm_prot = (prot - prot_min) / (prot_max - prot_min)

Score = norm_prot - norm_cost

Pick strategy with max(Score)
```

**Min Cost:**
```
Pick min(cost)
```

**Max Protection:**
```
Pick max(protection)
```

---

## 8. Greeks for Portfolio

### Portfolio Greeks

Sum of individual Greeks weighted by contracts:
```
Δ_portfolio = Σᵢ contracts[i] · Δ[i]
Γ_portfolio = Σᵢ contracts[i] · Γ[i]
ν_portfolio = Σᵢ contracts[i] · ν[i]
Θ_portfolio = Σᵢ contracts[i] · Θ[i]
ρ_portfolio = Σᵢ contracts[i] · ρ[i]
```

### Delta-Neutral Portfolio

Condition:
```
|Δ_portfolio| < ε

typically ε = 0.01
```

Hedge ratio:
```
Shares_to_hedge = -Δ_portfolio / Δ_stock

where Δ_stock = 1.0
```

### Gamma-Neutral Portfolio

```
|Γ_portfolio| < ε

typically ε = 0.001
```

Requires options with different strikes (Γ ≠ constant)

---

## 9. Risk Measures

### Minimum Value

```
Protection = 5th percentile of payoff distribution

Computed via Monte Carlo:
1. Simulate N paths to expiry
2. Compute payoff for each path
3. Sort payoffs ascending
4. Return payoff[0.05 × N]
```

### Value at Risk (VaR)

```
VaR_α = -quantile(P&L distribution, α)

typically α = 0.05 (95% confidence)
```

### Conditional Value at Risk (CVaR)

```
CVaR_α = -E[P&L | P&L < -VaR_α]

Expected loss in worst α% of cases
```

---

## 10. Parameter Bounds and Validation

### Black-Scholes Inputs

```
S > 0       (spot price)
K > 0       (strike)
T > 0       (time to expiry)
r ∈ ℝ       (risk-free rate, can be negative)
q ≥ 0       (dividend yield)
σ > 0       (volatility)
```

### SVI Parameters

```
a ≥ 0
b ≥ 0
-1 ≤ ρ ≤ 1
m ∈ ℝ
σ > 0
b/σ ≥ |ρ|  (no butterfly arbitrage)
```

### SABR Parameters

```
α > 0
0 ≤ β ≤ 1
-1 < ρ < 1
ν > 0
```

### Greeks Bounds

```
Call delta: 0 ≤ Δ ≤ 1
Put delta: -1 ≤ Δ ≤ 0
Gamma: Γ ≥ 0
Vega: ν ≥ 0
```

---

## References

1. **Black & Scholes (1973).** "The Pricing of Options and Corporate Liabilities"
2. **Merton (1973).** "Theory of Rational Option Pricing"
3. **Gatheral (2006).** "The Volatility Surface: A Practitioner's Guide"
4. **Hagan et al. (2002).** "Managing Smile Risk"
5. **Longstaff & Schwartz (2001).** "Valuing American Options by Simulation: A Simple Least-Squares Approach"
6. **Hull (2021).** "Options, Futures, and Other Derivatives" (10th edition)

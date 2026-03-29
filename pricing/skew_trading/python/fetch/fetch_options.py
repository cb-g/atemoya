#!/usr/bin/env python3
"""
Fetch option chain data and calibrate SVI volatility surface.

Downloads:
- Option chains for all available expiries
- Filters valid quotes (volume > 0, reasonable bid-ask spread)

Calibrates:
- SVI volatility surface per expiry

Outputs:
- {TICKER}_vol_surface.json (SVI parameters)
- {TICKER}_option_chain.csv (raw market quotes)
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf
from scipy.optimize import minimize
from scipy.stats import norm

from lib.python.retry import retry_with_backoff
from lib.python.iv import implied_vol_newton_raphson

# Load configuration
CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"


def load_config() -> dict:
    """Load configuration from config.json."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


CONFIG = load_config()


def black_scholes_price(S, K, T, r, sigma, option_type='call'):
    """Black-Scholes option price."""
    if T <= 0:
        if option_type == 'call':
            return max(S - K, 0)
        else:
            return max(K - S, 0)

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == 'call':
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def implied_vol_bisection(option_price, S, K, T, r, option_type='call', tol=1e-5, max_iter=100):
    """Solve for implied volatility using bisection (scalar version)."""
    if T <= 0:
        return None

    # Bisection bounds
    vol_low = 0.01
    vol_high = 3.0

    for _ in range(max_iter):
        vol_mid = (vol_low + vol_high) / 2
        price_mid = black_scholes_price(S, K, T, r, vol_mid, option_type)

        if abs(price_mid - option_price) < tol:
            return vol_mid

        if price_mid < option_price:
            vol_low = vol_mid
        else:
            vol_high = vol_mid

    return None


def black_scholes_vega(S, K, T, r, sigma):
    """Black-Scholes vega (sensitivity to volatility)."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return S * np.sqrt(T) * norm.pdf(d1)


# Re-export for backwards compatibility — implementation now in lib/python/iv.py
implied_vol_newton_raphson_vectorized = implied_vol_newton_raphson


def fetch_option_chain(
    ticker: str,
    min_expiry_days: int | None = None,
    max_expiry_days: int | None = None,
    max_spread: float | None = None,
    min_volume: int | None = None
):
    """
    Fetch option chain for ticker.

    Args:
        ticker: Stock ticker
        min_expiry_days: Minimum days to expiry (default: from config or 7)
        max_expiry_days: Maximum days to expiry (default: from config or 365)
        max_spread: Maximum bid-ask spread as fraction (default: from config or 0.5)
        min_volume: Minimum volume filter (default: from config or 1)

    Returns:
        DataFrame with columns: strike, expiry_date, expiry_years, bid, ask, mid,
                                volume, open_interest, option_type, implied_vol
    """
    # Load defaults from config
    opts_config = CONFIG.get("options", {})
    min_expiry_days = min_expiry_days if min_expiry_days is not None else opts_config.get("min_expiry_days", 7)
    max_expiry_days = max_expiry_days if max_expiry_days is not None else opts_config.get("max_expiry_days", 365)
    max_spread = max_spread if max_spread is not None else opts_config.get("max_bid_ask_spread", 0.5)
    min_volume = min_volume if min_volume is not None else opts_config.get("min_volume", 1)

    print(f"Fetching option chain for {ticker}...")

    stock = yf.Ticker(ticker)
    expirations = retry_with_backoff(lambda: stock.options)

    if not expirations:
        raise ValueError(f"No options data available for {ticker}")

    spot = retry_with_backoff(lambda: stock.history(period='1d'))['Close'].iloc[-1]
    print(f"  Spot Price: ${spot:.2f}")

    chains = []
    today = datetime.now()

    for expiry_str in expirations:
        expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d')
        days_to_expiry = (expiry_date - today).days

        # Filter expiries
        if days_to_expiry < min_expiry_days or days_to_expiry > max_expiry_days:
            continue

        expiry_years = days_to_expiry / 365.0

        print(f"  Fetching expiry: {expiry_str} ({days_to_expiry} days)")

        chain = retry_with_backoff(lambda exp=expiry_str: stock.option_chain(exp))

        # Process calls
        calls = chain.calls.copy()
        calls['option_type'] = 'call'
        calls['expiry_date'] = expiry_str
        calls['expiry_years'] = expiry_years

        # Process puts
        puts = chain.puts.copy()
        puts['option_type'] = 'put'
        puts['expiry_date'] = expiry_str
        puts['expiry_years'] = expiry_years

        chains.append(pd.concat([calls, puts], ignore_index=True))

    if not chains:
        raise ValueError(f"No valid option expiries found for {ticker}")

    full_chain = pd.concat(chains, ignore_index=True)

    # Filter valid quotes using config values
    full_chain = full_chain[
        (full_chain['bid'] > 0) &
        (full_chain['ask'] > full_chain['bid']) &
        (full_chain['volume'] >= min_volume) &
        ((full_chain['ask'] - full_chain['bid']) / full_chain['ask'] < max_spread)
    ].copy()

    # Compute mid price
    full_chain['mid'] = (full_chain['bid'] + full_chain['ask']) / 2

    print(f"  Valid quotes: {len(full_chain)}")

    return full_chain, spot


def compute_implied_vols(chain_df: pd.DataFrame, spot: float, rate: float | None = None):
    """
    Compute implied volatilities for all options using vectorized Newton-Raphson.

    Args:
        chain_df: Option chain DataFrame
        spot: Spot price
        rate: Risk-free rate (default: from config or 0.05)

    Returns:
        DataFrame with implied_vol column added
    """
    # Load defaults from config
    opts_config = CONFIG.get("options", {})
    iv_config = CONFIG.get("implied_vol", {})
    rate = rate if rate is not None else opts_config.get("risk_free_rate", 0.05)
    tol = iv_config.get("tolerance", 1e-5)
    max_iter = iv_config.get("max_iterations", 50)

    print("Computing implied volatilities (vectorized)...")

    # Use vectorized Newton-Raphson for much faster computation
    chain_df['implied_vol'] = implied_vol_newton_raphson_vectorized(
        prices=chain_df['mid'].values,
        spots=np.full(len(chain_df), spot),
        strikes=chain_df['strike'].values,
        expiries=chain_df['expiry_years'].values,
        rates=np.full(len(chain_df), rate),
        option_types=chain_df['option_type'].values,
        tol=tol,
        max_iter=max_iter,
    )

    # Filter out failed IV computations
    chain_df = chain_df[chain_df['implied_vol'].notna()].copy()

    print(f"  Successfully computed {len(chain_df)} IVs")

    return chain_df


def svi_variance(k, a, b, rho, m, sigma):
    """
    SVI total variance formula.

    w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))
    """
    delta_k = k - m
    sqrt_term = np.sqrt(delta_k**2 + sigma**2)
    return a + b * (rho * delta_k + sqrt_term)


def calibrate_svi_for_expiry(strikes, vols, expiry, spot, initial_guess=None):
    """
    Calibrate SVI parameters for a single expiry.

    Args:
        strikes: Array of strikes
        vols: Array of implied volatilities
        expiry: Time to expiry in years
        spot: Spot price
        initial_guess: Optional initial parameter guess

    Returns:
        dict with SVI parameters (a, b, rho, m, sigma)
    """
    # Load SVI bounds from config
    svi_config = CONFIG.get("svi", {})
    a_bounds = svi_config.get("a_bounds", [0.0, 1.0])
    b_bounds = svi_config.get("b_bounds", [0.0, 1.0])
    rho_bounds = svi_config.get("rho_bounds", [-1.0, 1.0])
    m_bounds = svi_config.get("m_bounds", [-0.5, 0.5])
    sigma_bounds = svi_config.get("sigma_bounds", [0.01, 1.0])

    # Convert to log-moneyness
    log_moneyness = np.log(strikes / spot)

    # Total variance = IV^2 * T
    total_variance = vols**2 * expiry

    # Initial guess if not provided
    if initial_guess is None:
        atm_var = np.median(total_variance)
        initial_guess = [
            atm_var,      # a
            0.1,          # b
            -0.5,         # rho (negative for equity put skew)
            0.0,          # m (ATM log-moneyness)
            0.1           # sigma
        ]

    def objective(params):
        a, b, rho, m, sigma = params
        model_var = svi_variance(log_moneyness, a, b, rho, m, sigma)
        return np.sum((model_var - total_variance)**2)

    # Parameter bounds from config
    bounds = [
        (max(0.001, a_bounds[0]), a_bounds[1] if a_bounds[1] else None),
        (max(0.001, b_bounds[0]), b_bounds[1] if b_bounds[1] else None),
        (max(-0.999, rho_bounds[0]), min(0.999, rho_bounds[1])),
        (m_bounds[0], m_bounds[1]),
        (max(0.001, sigma_bounds[0]), sigma_bounds[1] if sigma_bounds[1] else None)
    ]

    result = minimize(objective, initial_guess, bounds=bounds, method='L-BFGS-B')

    if not result.success:
        print(f"  Warning: SVI calibration did not converge for expiry {expiry:.3f}")

    a, b, rho, m, sigma = result.x

    return {
        'expiry': expiry,
        'a': float(a),
        'b': float(b),
        'rho': float(rho),
        'm': float(m),
        'sigma': float(sigma),
        'calibration_error': float(result.fun)
    }


def calibrate_svi_surface(chain_df: pd.DataFrame, spot: float):
    """
    Calibrate SVI surface for all expiries.

    Args:
        chain_df: Option chain with implied_vol column
        spot: Spot price

    Returns:
        List of SVI parameter dicts
    """
    print("Calibrating SVI surface...")

    expiries = sorted(chain_df['expiry_years'].unique())
    svi_params = []

    for expiry in expiries:
        expiry_data = chain_df[chain_df['expiry_years'] == expiry]

        # Use OTM options only (more liquid)
        otm_data = expiry_data[
            ((expiry_data['option_type'] == 'put') & (expiry_data['strike'] < spot)) |
            ((expiry_data['option_type'] == 'call') & (expiry_data['strike'] >= spot))
        ]

        if len(otm_data) < 5:
            print(f"  Skipping expiry {expiry:.3f} (insufficient data)")
            continue

        strikes = otm_data['strike'].values
        vols = otm_data['implied_vol'].values

        params = calibrate_svi_for_expiry(strikes, vols, expiry, spot)
        svi_params.append(params)

        print(f"  Expiry {expiry:.3f}: a={params['a']:.6f}, b={params['b']:.4f}, "
              f"rho={params['rho']:.2f}, error={params['calibration_error']:.6f}")

    return svi_params


def save_vol_surface(svi_params: list, ticker: str, output_dir: Path):
    """Save SVI parameters to JSON."""
    output_file = output_dir / f"{ticker}_vol_surface.json"

    surface_data = {
        'model': 'SVI',
        'params': svi_params
    }

    with open(output_file, 'w') as f:
        json.dump(surface_data, f, indent=2)

    print(f"✓ Saved SVI surface: {output_file}")


def save_option_chain(chain_df: pd.DataFrame, ticker: str, output_dir: Path):
    """Save raw option chain to CSV."""
    output_file = output_dir / f"{ticker}_option_chain.csv"

    # Select columns to save
    cols = ['strike', 'expiry_years', 'bid', 'ask', 'mid', 'volume', 'option_type', 'implied_vol']
    chain_df[cols].to_csv(output_file, index=False)

    print(f"✓ Saved option chain: {output_file} ({len(chain_df)} quotes)")


def main():
    parser = argparse.ArgumentParser(description='Fetch options and calibrate SVI vol surface')
    parser.add_argument('--ticker', type=str, required=True,
                        help='Stock ticker symbol (e.g., SPY, AAPL)')
    parser.add_argument('--output-dir', type=str, default='pricing/skew_trading/data',
                        help='Output directory (default: pricing/skew_trading/data)')
    parser.add_argument('--min-expiry', type=int, default=7,
                        help='Minimum days to expiry (default: 7)')
    parser.add_argument('--max-expiry', type=int, default=365,
                        help='Maximum days to expiry (default: 365)')
    parser.add_argument('--rate', type=float, default=0.05,
                        help='Risk-free rate (default: 0.05)')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Fetch option chain
    chain_df, spot = fetch_option_chain(args.ticker, args.min_expiry, args.max_expiry)

    # Compute implied volatilities
    chain_df = compute_implied_vols(chain_df, spot, args.rate)

    # Calibrate SVI surface
    svi_params = calibrate_svi_surface(chain_df, spot)

    if not svi_params:
        print("Error: Failed to calibrate SVI surface")
        return 1

    # Save outputs
    save_vol_surface(svi_params, args.ticker, output_dir)
    save_option_chain(chain_df, args.ticker, output_dir)

    print(f"\n✓ Option data fetched and SVI surface calibrated for {args.ticker}")
    print(f"  Expiries calibrated: {len(svi_params)}")

    return 0


if __name__ == '__main__':
    exit(main())

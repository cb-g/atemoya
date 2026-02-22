#!/usr/bin/env python3
"""
Calibrate volatility surface (SVI or SABR) from market option data
"""

import argparse
import sys
import json
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np
import numpy.typing as npt
from scipy.optimize import minimize, differential_evolution


# Load configuration
CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def load_config() -> dict:
    """Load configuration from config.json."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


CONFIG = load_config()


def svi_total_variance(
    k: float | npt.NDArray[np.float64],
    params: tuple[float, float, float, float, float]
) -> float | npt.NDArray[np.float64]:
    """
    SVI total variance formula
    w(k) = a + b × (ρ(k - m) + √((k - m)² + σ²))
    """
    a, b, rho, m, sigma = params
    delta_k = k - m
    return a + b * (rho * delta_k + np.sqrt(delta_k**2 + sigma**2))


def svi_implied_vol(
    k: float,
    T: float,
    params: tuple[float, float, float, float, float]
) -> float:
    """Convert SVI total variance to implied vol"""
    w = svi_total_variance(k, params)
    if w <= 0 or T <= 0:
        return np.nan
    return np.sqrt(w / T)


def calibrate_svi_single_expiry(
    df_expiry: pd.DataFrame,
    spot: float,
    expiry: float
) -> tuple[float, float, float, float, float] | None:
    """
    Calibrate SVI parameters for a single expiry

    Args:
        df_expiry: DataFrame with market quotes for this expiry
        spot: Current spot price
        expiry: Time to expiry in years

    Returns:
        Tuple of (a, b, rho, m, sigma) or None if calibration fails
    """
    # Compute log-moneyness
    df_expiry = df_expiry.copy()
    df_expiry['log_moneyness'] = np.log(df_expiry['strike'] / spot)
    df_expiry['total_var'] = (df_expiry['implied_volatility'] ** 2) * expiry

    # Remove invalid data
    df_expiry = df_expiry[
        (df_expiry['implied_volatility'] > 0) &
        (df_expiry['total_var'] > 0)
    ]

    if len(df_expiry) < 5:
        return None

    k_data = df_expiry['log_moneyness'].values
    w_data = df_expiry['total_var'].values

    # Load SVI and optimizer config
    svi_config = CONFIG.get("svi", {})
    opt_config = CONFIG.get("optimizer", {})
    a_bounds = tuple(svi_config.get("a_bounds", [0.0, 1.0]))
    b_bounds = tuple(svi_config.get("b_bounds", [0.0, 1.0]))
    rho_bounds = tuple(svi_config.get("rho_bounds", [-1.0, 1.0]))
    m_bounds = tuple(svi_config.get("m_bounds", [-0.5, 0.5]))
    sigma_bounds = tuple(svi_config.get("sigma_bounds", [0.01, 1.0]))
    max_iter = opt_config.get("max_iterations", 1000)
    tolerance = opt_config.get("tolerance", 1e-6)
    seed = opt_config.get("seed", 42)

    # Objective function: SSE with no-arbitrage penalty
    def objective(params):
        a, b, rho, m, sigma = params
        w_model = np.array([svi_total_variance(k, params) for k in k_data])
        sse = np.sum((w_model - w_data) ** 2)
        # Penalty for butterfly arbitrage violation: b/σ ≥ |ρ|
        butterfly_slack = b / sigma - abs(rho)
        if butterfly_slack < 0:
            sse += 1e6 * butterfly_slack ** 2
        # Penalty for negative total variance
        neg_var = np.sum(np.minimum(w_model, 0) ** 2)
        if neg_var > 0:
            sse += 1e6 * neg_var
        return sse

    # Initial guess
    atm_var = w_data[np.argmin(np.abs(k_data))].item()
    x0 = [atm_var, 0.1, 0.0, 0.0, 0.1]

    # Bounds from config
    bounds = [a_bounds, b_bounds, rho_bounds, m_bounds, sigma_bounds]

    # Optimize using differential evolution (global optimizer)
    result = differential_evolution(
        objective,
        bounds,
        maxiter=max_iter,
        seed=seed,
        atol=tolerance,
        tol=tolerance
    )

    if not result.success:
        # Try local optimizer as fallback
        result = minimize(
            objective,
            x0,
            bounds=bounds,
            method='L-BFGS-B'
        )

    if result.success:
        a, b, rho, m, sigma = result.x

        # Note if butterfly condition is binding
        if b / sigma <= abs(rho) + 1e-4:
            print(f"  Note: SVI butterfly condition tight at T={expiry:.2f} (b/σ={b/sigma:.4f}, |ρ|={abs(rho):.4f})")

        return (a, b, rho, m, sigma)

    return None


def calibrate_svi(df_options, spot):
    """
    Calibrate SVI for all expiries

    Returns:
        List of dictionaries with expiry and SVI parameters
    """
    print("Calibrating SVI volatility surface...")

    expiries = sorted(df_options['expiry'].unique())
    svi_params_list = []

    for expiry in expiries:
        df_expiry = df_options[df_options['expiry'] == expiry]

        params = calibrate_svi_single_expiry(df_expiry, spot, expiry)

        if params is not None:
            a, b, rho, m, sigma = params
            svi_params_list.append({
                'expiry': float(expiry),
                'a': float(a),
                'b': float(b),
                'rho': float(rho),
                'm': float(m),
                'sigma': float(sigma)
            })
            print(f"  ✓ T={expiry:.3f}y: a={a:.4f}, b={b:.4f}, ρ={rho:.3f}, m={m:.3f}, σ={sigma:.3f}")
        else:
            print(f"  ✗ T={expiry:.3f}y: Calibration failed")

    return svi_params_list


def sabr_implied_vol_hagan(F, K, T, params):
    """
    SABR implied volatility using Hagan et al. approximation

    Args:
        F: Forward price
        K: Strike
        T: Time to expiry
        params: (alpha, beta, rho, nu)
    """
    alpha, beta, rho, nu = params

    # Handle ATM case
    if abs(F - K) < 1e-6:
        fk_mid = F ** (1 - beta)
        atm_vol = alpha / fk_mid * (
            1 + T * (
                (1 - beta)**2 * alpha**2 / (24 * fk_mid**2)
                + 0.25 * rho * beta * nu * alpha / fk_mid
                + (2 - 3 * rho**2) * nu**2 / 24
            )
        )
        return atm_vol

    # General case
    fk_mid = (F * K) ** ((1 - beta) / 2)
    log_fk = np.log(F / K)

    z = (nu / alpha) * fk_mid * log_fk

    # χ(z) function
    if abs(z) < 1e-6:
        chi_z = 1.0
    else:
        sqrt_term = np.sqrt(1 - 2 * rho * z + z**2)
        chi_z = z / np.log((sqrt_term + z - rho) / (1 - rho))

    # First factor
    factor1 = alpha / fk_mid

    # Second factor
    correction = 1 + ((1 - beta)**2 * log_fk**2 / 24 + (1 - beta)**4 * log_fk**4 / 1920)
    factor2 = chi_z / correction

    # Time-dependent correction
    fk_avg = (F + K) / 2
    fk_avg_factor = fk_avg ** (1 - beta)

    time_correction = 1 + T * (
        (1 - beta)**2 * alpha**2 / (24 * fk_avg_factor**2)
        + 0.25 * rho * beta * nu * alpha / fk_avg_factor
        + (2 - 3 * rho**2) * nu**2 / 24
    )

    return factor1 * factor2 * time_correction


def calibrate_sabr_single_expiry(df_expiry, spot, expiry):
    """Calibrate SABR for single expiry"""
    df_expiry = df_expiry.copy()

    # Remove invalid data
    df_expiry = df_expiry[df_expiry['implied_volatility'] > 0]

    if len(df_expiry) < 5:
        return None

    strikes = df_expiry['strike'].values
    market_ivs = df_expiry['implied_volatility'].values

    # Forward ≈ spot for simplicity
    forward = spot

    # Load SABR and optimizer config
    sabr_config = CONFIG.get("sabr", {})
    opt_config = CONFIG.get("optimizer", {})
    alpha_bounds = tuple(sabr_config.get("alpha_bounds", [0.01, 2.0]))
    beta = sabr_config.get("beta", 0.5)  # Often fixed
    rho_bounds = tuple(sabr_config.get("rho_bounds", [-0.99, 0.99]))
    nu_bounds = tuple(sabr_config.get("nu_bounds", [0.01, 2.0]))
    max_iter = opt_config.get("max_iterations", 1000)
    seed = opt_config.get("seed", 42)

    def objective(params):
        alpha, beta, rho, nu = params
        model_ivs = np.array([
            sabr_implied_vol_hagan(forward, K, expiry, params)
            for K in strikes
        ])
        return np.sum((model_ivs - market_ivs) ** 2)

    # Initial guess
    atm_vol = market_ivs[np.argmin(np.abs(strikes - spot))]
    x0 = [atm_vol, beta, 0.0, 0.3]

    # Bounds from config
    bounds = [alpha_bounds, (0.0, 1.0), rho_bounds, nu_bounds]

    result = differential_evolution(
        objective,
        bounds,
        maxiter=max_iter,
        seed=seed
    )

    if result.success:
        return tuple(result.x)

    return None


def calibrate_sabr(df_options, spot):
    """Calibrate SABR for all expiries"""
    print("Calibrating SABR volatility surface...")

    expiries = sorted(df_options['expiry'].unique())
    sabr_params_list = []

    for expiry in expiries:
        df_expiry = df_options[df_options['expiry'] == expiry]

        params = calibrate_sabr_single_expiry(df_expiry, spot, expiry)

        if params is not None:
            alpha, beta, rho, nu = params
            sabr_params_list.append({
                'expiry': float(expiry),
                'alpha': float(alpha),
                'beta': float(beta),
                'rho': float(rho),
                'nu': float(nu)
            })
            print(f"  ✓ T={expiry:.3f}y: α={alpha:.4f}, β={beta:.3f}, ρ={rho:.3f}, ν={nu:.3f}")
        else:
            print(f"  ✗ T={expiry:.3f}y: Calibration failed")

    return sabr_params_list


def main():
    parser = argparse.ArgumentParser(description='Calibrate volatility surface')
    parser.add_argument('--ticker', required=True, help='Stock ticker')
    parser.add_argument('--model', choices=['svi', 'sabr', 'both'], default='both',
                       help='Volatility model (default: both)')
    parser.add_argument('--data-dir', default='pricing/options_hedging/data',
                       help='Data directory')

    args = parser.parse_args()

    try:
        data_dir = Path(args.data_dir)

        # Load option chain
        options_file = data_dir / f"{args.ticker}_options.csv"
        if not options_file.exists():
            raise FileNotFoundError(f"Option chain not found: {options_file}")

        df_options = pd.read_csv(options_file)

        # Load underlying data for spot price
        underlying_file = data_dir / f"{args.ticker}_underlying.csv"
        if not underlying_file.exists():
            raise FileNotFoundError(f"Underlying data not found: {underlying_file}")

        df_underlying = pd.read_csv(underlying_file)
        spot = df_underlying['spot_price'].iloc[0]

        models = ['svi', 'sabr'] if args.model == 'both' else [args.model]

        print(f"\n=== Volatility Surface Calibration: {args.ticker} ===")
        print(f"Spot Price: ${spot:.2f}")
        print(f"Models: {', '.join(m.upper() for m in models)}")
        print(f"Option Quotes: {len(df_options)}\n")

        for model in models:
            if model == 'svi':
                params = calibrate_svi(df_options, spot)
                surface = {'type': 'SVI', 'params': params}
            else:
                params = calibrate_sabr(df_options, spot)
                surface = {'type': 'SABR', 'params': params}

            if not params:
                print(f"\nWarning: {model.upper()} calibration failed for all expiries",
                      file=sys.stderr)
                continue

            # Save to model-specific JSON
            output_file = data_dir / f"{args.ticker}_vol_surface_{model}.json"
            with open(output_file, 'w') as f:
                json.dump(surface, f, indent=2)

            print(f"\n✓ Saved {model.upper()} volatility surface to {output_file}")
            print(f"  Calibrated {len(params)} expiries successfully\n")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

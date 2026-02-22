#!/usr/bin/env python3
"""
Plot volatility smile/skew from SVI surface.

Visualizes:
- Implied volatility vs strike
- Implied volatility vs moneyness
- Multiple expiries overlaid
"""

import argparse
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure


def setup_dark_style():
    """Configure matplotlib for dark mode."""
    setup_dark_mode()


def svi_variance(k, a, b, rho, m, sigma):
    """SVI total variance."""
    delta_k = k - m
    sqrt_term = np.sqrt(delta_k**2 + sigma**2)
    return a + b * (rho * delta_k + sqrt_term)


def svi_implied_vol(k, params, T):
    """Compute implied vol from SVI parameters."""
    var = svi_variance(k, params['a'], params['b'], params['rho'], params['m'], params['sigma'])
    return np.sqrt(var / T)


def select_key_expiries(params_list, target_days=[30, 60, 90, 180, 365]):
    """
    Select a subset of expiries closest to target days for cleaner visualization.

    Args:
        params_list: List of SVI params with 'expiry' in years
        target_days: Target expiry days to select

    Returns:
        Filtered list of params for key expiries
    """
    if len(params_list) <= len(target_days):
        return params_list

    selected = []
    used_indices = set()

    for target in target_days:
        target_years = target / 365.0
        best_idx = None
        best_diff = float('inf')

        for idx, params in enumerate(params_list):
            if idx in used_indices:
                continue
            diff = abs(params['expiry'] - target_years)
            if diff < best_diff:
                best_diff = diff
                best_idx = idx

        if best_idx is not None and best_diff < 0.1:  # Within ~36 days of target
            selected.append(params_list[best_idx])
            used_indices.add(best_idx)

    # Sort by expiry
    selected.sort(key=lambda x: x['expiry'])
    return selected


def plot_volatility_smile(vol_surface: dict, spot: float, output_file: Path, ticker: str = ''):
    """
    Plot volatility smile for key expiries.

    Args:
        vol_surface: SVI surface dict
        spot: Current spot price
        output_file: Output file path
    """
    setup_dark_style()

    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))

    # Filter to key expiries for cleaner visualization
    all_params = vol_surface['params']
    params_list = select_key_expiries(all_params, target_days=[30, 60, 90, 180, 365])

    # Strike range around spot
    strike_range = np.linspace(spot * 0.8, spot * 1.2, 200)
    log_moneyness = np.log(strike_range / spot)

    colors = [COLORS['blue'], COLORS['cyan'], COLORS['green'],
              COLORS['magenta'], COLORS['yellow']]

    # Plot 1: IV vs Strike (multiple expiries)
    for idx, params in enumerate(params_list):
        T = params['expiry']
        k = log_moneyness
        iv = svi_implied_vol(k, params, T)

        color = colors[idx % len(colors)]
        label = f"{T*365:.0f}d expiry"

        ax1.plot(strike_range, iv * 100, color=color, linewidth=2, label=label)

    ax1.axvline(spot, color=COLORS['fg'], linestyle='--', alpha=0.5, label='Spot')
    ax1.set_xlabel('Strike ($)')
    ax1.set_ylabel('Implied Volatility (%)')
    ax1.set_title('Volatility Smile: IV vs Strike')
    ax1.legend(loc='best', fontsize=8)
    ax1.grid(True, alpha=0.2)

    # Plot 2: IV vs Moneyness
    for idx, params in enumerate(params_list):
        T = params['expiry']
        k = log_moneyness
        iv = svi_implied_vol(k, params, T)

        color = colors[idx % len(colors)]
        label = f"{T*365:.0f}d"

        ax2.plot(log_moneyness * 100, iv * 100, color=color, linewidth=2, label=label)

    ax2.axvline(0, color=COLORS['fg'], linestyle='--', alpha=0.5, label='ATM')
    ax2.set_xlabel('Log-Moneyness (%)')
    ax2.set_ylabel('Implied Volatility (%)')
    ax2.set_title('Volatility Skew: IV vs Moneyness')
    ax2.legend(loc='best', fontsize=8)
    ax2.grid(True, alpha=0.2)

    # Plot 3: Skew (derivative dIV/dK)
    for idx, params in enumerate(params_list):
        T = params['expiry']
        k = log_moneyness
        iv = svi_implied_vol(k, params, T)

        # Numerical derivative
        skew = np.gradient(iv, log_moneyness)

        color = colors[idx % len(colors)]
        label = f"{T*365:.0f}d"

        ax3.plot(log_moneyness * 100, skew, color=color, linewidth=2, label=label)

    ax3.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.3)
    ax3.axvline(0, color=COLORS['fg'], linestyle='--', alpha=0.5)
    ax3.set_xlabel('Log-Moneyness (%)')
    ax3.set_ylabel('Skew (dIV/dk)')
    ax3.set_title('Volatility Skew Slope')
    ax3.legend(loc='best', fontsize=8)
    ax3.grid(True, alpha=0.2)

    # Plot 4: Term Structure (ATM vol) - use ALL expiries, sorted and smoothed
    all_sorted = sorted(all_params, key=lambda x: x['expiry'])
    expiries = np.array([p['expiry'] * 365 for p in all_sorted])
    atm_vols = []

    for params in all_sorted:
        T = params['expiry']
        iv_atm = svi_implied_vol(0.0, params, T)
        atm_vols.append(iv_atm * 100)

    atm_vols = np.array(atm_vols)

    # Apply simple moving average smoothing if enough points
    if len(atm_vols) >= 5:
        kernel_size = 3
        kernel = np.ones(kernel_size) / kernel_size
        atm_vols_smooth = np.convolve(atm_vols, kernel, mode='same')
        # Keep original values at edges
        atm_vols_smooth[0] = atm_vols[0]
        atm_vols_smooth[-1] = atm_vols[-1]
    else:
        atm_vols_smooth = atm_vols

    ax4.plot(expiries, atm_vols, 'o', color=COLORS['cyan'], markersize=5, alpha=0.5, label='Raw')
    ax4.plot(expiries, atm_vols_smooth, '-', color=COLORS['blue'], linewidth=2, label='Smoothed')
    ax4.set_xlabel('Days to Expiry')
    ax4.set_ylabel('ATM Implied Volatility (%)')
    ax4.set_title('Volatility Term Structure')
    ax4.legend(loc='best', fontsize=8)
    ax4.grid(True, alpha=0.2)

    if ticker:
        fig.suptitle(f'{ticker} — Volatility Surface', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    plt.close()

    print(f"✓ Saved volatility smile plot: {output_file}")


def load_vol_surface(ticker: str, data_dir: Path) -> dict:
    """Load SVI surface from JSON."""
    vol_file = data_dir / f"{ticker}_vol_surface.json"

    if not vol_file.exists():
        raise FileNotFoundError(f"Vol surface file not found: {vol_file}")

    with open(vol_file, 'r') as f:
        surface = json.load(f)

    return surface


def load_underlying(ticker: str, data_dir: Path) -> float:
    """Load spot price from underlying JSON."""
    underlying_file = data_dir / f"{ticker}_underlying.json"

    if not underlying_file.exists():
        raise FileNotFoundError(f"Underlying file not found: {underlying_file}")

    with open(underlying_file, 'r') as f:
        data = json.load(f)

    return data['spot_price']


def main():
    parser = argparse.ArgumentParser(description='Plot volatility smile/skew')
    parser.add_argument('--ticker', type=str, required=True,
                        help='Stock ticker symbol')
    parser.add_argument('--data-dir', type=str, default='pricing/skew_trading/data',
                        help='Data directory')
    parser.add_argument('--output-dir', type=str, default='pricing/skew_trading/output',
                        help='Output directory for plots')

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    vol_surface = load_vol_surface(args.ticker, data_dir)
    spot = load_underlying(args.ticker, data_dir)

    print(f"Spot price: ${spot:.2f}")
    print(f"SVI expiries: {len(vol_surface['params'])}")

    # Plot
    output_file = output_dir / f"{args.ticker}_vol_smile.png"
    plot_volatility_smile(vol_surface, spot, output_file, ticker=args.ticker)

    return 0


if __name__ == '__main__':
    exit(main())

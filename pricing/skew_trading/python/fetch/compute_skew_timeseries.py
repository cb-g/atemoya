#!/usr/bin/env python3
"""
Compute historical skew time series from option chain data.

Uses real historical data from daily collection (collect_snapshot.py) when
available. Falls back to synthetic generation when insufficient history exists.

Real data: Accumulated via daily cron job running collect_snapshot.py,
stored in {TICKER}_skew_history.csv.

Synthetic data: Creates approximate skew observations from a single SVI
surface snapshot + random noise. Used for demo/backtest bootstrapping.
"""

import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import pandas as pd


def generate_synthetic_skew_timeseries(
    ticker: str,
    spot_prices: pd.DataFrame,
    vol_surface: dict,
    expiry_days: int = 30
) -> pd.DataFrame:
    """
    Generate synthetic skew observations.

    In production, this would use real historical IV data.
    For demo purposes, we add noise to current SVI surface.

    Args:
        ticker: Stock ticker
        spot_prices: DataFrame with timestamp, close columns
        vol_surface: SVI surface dict
        expiry_days: Fixed expiry to use

    Returns:
        DataFrame with skew observations
    """
    print(f"Generating synthetic skew timeseries for {ticker}...")
    print(f"  Using {len(spot_prices)} historical observations")

    expiry_years = expiry_days / 365.0

    # Find closest SVI parameters for target expiry
    params_list = vol_surface['params']
    target_params = min(params_list, key=lambda p: abs(p['expiry'] - expiry_years))

    print(f"  Using SVI params for expiry {target_params['expiry']:.3f}")

    observations = []

    # AR(1) process with regime shifts for realistic dynamics
    # rr25[t] = base + alpha*(rr25[t-1] - base) + noise + jumps
    base_rr25 = -0.04   # -4% base put skew
    base_bf25 = 0.02    # +2% base smile
    atm_var = target_params['a']
    base_atm_vol = np.sqrt(atm_var / target_params['expiry'])

    alpha_rr = 0.92    # Strong persistence in skew
    alpha_bf = 0.90    # Persistence in butterfly
    alpha_vol = 0.95   # Very persistent ATM vol

    sigma_rr = 0.004   # Innovation noise for RR25
    sigma_bf = 0.002   # Innovation noise for BF25
    sigma_vol = 0.008  # Innovation noise for ATM vol

    # Regime shift parameters: occasional jumps that break mean reversion
    jump_prob = 0.04    # 4% chance of regime jump per day
    jump_size_rr = 0.02 # Jump magnitude for RR25
    jump_size_vol = 0.04  # Jump magnitude for ATM vol

    # Initialize state
    rr25 = base_rr25
    bf25 = base_bf25
    atm_vol = base_atm_vol
    n_obs = len(spot_prices)

    for i, (idx, row) in enumerate(spot_prices.iterrows()):
        timestamp = row['timestamp']
        spot = row['close']

        # Time-varying equilibrium: simulates changing market structure
        # The strategy uses an expanding-window mean, so when the true base
        # drifts, the estimated mean lags behind → creates realistic losses
        drift_rr = 0.015 * np.sin(2 * np.pi * i / 100)    # ±1.5% on 100-day cycle
        drift_vol = 0.03 * np.sin(2 * np.pi * i / 150)     # ±3% on 150-day cycle
        local_base_rr = base_rr25 + drift_rr
        local_base_vol = base_atm_vol + drift_vol

        # AR(1) updates: mean-reverting to drifting local equilibrium
        rr25 = local_base_rr + alpha_rr * (rr25 - local_base_rr) + np.random.normal(0, sigma_rr)
        bf25 = base_bf25 + alpha_bf * (bf25 - base_bf25) + np.random.normal(0, sigma_bf)
        atm_vol = local_base_vol + alpha_vol * (atm_vol - local_base_vol) + np.random.normal(0, sigma_vol)

        # Regime jumps: simulate sudden skew dislocations (earnings, macro events)
        if np.random.random() < jump_prob:
            rr25 += np.random.choice([-1, 1]) * jump_size_rr * np.random.random()
            atm_vol += jump_size_vol * np.random.random()

        # Wings vols
        call_25d_vol = atm_vol + rr25 / 2 + bf25
        put_25d_vol = atm_vol - rr25 / 2 + bf25

        # Delta-based strikes (simplified, assume 25% delta)
        # For more accuracy, would solve Black-Scholes delta equation
        call_25d_strike = spot * 1.05  # Approx 25-delta call
        put_25d_strike = spot * 0.95   # Approx 25-delta put

        # Skew slope (linear regression placeholder)
        skew_slope = rr25 / 0.10  # Approx: RR25 divided by moneyness range

        observations.append({
            'timestamp': timestamp,
            'ticker': ticker,
            'expiry': expiry_years,
            'rr25': rr25,
            'bf25': bf25,
            'skew_slope': skew_slope,
            'atm_vol': atm_vol,
            'put_25d_vol': put_25d_vol,
            'call_25d_vol': call_25d_vol,
            'put_25d_strike': put_25d_strike,
            'call_25d_strike': call_25d_strike
        })

    df = pd.DataFrame(observations)
    print(f"  Generated {len(df)} skew observations")

    return df


def load_price_data(ticker: str, data_dir: Path) -> pd.DataFrame:
    """Load historical price data."""
    price_file = data_dir / f"{ticker}_prices.csv"

    if not price_file.exists():
        raise FileNotFoundError(f"Price file not found: {price_file}")

    df = pd.read_csv(price_file)
    print(f"Loaded {len(df)} price observations from {price_file}")

    return df


def load_vol_surface(ticker: str, data_dir: Path) -> dict:
    """Load calibrated vol surface."""
    vol_file = data_dir / f"{ticker}_vol_surface.json"

    if not vol_file.exists():
        raise FileNotFoundError(f"Vol surface file not found: {vol_file}")

    with open(vol_file, 'r') as f:
        surface = json.load(f)

    print(f"Loaded SVI surface with {len(surface['params'])} expiries")

    return surface


def use_real_history_if_available(
    ticker: str, data_dir: Path, min_rows: int = 60
) -> pd.DataFrame | None:
    """
    Check if real historical skew data is available.

    Looks for {TICKER}_skew_history.csv produced by collect_snapshot.py.

    Args:
        ticker: Stock ticker
        data_dir: Data directory
        min_rows: Minimum rows needed for downstream lookback (default: 60)

    Returns:
        DataFrame if real history is sufficient, else None
    """
    history_file = data_dir / f"{ticker}_skew_history.csv"

    if not history_file.exists():
        return None

    df = pd.read_csv(history_file)

    if len(df) < min_rows:
        print(f"Real history has {len(df)} rows (need {min_rows}), using synthetic")
        return None

    print(f"Using real historical skew data: {len(df)} observations")
    return df


def save_skew_timeseries(df: pd.DataFrame, ticker: str, output_dir: Path):
    """Save skew timeseries to CSV."""
    output_file = output_dir / f"{ticker}_skew_timeseries.csv"

    df.to_csv(output_file, index=False)

    print(f"✓ Saved skew timeseries: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Compute historical skew timeseries'
    )
    parser.add_argument('--ticker', type=str, required=True,
                        help='Stock ticker symbol')
    parser.add_argument('--data-dir', type=str, default='pricing/skew_trading/data',
                        help='Data directory (default: pricing/skew_trading/data)')
    parser.add_argument('--expiry', type=int, default=30,
                        help='Days to expiry for skew observations (default: 30)')
    parser.add_argument('--min-history', type=int, default=60,
                        help='Minimum real history rows before using real data (default: 60)')

    args = parser.parse_args()

    data_dir = Path(args.data_dir)

    # Try real historical data first
    real_history = use_real_history_if_available(args.ticker, data_dir, args.min_history)

    if real_history is not None:
        save_skew_timeseries(real_history, args.ticker, data_dir)
        print(f"\n✓ Skew timeseries from real market data for {args.ticker}")
        return 0

    # Fall back to synthetic generation
    print("Generating synthetic timeseries (no sufficient real history)...")
    price_data = load_price_data(args.ticker, data_dir)
    vol_surface = load_vol_surface(args.ticker, data_dir)

    skew_df = generate_synthetic_skew_timeseries(
        args.ticker,
        price_data,
        vol_surface,
        args.expiry
    )

    save_skew_timeseries(skew_df, args.ticker, data_dir)

    print(f"\n✓ Skew timeseries generated for {args.ticker}")
    print(f"  Note: Synthetic data. Run collect_snapshot.py daily to accumulate real history.")

    return 0


if __name__ == '__main__':
    exit(main())

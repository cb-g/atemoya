#!/usr/bin/env python3
"""
Fetch Historical Earnings Data

Fetches historical earnings dates and calculates:
1. Implied move (from ATM straddle IV before earnings)
2. Realized move (actual % move on earnings day)

Uses the unified data provider system (IBKR if available, yfinance fallback)
for historical price data. Earnings dates are fetched via yfinance.

If IV snapshot history exists (from collect_earnings_iv.py), uses actual
implied moves instead of the RV*1.2 estimate.

Builds the historical database needed for the 4 signals.
"""

import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import argparse

from lib.python.retry import retry_with_backoff
from lib.python.data_fetcher import get_provider


def calculate_implied_move_from_straddle(atm_call_iv, atm_put_iv, days_to_expiry):
    """
    Calculate implied move from ATM straddle IVs.

    Simplified: Use average IV, convert to 1-day expected move.
    Formula: sqrt(2/pi) * sigma * sqrt(1/365)
    """
    if days_to_expiry <= 0:
        return 0.0

    # Average IV
    avg_iv = (atm_call_iv + atm_put_iv) / 2

    # Convert to 1-day expected absolute move
    # sigma_event = sigma_annual * sqrt(1/365)
    # Expected absolute move = sqrt(2/pi) * sigma_event ~ 0.798 * sigma_event
    one_day_vol = avg_iv * np.sqrt(1/365)
    implied_move = 0.798 * one_day_vol

    return implied_move


def load_snapshot_history(ticker: str, data_dir: Path) -> pd.DataFrame | None:
    """Load IV snapshot history for a ticker, if available."""
    snapshots_file = data_dir / f"{ticker}_iv_snapshots.csv"
    if not snapshots_file.exists():
        return None

    try:
        df = pd.read_csv(snapshots_file)
        if len(df) == 0:
            return None
        return df
    except Exception:
        return None


def lookup_snapshot_implied_move(
    snapshots: pd.DataFrame,
    earnings_date_str: str,
) -> float | None:
    """
    Look up actual implied move from snapshot history for a given earnings date.

    Finds snapshots within 14 days before this earnings date, preferring
    the one closest to 14 days out (ideal entry point).

    Returns implied_move if found, None otherwise.
    """
    nearby = snapshots[
        (snapshots['earnings_date'] == earnings_date_str)
        & (snapshots['days_to_earnings'] >= 10)
        & (snapshots['days_to_earnings'] <= 18)
    ]

    if len(nearby) == 0:
        return None

    # Prefer snapshot closest to 14 days before earnings (ideal entry)
    best_idx = (nearby['days_to_earnings'] - 14).abs().argsort().iloc[0]
    best = nearby.iloc[best_idx]
    return float(best['implied_move'])


def fetch_earnings_history(ticker: str, output_dir: Path, years_back: int = 3):
    """
    Fetch historical earnings and calculate implied/realized moves.

    Uses IV snapshot history (from collect_earnings_iv.py) when available,
    falling back to RV*1.2 estimate otherwise.
    """

    provider = get_provider()
    print(f"\nFetching earnings history for {ticker}...")
    print(f"  Data provider: {provider.name}")

    # Get earnings dates (always via yfinance — provider system doesn't wrap earnings)
    stock = yf.Ticker(ticker)

    try:
        earnings_dates = retry_with_backoff(lambda: stock.earnings_dates)
        if earnings_dates is None or len(earnings_dates) == 0:
            print(f"  x No earnings data available for {ticker}")
            return None
    except Exception as e:
        print(f"  x Error fetching earnings: {e}")
        return None

    print(f"  Found {len(earnings_dates)} earnings dates")

    # Get historical prices via provider
    period = f"{years_back}y"
    ohlcv = provider.fetch_ohlcv(ticker, period=period, interval="1d")

    if ohlcv is None or len(ohlcv) == 0:
        print(f"  x No historical price data")
        return None

    # Convert OHLCV to DataFrame for easier date-based lookup
    hist_prices = pd.DataFrame({
        'Date': pd.to_datetime(ohlcv.dates),
        'Close': ohlcv.close,
    })
    hist_prices = hist_prices.set_index('Date')

    # Load snapshot history if available
    snapshots = load_snapshot_history(ticker, output_dir)
    snapshot_count = 0
    estimate_count = 0

    if snapshots is not None:
        print(f"  Found {len(snapshots)} IV snapshots")

    # Process each earnings event
    earnings_data = []

    for earnings_date, row in earnings_dates.iterrows():
        # Skip future earnings
        if earnings_date.date() > datetime.now().date():
            continue

        # Get price on earnings day and day before
        try:
            earnings_date_only = earnings_date.date()

            # Get price before earnings
            before_date = earnings_date_only - timedelta(days=1)
            before_prices = hist_prices[hist_prices.index.date <= before_date]
            if len(before_prices) == 0:
                continue
            price_before = before_prices['Close'].iloc[-1]

            # Get price after earnings
            after_prices = hist_prices[hist_prices.index.date >= earnings_date_only]
            if len(after_prices) == 0:
                continue
            price_after = after_prices['Close'].iloc[0]

            # Calculate realized move
            realized_move = abs(price_after - price_before) / price_before

            # Try snapshot history first for implied move
            earnings_date_str = earnings_date_only.strftime('%Y-%m-%d')
            implied_move = None
            source = "estimate"

            if snapshots is not None:
                implied_move = lookup_snapshot_implied_move(snapshots, earnings_date_str)
                if implied_move is not None:
                    source = "snapshot"
                    snapshot_count += 1

            # Fall back to RV*1.2 estimate
            if implied_move is None:
                vol_window = hist_prices[hist_prices.index.date < earnings_date_only].tail(30)
                if len(vol_window) >= 20:
                    returns = vol_window['Close'].pct_change().dropna()
                    realized_vol_30d = returns.std() * np.sqrt(252)

                    # Rough estimate: implied move often ~1.2x realized vol converted to 1-day
                    implied_move = realized_vol_30d * np.sqrt(1/365) * 0.798 * 1.2
                else:
                    implied_move = realized_move * 1.1  # Rough placeholder
                estimate_count += 1

            earnings_data.append({
                'ticker': ticker,
                'date': earnings_date_str,
                'implied_move': implied_move,
                'realized_move': realized_move,
            })

        except Exception as e:
            print(f"  x Error processing {earnings_date}: {e}")
            continue

    if len(earnings_data) == 0:
        print(f"  x No valid earnings events found")
        return None

    # Print IV source breakdown
    total = snapshot_count + estimate_count
    print(f"\n  IV sources: {snapshot_count}/{total} from snapshots, {estimate_count}/{total} estimated (RV*1.2)")

    # Create DataFrame
    df = pd.DataFrame(earnings_data)

    # Sort by date
    df = df.sort_values('date')

    # Save to CSV
    output_file = output_dir / 'earnings_history.csv'

    # Load existing if present and append
    if output_file.exists():
        existing = pd.read_csv(output_file)
        # Remove duplicates for this ticker
        existing = existing[existing['ticker'] != ticker]
        # Append new data
        df = pd.concat([existing, df], ignore_index=True)
        df = df.sort_values(['ticker', 'date'])

    df.to_csv(output_file, index=False)

    print(f"\n+ Earnings history saved: {output_file}")
    print(f"  {len(earnings_data)} events for {ticker}")
    print(f"\nRecent events:")
    print(df[df['ticker'] == ticker].tail(5).to_string(index=False))

    return df

def main():
    parser = argparse.ArgumentParser(description='Fetch earnings history')
    parser.add_argument('--ticker', type=str, required=True, help='Stock ticker')
    parser.add_argument('--years', type=int, default=3, help='Years of history (default: 3)')
    parser.add_argument('--output-dir', type=str, default='pricing/pre_earnings_straddle/data',
                       help='Output directory')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fetch_earnings_history(args.ticker, output_dir, args.years)

if __name__ == "__main__":
    main()

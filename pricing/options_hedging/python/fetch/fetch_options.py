#!/usr/bin/env python3
"""
Fetch option chain data for vol surface calibration.
Uses yfinance for comprehensive chain fetch (all expiries needed for calibration).
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf
import pandas as pd
import numpy as np

from lib.python.retry import retry_with_backoff
from lib.python.data_fetcher import get_available_providers


def fetch_option_chain(ticker: str, min_days: int = 7, max_days: int = 730) -> pd.DataFrame:
    """
    Fetch option chain for all available expiries.

    Args:
        ticker: Stock ticker symbol
        min_days: Minimum days to expiry to include
        max_days: Maximum days to expiry to include

    Returns:
        DataFrame with columns: ticker, option_type, strike, expiry, bid, ask, implied_volatility
    """
    print(f"Fetching option chain for {ticker}...")
    print(f"Available providers: {get_available_providers()}")

    stock = yf.Ticker(ticker)

    try:
        expirations = retry_with_backoff(lambda: stock.options)
    except Exception as e:
        raise ValueError(f"Failed to fetch option expirations for {ticker}: {e}")

    if not expirations:
        raise ValueError(f"No options data available for {ticker}")

    chains = []
    now = datetime.now()

    for expiry_str in expirations:
        expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d')
        days_to_expiry = (expiry_dt - now).days

        # Filter by expiry range
        if days_to_expiry < min_days or days_to_expiry > max_days:
            continue

        try:
            chain = retry_with_backoff(lambda exp=expiry_str: stock.option_chain(exp))
        except Exception as e:
            print(f"  Warning: Failed to fetch chain for {expiry_str}: {e}")
            continue

        # Process calls
        calls = chain.calls.copy()
        calls['option_type'] = 'call'
        calls['expiry'] = days_to_expiry / 365.0  # Convert to years

        # Process puts
        puts = chain.puts.copy()
        puts['option_type'] = 'put'
        puts['expiry'] = days_to_expiry / 365.0

        # Combine
        combined = pd.concat([calls, puts], ignore_index=True)
        combined['ticker'] = ticker

        chains.append(combined)

        print(f"  Fetched {expiry_str} ({days_to_expiry} days): {len(calls)} calls, {len(puts)} puts")

    if not chains:
        raise ValueError(f"No valid option chains found for {ticker}")

    # Combine all chains
    full_chain = pd.concat(chains, ignore_index=True)

    # Select relevant columns
    columns_to_keep = [
        'ticker', 'option_type', 'strike', 'expiry',
        'bid', 'ask', 'impliedVolatility'
    ]

    # Handle missing columns
    for col in columns_to_keep:
        if col not in full_chain.columns:
            full_chain[col] = np.nan

    full_chain = full_chain[columns_to_keep]

    # Rename for consistency
    full_chain = full_chain.rename(columns={
        'impliedVolatility': 'implied_volatility'
    })

    # Filter valid quotes
    full_chain = full_chain[
        (full_chain['bid'] > 0) &
        (full_chain['ask'] > full_chain['bid']) &
        (full_chain['implied_volatility'].notna()) &
        (full_chain['implied_volatility'] > 0)
    ]

    print(f"\nFiltered to {len(full_chain)} valid option quotes")

    return full_chain


def main():
    parser = argparse.ArgumentParser(description='Fetch option chain data')
    parser.add_argument('--ticker', required=True, help='Stock ticker symbol')
    parser.add_argument('--output-dir', default='pricing/options_hedging/data',
                       help='Output directory')
    parser.add_argument('--min-days', type=int, default=7,
                       help='Minimum days to expiry (default: 7)')
    parser.add_argument('--max-days', type=int, default=730,
                       help='Maximum days to expiry (default: 730)')

    args = parser.parse_args()

    try:
        # Fetch option chain
        chain = fetch_option_chain(args.ticker, args.min_days, args.max_days)

        if chain.empty:
            print("Error: No valid option data found", file=sys.stderr)
            sys.exit(1)

        # Print summary
        print(f"\n=== Option Chain Summary: {args.ticker} ===")
        print(f"Total Quotes: {len(chain)}")
        print(f"Calls: {len(chain[chain['option_type'] == 'call'])}")
        print(f"Puts: {len(chain[chain['option_type'] == 'put'])}")

        expiries = chain['expiry'].unique()
        print(f"Expiries: {len(expiries)} ({expiries.min():.2f} to {expiries.max():.2f} years)")

        strikes = chain['strike'].unique()
        print(f"Strikes: {len(strikes)} (${strikes.min():.2f} to ${strikes.max():.2f})")

        # Save to CSV
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{args.ticker}_options.csv"
        chain.to_csv(output_file, index=False)

        print(f"\n✓ Saved option chain to {output_file}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

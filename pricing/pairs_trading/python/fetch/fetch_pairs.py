#!/usr/bin/env python3
"""
Fetch historical data for pairs trading.

Uses unified data_fetcher library (IBKR if available, yfinance fallback).

Usage:
    python fetch_pairs.py --ticker1 GLD --ticker2 GDX --days 252
"""

import argparse
import sys
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta

# Add lib to path
sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.data_fetcher import fetch_multiple_ohlcv, get_available_providers


def fetch_pair_data(ticker1: str, ticker2: str, days: int = 252) -> tuple:
    """Fetch historical data for a pair of tickers."""

    print(f"\n=== Fetching Pair Data ===\n")
    print(f"Ticker 1: {ticker1}")
    print(f"Ticker 2: {ticker2}")
    print(f"Lookback: {days} days")
    print(f"Available providers: {get_available_providers()}\n")

    # Map days to period
    if days <= 30:
        period = "1mo"
    elif days <= 90:
        period = "3mo"
    elif days <= 180:
        period = "6mo"
    elif days <= 365:
        period = "1y"
    elif days <= 730:
        period = "2y"
    else:
        period = "5y"

    # Fetch both tickers using batch download
    ohlcv_data = fetch_multiple_ohlcv([ticker1, ticker2], period=period, interval="1d")

    if ticker1 not in ohlcv_data or ticker2 not in ohlcv_data:
        raise ValueError(f"Failed to fetch data for {ticker1} or {ticker2}")

    ohlcv1 = ohlcv_data[ticker1]
    ohlcv2 = ohlcv_data[ticker2]

    # Create DataFrames from OHLCV
    df1 = pd.DataFrame({'date': pd.to_datetime(ohlcv1.dates), 'price': ohlcv1.close})
    df2 = pd.DataFrame({'date': pd.to_datetime(ohlcv2.dates), 'price': ohlcv2.close})

    # Merge on date
    df = pd.merge(df1, df2, on='date', suffixes=('_1', '_2'))

    print(f"✓ Downloaded {len(df)} observations")
    print(f"  {ticker1}: ${df['price_1'].iloc[-1]:.2f}")
    print(f"  {ticker2}: ${df['price_2'].iloc[-1]:.2f}")

    return df, ticker1, ticker2

def save_pair_data(df: pd.DataFrame, ticker1: str, ticker2: str):
    """Save pair data to CSV."""

    output_dir = Path(__file__).resolve().parent.parent.parent / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save combined data (per-pair filenames)
    pair_tag = f"{ticker1}_{ticker2}"
    output_file = output_dir / f"pair_data_{pair_tag}.csv"
    df.to_csv(output_file, index=False)

    # Save metadata
    metadata = pd.DataFrame([{
        'ticker1': ticker1,
        'ticker2': ticker2,
        'n_observations': len(df),
        'start_date': df['date'].iloc[0].strftime("%Y-%m-%d"),
        'end_date': df['date'].iloc[-1].strftime("%Y-%m-%d"),
        'price1_current': df['price_1'].iloc[-1],
        'price2_current': df['price_2'].iloc[-1],
    }])
    metadata.to_csv(output_dir / f"metadata_{pair_tag}.csv", index=False)

    print(f"\n✓ Data saved to: {output_file}")
    print(f"✓ Metadata saved to: {output_dir / f'metadata_{pair_tag}.csv'}")

def main():
    parser = argparse.ArgumentParser(
        description="Fetch historical data for pairs trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Classic pairs: Gold miners vs Gold
  python fetch_pairs.py --ticker1 GLD --ticker2 GDX

  # Tech stocks
  python fetch_pairs.py --ticker1 AAPL --ticker2 MSFT --days 365

  # Energy pair
  python fetch_pairs.py --ticker1 XLE --ticker2 USO
        """
    )

    parser.add_argument("--ticker1", type=str, required=True,
                       help="First ticker symbol")
    parser.add_argument("--ticker2", type=str, required=True,
                       help="Second ticker symbol")
    parser.add_argument("--days", type=int, default=252,
                       help="Lookback days (default: 252)")

    args = parser.parse_args()

    try:
        df, ticker1, ticker2 = fetch_pair_data(args.ticker1, args.ticker2, args.days)
        save_pair_data(df, ticker1, ticker2)

        # Quick stats
        corr = df['price_1'].corr(df['price_2'])
        print(f"\n=== Quick Stats ===")
        print(f"Correlation: {corr:.2%}")

        if corr > 0.8:
            print(f"→ High correlation, good candidate for pairs trading!")
        elif corr > 0.6:
            print(f"→ Moderate correlation, test cointegration")
        else:
            print(f"→ Low correlation, may not be a good pair")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

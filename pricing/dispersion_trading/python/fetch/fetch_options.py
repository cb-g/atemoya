#!/usr/bin/env python3
"""
Fetch options data for dispersion trading.

Usage:
    python fetch_options.py --index SPY --constituents AAPL,MSFT,GOOGL,AMZN,NVDA
"""

import argparse
import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import numpy as np

from lib.python.retry import retry_with_backoff

def fetch_implied_vol(ticker: str, days: int = 30) -> dict:
    """
    Fetch implied volatility for a ticker.

    Note: yfinance doesn't provide IV directly, so we calculate
    historical volatility as a proxy.
    """
    print(f"Fetching data for {ticker}...")

    # Download historical data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    data = retry_with_backoff(lambda: yf.download(
        ticker,
        start=start_date.strftime("%Y-%m-%d"),
        end=end_date.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=True
    ))

    if len(data) == 0:
        print(f"  Warning: No data for {ticker}")
        return None

    # Handle MultiIndex columns
    if isinstance(data.columns, pd.MultiIndex):
        close = data['Close'].iloc[:, 0] if isinstance(data['Close'], pd.DataFrame) else data['Close']
    else:
        close = data['Close']

    # Calculate returns
    returns = close.pct_change().dropna()

    # Calculate historical volatility (annualized)
    hist_vol = returns.std() * np.sqrt(252)

    # Get current price
    current_price = close.iloc[-1]

    return {
        'ticker': ticker,
        'spot': current_price,
        'implied_vol': hist_vol,  # Using HV as proxy
        'observations': len(returns)
    }

def main():
    parser = argparse.ArgumentParser(
        description="Fetch options data for dispersion trading"
    )

    parser.add_argument("--index", type=str, default="SPY",
                       help="Index ticker (default: SPY)")
    parser.add_argument("--constituents", type=str,
                       default="AAPL,MSFT,GOOGL,AMZN,NVDA",
                       help="Comma-separated constituent tickers")
    parser.add_argument("--days", type=int, default=30,
                       help="Lookback days (default: 30)")

    args = parser.parse_args()

    # Parse constituents
    constituents = [t.strip() for t in args.constituents.split(',')]

    print(f"\n=== Fetching Dispersion Data ===\n")
    print(f"Index: {args.index}")
    print(f"Constituents: {', '.join(constituents)}\n")

    # Fetch index data
    index_data = fetch_implied_vol(args.index, args.days)
    if index_data is None:
        print(f"Error: Failed to fetch index data")
        sys.exit(1)

    # Fetch constituent data
    constituent_data = []
    for ticker in constituents:
        data = fetch_implied_vol(ticker, args.days)
        if data is not None:
            constituent_data.append(data)

    if len(constituent_data) == 0:
        print("Error: No constituent data fetched")
        sys.exit(1)

    # Create output directory
    output_dir = Path(__file__).resolve().parent.parent.parent / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save index data
    index_df = pd.DataFrame([index_data])
    index_df.to_csv(output_dir / "index_data.csv", index=False)
    print(f"\n✓ Index data saved: {output_dir / 'index_data.csv'}")

    # Save constituent data
    constituents_df = pd.DataFrame(constituent_data)
    # Add equal weights
    constituents_df['weight'] = 1.0 / len(constituent_data)
    constituents_df.to_csv(output_dir / "constituents_data.csv", index=False)
    print(f"✓ Constituents data saved: {output_dir / 'constituents_data.csv'}")

    # Display summary
    print(f"\n=== Summary ===")
    print(f"\nIndex: {index_data['ticker']}")
    print(f"  Spot: ${index_data['spot']:.2f}")
    print(f"  IV: {index_data['implied_vol']*100:.2f}%")

    print(f"\nConstituents:")
    for data in constituent_data:
        print(f"  {data['ticker']}: Spot=${data['spot']:.2f}, IV={data['implied_vol']*100:.2f}%")

    # Calculate dispersion
    weighted_avg_iv = sum(d['implied_vol'] * (1.0/len(constituent_data)) for d in constituent_data)
    dispersion = weighted_avg_iv - index_data['implied_vol']

    print(f"\nWeighted Avg IV: {weighted_avg_iv*100:.2f}%")
    print(f"Dispersion Level: {dispersion*100:.2f}%")

    if dispersion > 0.05:
        print(f"\n→ Signal: LONG DISPERSION (buy stocks, sell index)")
    elif dispersion < -0.02:
        print(f"\n→ Signal: SHORT DISPERSION (sell stocks, buy index)")
    else:
        print(f"\n→ Signal: NEUTRAL")

if __name__ == "__main__":
    main()

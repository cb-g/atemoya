#!/usr/bin/env python3
"""
Fetch earnings calendar and stock data for earnings vol scanner.
"""

import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf
import pandas as pd
import argparse
from datetime import datetime, timedelta

from lib.python.retry import retry_with_backoff

def fetch_earnings_data(ticker: str, output_dir: Path):
    """Fetch earnings date and stock metrics."""

    stock = yf.Ticker(ticker)

    # Get stock info
    info = retry_with_backoff(lambda: stock.info)
    spot_price = info.get('currentPrice', info.get('regularMarketPrice', 0))

    # Get earnings date
    try:
        calendar = retry_with_backoff(lambda: stock.calendar)
        if calendar is not None:
            # Handle both DataFrame and dict/list formats
            if isinstance(calendar, dict) and 'Earnings Date' in calendar:
                earnings_date = calendar['Earnings Date']
                if isinstance(earnings_date, list) and len(earnings_date) > 0:
                    earnings_date = earnings_date[0]
                if isinstance(earnings_date, pd.Timestamp):
                    earnings_date_str = earnings_date.strftime('%Y-%m-%d')
                else:
                    earnings_date_str = str(earnings_date)
            elif hasattr(calendar, 'iloc') and 'Earnings Date' in calendar:
                earnings_date = calendar['Earnings Date'].iloc[0]
                if isinstance(earnings_date, pd.Timestamp):
                    earnings_date_str = earnings_date.strftime('%Y-%m-%d')
                else:
                    earnings_date_str = str(earnings_date)
            else:
                earnings_date_str = "Unknown"
        else:
            earnings_date_str = "Unknown"
    except (KeyError, IndexError, AttributeError, TypeError) as e:
        # Calendar data unavailable or malformed
        earnings_date_str = "Unknown"

    # Calculate days to earnings
    if earnings_date_str != "Unknown":
        try:
            earn_dt = datetime.strptime(earnings_date_str, '%Y-%m-%d')
            days_to_earnings = (earn_dt - datetime.now()).days
        except ValueError:
            # Invalid date format
            days_to_earnings = 0
    else:
        days_to_earnings = 0

    # Get 30-day average volume
    hist = retry_with_backoff(lambda: stock.history(period='1mo'))
    avg_volume_30d = hist['Volume'].mean() if len(hist) > 0 else 0

    # Save earnings data
    earnings_data = pd.DataFrame([{
        'ticker': ticker,
        'earnings_date': earnings_date_str,
        'days_to_earnings': days_to_earnings,
        'spot_price': spot_price,
        'avg_volume_30d': avg_volume_30d
    }])

    earnings_file = output_dir / f"{ticker}_earnings.csv"
    earnings_data.to_csv(earnings_file, index=False)

    print(f"✓ Earnings data saved: {earnings_file}")
    print(f"  Date: {earnings_date_str}")
    print(f"  Days to Earnings: {days_to_earnings}")
    print(f"  Spot: ${spot_price:.2f}")
    print(f"  Avg Volume (30d): {avg_volume_30d:,.0f}")

    # Fetch price history for realized vol calculation
    hist_90d = retry_with_backoff(lambda: stock.history(period='3mo'))
    if len(hist_90d) > 0:
        prices = hist_90d[['Close']].reset_index()
        prices.columns = ['date', 'price']

        prices_file = output_dir / f"{ticker}_prices.csv"
        prices.to_csv(prices_file, index=False)
        print(f"✓ Price history saved: {prices_file} ({len(prices)} days)")

def main():
    parser = argparse.ArgumentParser(description='Fetch earnings data')
    parser.add_argument('--ticker', type=str, required=True, help='Stock ticker')
    parser.add_argument('--output-dir', type=str, default='pricing/earnings_vol/data',
                       help='Output directory')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nFetching earnings data for {args.ticker}...")
    fetch_earnings_data(args.ticker, output_dir)

    print(f"\n✅ Data fetch complete for {args.ticker}")

if __name__ == "__main__":
    main()

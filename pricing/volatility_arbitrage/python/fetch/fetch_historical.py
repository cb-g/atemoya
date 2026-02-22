#!/usr/bin/env python3
"""
Fetch historical OHLC data for realized volatility calculation.

Uses unified data_fetcher (IBKR if available, yfinance fallback).
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd

# Add lib to path
sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.data_fetcher import fetch_ohlcv, get_available_providers


def fetch_historical_ohlc(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch daily OHLC data

    Uses unified data_fetcher (IBKR if available, yfinance fallback).

    Args:
        ticker: Stock ticker
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume
    """
    # Calculate period from dates
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days

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

    ohlcv = fetch_ohlcv(ticker, period=period, interval="1d")

    if ohlcv is None or len(ohlcv) == 0:
        raise ValueError(f"No data returned for {ticker}")

    # Create DataFrame
    dates = pd.to_datetime(ohlcv.dates)
    df = pd.DataFrame({
        'timestamp': dates.astype(int) / 10**9,
        'open': ohlcv.open,
        'high': ohlcv.high,
        'low': ohlcv.low,
        'close': ohlcv.close,
        'volume': ohlcv.volume,
    })

    # Filter to date range
    mask = (dates >= start_date) & (dates <= end_date)
    df = df[mask].reset_index(drop=True)

    return df


def main():
    parser = argparse.ArgumentParser(description='Fetch historical OHLC data')
    parser.add_argument('--ticker', required=True, help='Stock ticker')
    parser.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='End date (YYYY-MM-DD)')
    parser.add_argument('--lookback-days', type=int, default=252,
                        help='Lookback period in days (default: 252 = 1 year)')
    parser.add_argument('--data-dir', default='pricing/volatility_arbitrage/data',
                        help='Data directory')

    args = parser.parse_args()

    try:
        # Determine date range
        if args.end_date:
            end_date = args.end_date
        else:
            end_date = datetime.now().strftime('%Y-%m-%d')

        if args.start_date:
            start_date = args.start_date
        else:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            start_dt = end_dt - timedelta(days=args.lookback_days)
            start_date = start_dt.strftime('%Y-%m-%d')

        print(f"Fetching OHLC data for {args.ticker}")
        print(f"Available providers: {get_available_providers()}")
        print(f"Date range: {start_date} to {end_date}")

        # Fetch data
        df = fetch_historical_ohlc(args.ticker, start_date, end_date)

        print(f"Retrieved {len(df)} trading days")
        print(f"Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

        # Save to CSV
        data_dir = Path(args.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        output_file = data_dir / f"{args.ticker}_ohlc.csv"
        df.to_csv(output_file, index=False)

        print(f"Saved to {output_file}")

        # Also save spot price and dividend yield for underlying data file
        spot_price = df['close'].iloc[-1]

        # Fetch dividend data using data_fetcher
        from lib.python.data_fetcher import fetch_dividends
        div_data = fetch_dividends(args.ticker)

        if div_data is not None and div_data.dividend_yield > 0:
            dividend_yield = div_data.dividend_yield
        elif div_data is not None and div_data.annual_dividend > 0:
            dividend_yield = div_data.annual_dividend / spot_price
        else:
            dividend_yield = 0.0

        # Create underlying data file
        underlying_df = pd.DataFrame({
            'ticker': [args.ticker],
            'spot_price': [spot_price],
            'dividend_yield': [dividend_yield]
        })

        underlying_file = data_dir / f"{args.ticker}_underlying.csv"
        underlying_df.to_csv(underlying_file, index=False)

        print(f"Saved underlying data to {underlying_file}")
        print(f"  Spot: ${spot_price:.2f}")
        print(f"  Dividend Yield: {dividend_yield*100:.2f}%")

        print("\n✓ Successfully fetched historical data")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

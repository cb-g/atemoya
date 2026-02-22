#!/usr/bin/env python3
"""
Fetch historical prices for momentum calculation.

Fetches both stock and market (SPY) prices for beta/alpha calculations.
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

def fetch_historical_prices(ticker: str, days: int, output_dir: Path):
    """Fetch historical prices for momentum calculation."""

    print(f"\nFetching {days} days of price history for {ticker}...")

    # Calculate start date
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    try:
        # Fetch stock data
        stock = yf.Ticker(ticker)
        stock_data = retry_with_backoff(lambda: stock.history(start=start_date, end=end_date))

        if len(stock_data) == 0:
            print(f"  ✗ No price data available for {ticker}")
            return None

        # Fetch SPY (market) data
        spy = yf.Ticker("SPY")
        spy_data = retry_with_backoff(lambda: spy.history(start=start_date, end=end_date))

        if len(spy_data) == 0:
            print(f"  ✗ No market data available")
            return None

        # Extract close prices
        stock_prices = stock_data[['Close']].reset_index()
        stock_prices.columns = ['date', 'price']
        stock_prices['date'] = stock_prices['date'].dt.strftime('%Y-%m-%d')

        spy_prices = spy_data[['Close']].reset_index()
        spy_prices.columns = ['date', 'price']
        spy_prices['date'] = spy_prices['date'].dt.strftime('%Y-%m-%d')

        # Save stock prices
        stock_file = output_dir / f"{ticker}_prices.csv"
        stock_prices.to_csv(stock_file, index=False)

        # Save market prices
        market_file = output_dir / f"SPY_prices.csv"
        spy_prices.to_csv(market_file, index=False)

        # Calculate basic metrics
        current_price = stock_prices['price'].iloc[-1]
        week_ago = stock_prices['price'].iloc[-5] if len(stock_prices) >= 5 else current_price
        month_ago = stock_prices['price'].iloc[-21] if len(stock_prices) >= 21 else current_price
        three_months_ago = stock_prices['price'].iloc[-63] if len(stock_prices) >= 63 else current_price
        high_52w = stock_prices['price'].max()

        return_1w = (current_price - week_ago) / week_ago * 100
        return_1m = (current_price - month_ago) / month_ago * 100
        return_3m = (current_price - three_months_ago) / three_months_ago * 100
        pct_from_high = (current_price - high_52w) / high_52w * 100

        print(f"\n✓ Price data saved:")
        print(f"  Stock: {stock_file}")
        print(f"  Market: {market_file}")
        print(f"  {len(stock_prices)} trading days")
        print(f"\nQuick metrics:")
        print(f"  Current price: ${current_price:.2f}")
        print(f"  1W return: {return_1w:+.2f}%")
        print(f"  1M return: {return_1m:+.2f}%")
        print(f"  3M return: {return_3m:+.2f}%")
        print(f"  From 52W high: {pct_from_high:+.2f}%")

        return {
            'stock_prices': stock_prices,
            'market_prices': spy_prices,
            'current_price': current_price,
            'return_1w': return_1w,
            'return_1m': return_1m,
            'return_3m': return_3m,
            'pct_from_52w_high': pct_from_high,
        }

    except Exception as e:
        print(f"  ✗ Error fetching prices: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Fetch historical prices')
    parser.add_argument('--ticker', type=str, required=True, help='Stock ticker')
    parser.add_argument('--days', type=int, default=252, help='Days of history (default: 252 = 1 year)')
    parser.add_argument('--output-dir', type=str, default='pricing/skew_verticals/data',
                       help='Output directory')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fetch_historical_prices(args.ticker, args.days, output_dir)

if __name__ == "__main__":
    main()

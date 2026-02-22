#!/usr/bin/env python3
"""
Fetch underlying stock data (spot price, historical volatility, dividend yield).

Uses unified data_fetcher (IBKR if available, yfinance fallback).
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# Add lib to path
sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.data_fetcher import fetch_ohlcv, fetch_dividends, get_available_providers


def fetch_underlying_data(ticker: str, lookback_days: int = 252) -> dict:
    """
    Fetch underlying stock data.

    Uses unified data_fetcher (IBKR if available, yfinance fallback).

    Args:
        ticker: Stock ticker symbol
        lookback_days: Number of days to look back for historical data

    Returns:
        Dictionary with ticker, spot_price, dividend_yield, historical_vol
    """
    print(f"Fetching underlying data for {ticker}...")
    print(f"Available providers: {get_available_providers()}")

    # Map lookback days to period
    if lookback_days <= 30:
        period = "1mo"
    elif lookback_days <= 90:
        period = "3mo"
    elif lookback_days <= 180:
        period = "6mo"
    elif lookback_days <= 365:
        period = "1y"
    elif lookback_days <= 730:
        period = "2y"
    else:
        period = "5y"

    # Fetch OHLCV data
    ohlcv = fetch_ohlcv(ticker, period=period, interval="1d")

    if ohlcv is None or len(ohlcv) == 0:
        raise ValueError(f"No historical data found for {ticker}")

    # Current spot price
    spot_price = float(ohlcv.close[-1])

    # Calculate historical volatility (annualized)
    closes = pd.Series(ohlcv.close)
    returns = closes.pct_change().dropna()

    # Use last N days
    recent_returns = returns.tail(lookback_days)
    hist_vol = float(recent_returns.std() * np.sqrt(252))  # Annualize

    # Fetch dividend data
    div_data = fetch_dividends(ticker)

    if div_data is not None and div_data.dividend_yield > 0:
        div_yield = div_data.dividend_yield
    elif div_data is not None and div_data.annual_dividend > 0:
        div_yield = div_data.annual_dividend / spot_price
    else:
        div_yield = 0.0

    result = {
        'ticker': ticker,
        'spot_price': spot_price,
        'dividend_yield': div_yield,
        'historical_vol': hist_vol,
        'last_updated': datetime.now().strftime('%Y-%m-%d'),
        'lookback_days': lookback_days
    }

    return result


def save_underlying_csv(data: dict, output_file: Path):
    """Save underlying data to CSV format for OCaml consumption"""
    # CSV format: ticker, spot_price, dividend_yield
    df = pd.DataFrame([{
        'ticker': data['ticker'],
        'spot_price': data['spot_price'],
        'dividend_yield': data['dividend_yield']
    }])

    df.to_csv(output_file, index=False)
    print(f"Saved underlying data to {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Fetch underlying stock data')
    parser.add_argument('--ticker', required=True, help='Stock ticker symbol')
    parser.add_argument('--output-dir', default='pricing/options_hedging/data',
                       help='Output directory')
    parser.add_argument('--lookback', type=int, default=252,
                       help='Lookback days for volatility calculation (default: 252)')

    args = parser.parse_args()

    try:
        # Fetch data
        data = fetch_underlying_data(args.ticker, args.lookback)

        # Print summary
        print(f"\n=== Underlying Data: {args.ticker} ===")
        print(f"Spot Price: ${data['spot_price']:.2f}")
        print(f"Dividend Yield: {data['dividend_yield']*100:.2f}%")
        print(f"Historical Vol: {data['historical_vol']*100:.2f}%")
        print(f"Last Updated: {data['last_updated']}")

        # Save to CSV
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{args.ticker}_underlying.csv"
        save_underlying_csv(data, output_file)

        print(f"\n✓ Successfully fetched underlying data for {args.ticker}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

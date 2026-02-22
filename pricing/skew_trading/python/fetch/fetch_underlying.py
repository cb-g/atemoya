#!/usr/bin/env python3
"""
Fetch underlying asset data for skew trading.

Uses unified data_fetcher (IBKR if available, yfinance fallback).

Downloads:
- Current spot price
- Dividend yield
- Historical prices

Outputs:
- {TICKER}_underlying.json
- {TICKER}_prices.csv
"""

import argparse
import json
import sys
from pathlib import Path
import pandas as pd

# Add lib to path
sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.data_fetcher import fetch_ohlcv, fetch_dividends, get_available_providers


def fetch_underlying_data(ticker: str, lookback_days: int = 252) -> dict:
    """
    Fetch underlying asset data.

    Uses unified data_fetcher (IBKR if available, yfinance fallback).

    Args:
        ticker: Stock ticker symbol
        lookback_days: Historical data window

    Returns:
        Dictionary with ticker, spot_price, dividend_yield
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

    spot_price = float(ohlcv.close[-1])

    # Fetch dividend data (if available)
    div_data = fetch_dividends(ticker)

    if div_data is not None and div_data.dividend_yield > 0:
        dividend_yield = div_data.dividend_yield
    else:
        # Fall back to calculating from history if available
        dividend_yield = 0.0
        if div_data is not None and div_data.annual_dividend > 0:
            dividend_yield = div_data.annual_dividend / spot_price

    print(f"  Spot Price: ${spot_price:.2f}")
    print(f"  Dividend Yield: {dividend_yield*100:.2f}%")
    print(f"  Historical Observations: {len(ohlcv)}")

    return {
        'ticker': ticker,
        'spot_price': spot_price,
        'dividend_yield': dividend_yield
    }


def save_underlying_json(data: dict, output_dir: Path):
    """Save underlying data to JSON."""
    output_file = output_dir / f"{data['ticker']}_underlying.json"

    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✓ Saved: {output_file}")


def save_price_history(ticker: str, output_dir: Path, lookback_days: int = 252):
    """Save historical prices to CSV."""
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

    ohlcv = fetch_ohlcv(ticker, period=period, interval="1d")

    if ohlcv is None or len(ohlcv) == 0:
        print(f"Warning: No price history found for {ticker}")
        return

    # Prepare CSV: timestamp, close_price
    dates = pd.to_datetime(ohlcv.dates)
    price_data = pd.DataFrame({
        'timestamp': dates.astype(int) // 10**9,  # Unix timestamp
        'close': ohlcv.close
    })

    output_file = output_dir / f"{ticker}_prices.csv"
    price_data.to_csv(output_file, index=False)

    print(f"✓ Saved: {output_file} ({len(price_data)} observations)")


def main():
    parser = argparse.ArgumentParser(description='Fetch underlying asset data for skew trading')
    parser.add_argument('--ticker', type=str, required=True,
                        help='Stock ticker symbol (e.g., SPY, AAPL)')
    parser.add_argument('--output-dir', type=str, default='pricing/skew_trading/data',
                        help='Output directory (default: pricing/skew_trading/data)')
    parser.add_argument('--lookback', type=int, default=252,
                        help='Lookback days for historical data (default: 252)')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Fetch underlying data
    underlying_data = fetch_underlying_data(args.ticker, args.lookback)

    # Save JSON
    save_underlying_json(underlying_data, output_dir)

    # Save price history
    save_price_history(args.ticker, output_dir, args.lookback)

    print(f"\n✓ Underlying data fetched for {args.ticker}")


if __name__ == '__main__':
    main()

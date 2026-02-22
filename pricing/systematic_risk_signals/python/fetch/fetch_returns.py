#!/usr/bin/env python3
"""
Fetch historical returns data for systematic risk signal analysis.

Uses the unified data_fetcher library to get OHLCV data and compute
daily returns for the specified tickers.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from lib.python.data_fetcher import fetch_ohlcv, fetch_multiple_ohlcv, get_available_providers


def compute_returns(prices):
    """Compute simple returns from price series."""
    returns = []
    for i in range(1, len(prices)):
        if prices[i-1] != 0:
            ret = (prices[i] - prices[i-1]) / prices[i-1]
            returns.append(ret)
        else:
            returns.append(0.0)
    return returns


def fetch_returns_data(tickers: list[str], lookback_days: int = 252) -> dict:
    """
    Fetch historical returns data for multiple tickers.

    Args:
        tickers: List of ticker symbols
        lookback_days: Number of trading days to look back

    Returns:
        Dictionary with assets data ready for JSON output
    """
    print(f"Fetching data for {len(tickers)} tickers...")
    print(f"Available providers: {get_available_providers()}")

    # Determine period string - add buffer for returns calculation
    # 252 trading days ≈ 1 year, add extra for weekends/holidays
    calendar_days = int(lookback_days * 1.5)

    if calendar_days <= 30:
        period = "1mo"
    elif calendar_days <= 90:
        period = "3mo"
    elif calendar_days <= 180:
        period = "6mo"
    elif calendar_days <= 365:
        period = "1y"
    elif calendar_days <= 730:
        period = "2y"
    else:
        period = "5y"

    # Fetch data for all tickers
    all_data = fetch_multiple_ohlcv(tickers, period=period, interval="1d")

    assets = []
    common_dates = None

    for ticker in tickers:
        if ticker not in all_data or all_data[ticker] is None:
            print(f"  Warning: No data for {ticker}")
            continue

        ohlcv = all_data[ticker]
        if len(ohlcv) == 0:
            print(f"  Warning: Empty data for {ticker}")
            continue

        # Get dates and closing prices from OHLCV dataclass
        dates = ohlcv.dates
        closes = ohlcv.close

        # Compute returns (skip first date since we need previous close)
        returns = compute_returns(closes)
        dates = dates[1:]  # Align with returns

        if len(returns) < 20:
            print(f"  Warning: Insufficient data for {ticker} ({len(returns)} days)")
            continue

        # Track common dates
        date_set = set(dates)
        if common_dates is None:
            common_dates = date_set
        else:
            common_dates = common_dates.intersection(date_set)

        assets.append({
            'ticker': ticker,
            'returns': returns,
            'dates': dates,
            'n_obs': len(returns)
        })

        print(f"  {ticker}: {len(returns)} observations")

    # Align all assets to common dates
    common_dates_sorted = []
    if common_dates and len(assets) > 1:
        common_dates_sorted = sorted(list(common_dates))

        for asset in assets:
            date_to_return = dict(zip(asset['dates'], asset['returns']))
            aligned_returns = [date_to_return.get(d, 0.0) for d in common_dates_sorted]
            asset['returns'] = aligned_returns
            asset['dates'] = common_dates_sorted
            asset['n_obs'] = len(aligned_returns)

        print(f"\nAligned to {len(common_dates_sorted)} common trading days")
    elif len(assets) == 1:
        common_dates_sorted = assets[0]['dates']

    return {
        'assets': assets,
        'n_assets': len(assets),
        'n_observations': len(common_dates_sorted) if common_dates_sorted else 0,
        'fetch_timestamp': datetime.now().isoformat(),
        'tickers': [a['ticker'] for a in assets]
    }


def main():
    parser = argparse.ArgumentParser(
        description='Fetch historical returns data for systematic risk analysis'
    )
    parser.add_argument(
        '--tickers', '-t',
        required=True,
        help='Comma-separated list of ticker symbols'
    )
    parser.add_argument(
        '--lookback', '-l',
        type=int,
        default=252,
        help='Number of trading days to look back (default: 252)'
    )
    parser.add_argument(
        '--output', '-o',
        default='pricing/systematic_risk_signals/data/returns.json',
        help='Output file path'
    )

    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',')]

    # Fetch data
    data = fetch_returns_data(tickers, args.lookback)

    if data['n_assets'] == 0:
        print("Error: No data fetched for any ticker")
        sys.exit(1)

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\nData written to {output_path}")
    print(f"  Assets: {data['n_assets']}")
    print(f"  Observations: {data['n_observations']}")


if __name__ == '__main__':
    main()

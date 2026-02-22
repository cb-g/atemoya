#!/usr/bin/env python3
"""
Fetch historical price data for regime detection.

Uses unified data_fetcher (IBKR if available, yfinance fallback).

Usage:
    python fetch_prices.py --ticker SPY --years 5
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.retry import retry_with_backoff
from lib.python.data_fetcher import fetch_ohlcv, get_available_providers


def fetch_prices(ticker: str, years: int = 5) -> dict:
    """Fetch historical adjusted close prices.

    Uses unified data_fetcher (IBKR if available, yfinance fallback).
    """
    providers = get_available_providers()
    print(f"Fetching {ticker} ({years}y history)... (providers: {', '.join(providers)})")

    # Map years to period string
    if years <= 1:
        period = "1y"
    elif years <= 2:
        period = "2y"
    elif years <= 5:
        period = "5y"
    else:
        period = "max"

    ohlcv = fetch_ohlcv(ticker, period=period, interval="1d")

    if ohlcv is not None and len(ohlcv.dates) > 0:
        import pandas as pd
        dates_ts = pd.to_datetime(ohlcv.dates)
        dates = [d.strftime("%Y-%m-%d") for d in dates_ts]
        prices = [round(float(p), 4) for p in ohlcv.close]
        print(f"Retrieved {len(dates)} trading days")
    else:
        # Fallback: direct yfinance if data_fetcher returned nothing
        print("  data_fetcher returned no data, trying yfinance directly...")
        import yfinance as yf
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years * 365 + 30)
        stock = yf.Ticker(ticker)
        hist = retry_with_backoff(lambda: stock.history(start=start_date, end=end_date, auto_adjust=True))
        if hist.empty:
            raise ValueError(f"No data returned for {ticker}")
        dates = [d.strftime("%Y-%m-%d") for d in hist.index]
        prices = [round(p, 4) for p in hist['Close'].tolist()]
        print(f"Retrieved {len(dates)} trading days (yfinance direct)")

    return {
        "ticker": ticker,
        "start_date": dates[0],
        "end_date": dates[-1],
        "trading_days": len(dates),
        "dates": dates,
        "prices": prices,
        "fetch_date": datetime.now().isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch price data for regime detection")
    parser.add_argument("--ticker", default="SPY", help="Ticker symbol (default: SPY)")
    parser.add_argument("--years", type=int, default=5, help="Years of history (default: 5)")
    parser.add_argument("--output", "-o", help="Output JSON file path")

    args = parser.parse_args()

    # Fetch data
    data = fetch_prices(args.ticker, args.years)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_dir = Path(__file__).parent.parent.parent / "data"
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"{args.ticker.lower()}_prices.json"

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Saved to {output_path}")
    print(f"  Period: {data['start_date']} to {data['end_date']}")
    print(f"  Trading days: {data['trading_days']}")


if __name__ == "__main__":
    main()

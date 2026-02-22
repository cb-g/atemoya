#!/usr/bin/env python3
"""
Fetch market data for liquidity analysis.
Data fetching only - computations are done in OCaml.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import yfinance as yf

from lib.python.retry import retry_with_backoff


def fetch_ticker_data(ticker: str, period: str = "3mo") -> dict | None:
    """Fetch OHLCV data for a single ticker."""
    try:
        stock = yf.Ticker(ticker)
        hist = retry_with_backoff(lambda: stock.history(period=period))

        if hist.empty or len(hist) < 30:
            print(f"Warning: Insufficient data for {ticker}", file=sys.stderr)
            return None

        info = retry_with_backoff(lambda: stock.info)

        # Convert to lists for JSON serialization
        data = {
            "ticker": ticker,
            "shares_outstanding": info.get("sharesOutstanding", 0),
            "market_cap": info.get("marketCap", 0),
            "dates": [d.strftime("%Y-%m-%d") for d in hist.index],
            "open": hist["Open"].tolist(),
            "high": hist["High"].tolist(),
            "low": hist["Low"].tolist(),
            "close": hist["Close"].tolist(),
            "volume": hist["Volume"].tolist(),
        }

        return data

    except Exception as e:
        print(f"Error fetching {ticker}: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Fetch liquidity data")
    parser.add_argument("--ticker", help="Single ticker")
    parser.add_argument("--tickers", help="Comma-separated tickers")
    parser.add_argument("--data-dir", default="pricing/liquidity/data")
    parser.add_argument("--period", default="3mo", help="Data period")

    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Determine tickers
    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
    else:
        tickers_file = data_dir / "tickers.json"
        if tickers_file.exists():
            with open(tickers_file) as f:
                tickers = json.load(f).get("tickers", [])
        else:
            tickers = ["NVDA", "SPY", "BRK-B", "TAC", "BWEN", "SMCI", "SFM"]

    print(f"Fetching data for {len(tickers)} tickers...")

    results = []
    for ticker in tickers:
        print(f"  {ticker}...", end=" ", flush=True)
        data = fetch_ticker_data(ticker, args.period)
        if data:
            results.append(data)
            print("done")
        else:
            print("failed")

    # Save to data directory
    output_file = data_dir / "market_data.json"
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "period": args.period,
            "tickers": results,
        }, f, indent=2)

    print(f"\nData saved to: {output_file}")


if __name__ == "__main__":
    main()

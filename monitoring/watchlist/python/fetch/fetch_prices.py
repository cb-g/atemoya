#!/usr/bin/env python3
"""
Fetch market prices for portfolio positions.

Uses unified data_fetcher (IBKR if available, yfinance fallback).

Usage:
    python fetch_prices.py [--portfolio path/to/portfolio.json] [--output path/to/prices.json]
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from lib.python.data_fetcher import fetch_ohlcv, fetch_extended_info, get_available_providers


def load_portfolio(filepath: Path) -> list[str]:
    """Load portfolio and extract tickers."""
    with open(filepath) as f:
        data = json.load(f)
    return [p["ticker"] for p in data.get("positions", [])]


def fetch_price_data(symbol: str) -> dict:
    """Fetch price data for a single ticker."""
    try:
        # Fetch OHLCV data
        ohlcv = fetch_ohlcv(symbol, period="1mo", interval="1d")

        if ohlcv is None or len(ohlcv) < 2:
            return {"symbol": symbol, "error": "Insufficient historical data"}

        prices = ohlcv.close
        current_price = float(prices[-1])
        prev_close = float(prices[-2]) if len(prices) > 1 else current_price

        # Price changes
        change_1d_pct = ((current_price / prev_close) - 1) * 100 if prev_close > 0 else 0
        change_5d_pct = ((current_price / prices[-5]) - 1) * 100 if len(prices) >= 5 else change_1d_pct

        # 52-week data from extended info
        ext_info = fetch_extended_info(symbol)
        if ext_info:
            high_52w = ext_info.fifty_two_week_high or current_price
            low_52w = ext_info.fifty_two_week_low or current_price
        else:
            high_52w = current_price
            low_52w = current_price

        return {
            "symbol": symbol,
            "current_price": current_price,
            "prev_close": prev_close,
            "change_1d_pct": change_1d_pct,
            "change_5d_pct": change_5d_pct,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "fetch_time": datetime.now().isoformat(),
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "error": str(e),
            "fetch_time": datetime.now().isoformat(),
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch market prices for portfolio")
    parser.add_argument(
        "--portfolio",
        default=Path(__file__).parent.parent / "data" / "portfolio.json",
        type=Path,
        help="Path to portfolio JSON",
    )
    parser.add_argument(
        "--output",
        default=Path(__file__).parent.parent / "data" / "prices.json",
        type=Path,
        help="Output path for price data",
    )

    args = parser.parse_args()

    if not args.portfolio.exists():
        print(f"Error: Portfolio not found at {args.portfolio}", file=sys.stderr)
        sys.exit(1)

    tickers = load_portfolio(args.portfolio)

    if not tickers:
        print("No positions in portfolio")
        sys.exit(0)

    print(f"Available providers: {get_available_providers()}")
    print(f"Fetching prices for {len(tickers)} position(s)...")

    results = []
    for symbol in tickers:
        print(f"  {symbol}...", end=" ", flush=True)

        data = fetch_price_data(symbol)

        if data.get("error"):
            print(f"ERROR: {data['error']}")
        else:
            change = data["change_1d_pct"]
            sign = "+" if change >= 0 else ""
            print(f"${data['current_price']:.2f} ({sign}{change:.1f}%)")

        results.append(data)

    # Save results
    output = {
        "fetch_time": datetime.now().isoformat(),
        "tickers": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nPrices saved to {args.output}")

    # Count errors
    errors = [r for r in results if r.get("error")]
    if errors:
        print(f"  ({len(errors)} error(s))")


if __name__ == "__main__":
    main()

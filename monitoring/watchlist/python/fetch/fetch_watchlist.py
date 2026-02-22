#!/usr/bin/env python3
"""
Fetch data for all tickers in the watchlist.

Uses unified data_fetcher (IBKR if available, yfinance fallback).

This script:
1. Reads the watchlist JSON
2. Fetches current price, volume, and technical data for each ticker
3. Outputs a combined data file for the OCaml signal detector

Usage:
    python fetch_watchlist.py [--watchlist path/to/watchlist.json]
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

# Add lib to path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from lib.python.data_fetcher import fetch_ohlcv, fetch_extended_info, get_available_providers


def load_watchlist(filepath: Path) -> dict:
    """Load watchlist configuration."""
    with open(filepath) as f:
        return json.load(f)


def calculate_obv(prices: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    """Calculate On-Balance Volume."""
    obv = np.zeros(len(prices))
    obv[0] = volumes[0]

    for i in range(1, len(prices)):
        if prices[i] > prices[i - 1]:
            obv[i] = obv[i - 1] + volumes[i]
        elif prices[i] < prices[i - 1]:
            obv[i] = obv[i - 1] - volumes[i]
        else:
            obv[i] = obv[i - 1]

    return obv


def calculate_rsi(prices: np.ndarray, period: int = 14) -> float:
    """Calculate RSI."""
    if len(prices) < period + 1:
        return 50.0

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def detect_obv_divergence(prices: np.ndarray, obv: np.ndarray, lookback: int = 20) -> str:
    """
    Detect OBV divergence.

    Returns:
        "bullish" - price making lower lows but OBV making higher lows
        "bearish" - price making higher highs but OBV making lower highs
        "none" - no divergence
    """
    if len(prices) < lookback:
        return "none"

    recent_prices = prices[-lookback:]
    recent_obv = obv[-lookback:]

    # Find local min/max in first and second half
    mid = lookback // 2

    price_low1 = np.min(recent_prices[:mid])
    price_low2 = np.min(recent_prices[mid:])
    obv_low1 = np.min(recent_obv[:mid])
    obv_low2 = np.min(recent_obv[mid:])

    price_high1 = np.max(recent_prices[:mid])
    price_high2 = np.max(recent_prices[mid:])
    obv_high1 = np.max(recent_obv[:mid])
    obv_high2 = np.max(recent_obv[mid:])

    # Bullish divergence: price lower low, OBV higher low
    if price_low2 < price_low1 and obv_low2 > obv_low1:
        return "bullish"

    # Bearish divergence: price higher high, OBV lower high
    if price_high2 > price_high1 and obv_high2 < obv_high1:
        return "bearish"

    return "none"


def fetch_ticker_data(symbol: str) -> dict:
    """Fetch comprehensive data for a single ticker."""
    try:
        # Fetch OHLCV data (3 months for technical analysis)
        ohlcv = fetch_ohlcv(symbol, period="3mo", interval="1d")

        if ohlcv is None or len(ohlcv) < 5:
            return {"symbol": symbol, "error": "Insufficient historical data"}

        prices = np.array(ohlcv.close)
        volumes = np.array(ohlcv.volume)
        current_price = float(prices[-1])
        prev_close = float(prices[-2]) if len(prices) > 1 else current_price

        # Volume analysis
        avg_volume_20d = float(np.mean(volumes[-20:])) if len(volumes) >= 20 else float(np.mean(volumes))
        current_volume = float(volumes[-1])
        volume_ratio = current_volume / avg_volume_20d if avg_volume_20d > 0 else 1.0

        # OBV analysis
        obv = calculate_obv(prices, volumes)
        obv_divergence = detect_obv_divergence(prices, obv)

        # RSI
        rsi = calculate_rsi(prices)

        # Price change
        price_change_1d = ((current_price / prev_close) - 1) * 100 if prev_close > 0 else 0
        price_change_5d = ((current_price / prices[-5]) - 1) * 100 if len(prices) >= 5 else 0
        price_change_20d = ((current_price / prices[-20]) - 1) * 100 if len(prices) >= 20 else 0

        # Get extended info for 52-week data and market cap
        ext_info = fetch_extended_info(symbol)
        if ext_info:
            high_52w = ext_info.fifty_two_week_high or current_price
            low_52w = ext_info.fifty_two_week_low or current_price
            market_cap = int(ext_info.market_cap) if ext_info.market_cap else 0
            name = symbol  # ExtendedTickerInfo doesn't have name
        else:
            high_52w = current_price
            low_52w = current_price
            market_cap = 0
            name = symbol

        range_position = (current_price - low_52w) / (high_52w - low_52w) if high_52w != low_52w else 0.5

        return {
            "symbol": symbol,
            "name": name,
            "current_price": current_price,
            "prev_close": prev_close,
            "price_change_1d_pct": price_change_1d,
            "price_change_5d_pct": price_change_5d,
            "price_change_20d_pct": price_change_20d,
            "volume": current_volume,
            "avg_volume_20d": avg_volume_20d,
            "volume_ratio": volume_ratio,
            "volume_surge": volume_ratio > 2.0,
            "obv_current": float(obv[-1]),
            "obv_divergence": obv_divergence,
            "rsi": rsi,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "range_position_52w": range_position,
            "market_cap": market_cap,
            "fetch_time": datetime.now().isoformat(),
            "error": None,
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "error": str(e),
            "fetch_time": datetime.now().isoformat(),
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch data for watchlist tickers")
    parser.add_argument(
        "--watchlist",
        default=Path(__file__).parent.parent / "data" / "watchlist.json",
        type=Path,
        help="Path to watchlist JSON",
    )
    parser.add_argument(
        "--output",
        default=Path(__file__).parent.parent / "data" / "ticker_data.json",
        type=Path,
        help="Output path for fetched data",
    )

    args = parser.parse_args()

    if not args.watchlist.exists():
        print(f"Error: Watchlist not found at {args.watchlist}", file=sys.stderr)
        sys.exit(1)

    watchlist = load_watchlist(args.watchlist)
    tickers = watchlist.get("tickers", [])

    if not tickers:
        print("No tickers in watchlist")
        sys.exit(0)

    print(f"Available providers: {get_available_providers()}")
    print(f"Fetching data for {len(tickers)} ticker(s)...")

    results = []
    for entry in tickers:
        symbol = entry["symbol"]
        print(f"  Fetching {symbol}...", end=" ", flush=True)

        data = fetch_ticker_data(symbol)
        data["watchlist_entry"] = entry  # Include original watchlist config

        if data.get("error"):
            print(f"ERROR: {data['error']}")
        else:
            print(f"${data['current_price']:.2f} (vol ratio: {data['volume_ratio']:.1f}x)")

        results.append(data)

    # Save results
    output = {
        "fetch_time": datetime.now().isoformat(),
        "ticker_count": len(results),
        "tickers": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nData saved to {args.output}")

    # Summary
    errors = [r for r in results if r.get("error")]
    volume_surges = [r for r in results if r.get("volume_surge")]
    bullish_div = [r for r in results if r.get("obv_divergence") == "bullish"]
    bearish_div = [r for r in results if r.get("obv_divergence") == "bearish"]

    print(f"\nSummary:")
    print(f"  Successful: {len(results) - len(errors)}/{len(results)}")
    if volume_surges:
        print(f"  Volume surges: {', '.join(r['symbol'] for r in volume_surges)}")
    if bullish_div:
        print(f"  Bullish OBV divergence: {', '.join(r['symbol'] for r in bullish_div)}")
    if bearish_div:
        print(f"  Bearish OBV divergence: {', '.join(r['symbol'] for r in bearish_div)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Fetch short interest data for tickers.

Uses Yahoo Finance as the primary data source for short interest metrics.
FINRA data could be added as an alternative but requires parsing their files.

Usage:
    python fetch_short_interest.py AAPL NVDA GME AMC
    python fetch_short_interest.py --file tickers.txt
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[3]))

import yfinance as yf
import numpy as np

from lib.python.retry import retry_with_backoff


def fetch_short_interest(ticker: str) -> dict:
    """
    Fetch short interest data for a single ticker.

    Returns dict with:
    - shares_short: Number of shares sold short
    - short_ratio: Short % of float
    - days_to_cover: Days to cover based on avg volume
    - short_change: Change from prior period
    - float_shares: Float shares outstanding
    - avg_volume: Average daily volume
    """
    try:
        stock = yf.Ticker(ticker)
        info = retry_with_backoff(lambda: stock.info)

        # Extract short interest data
        shares_short = info.get("sharesShort", 0) or 0
        shares_short_prior = info.get("sharesShortPriorMonth", 0) or 0
        short_ratio = info.get("shortRatio", 0) or 0  # Days to cover
        short_percent_of_float = info.get("shortPercentOfFloat", 0) or 0

        # Float and share data
        float_shares = info.get("floatShares", 0) or 0
        shares_outstanding = info.get("sharesOutstanding", 0) or 0

        # Volume data
        avg_volume = info.get("averageVolume", 0) or 0
        avg_volume_10d = info.get("averageVolume10days", 0) or 0

        # Price data for context
        current_price = info.get("regularMarketPrice", info.get("previousClose", 0)) or 0
        market_cap = info.get("marketCap", 0) or 0

        # Calculate additional metrics
        short_change = shares_short - shares_short_prior if shares_short_prior > 0 else 0
        short_change_pct = (short_change / shares_short_prior * 100) if shares_short_prior > 0 else 0

        # Days to cover (our calculation vs Yahoo's)
        days_to_cover = (shares_short / avg_volume) if avg_volume > 0 else 0

        # Short interest as % of outstanding (if float not available)
        if float_shares > 0:
            si_pct_float = (shares_short / float_shares) * 100
        elif shares_outstanding > 0:
            si_pct_float = (shares_short / shares_outstanding) * 100
        else:
            si_pct_float = short_percent_of_float * 100  # Yahoo sometimes gives decimal

        # Normalize short_percent_of_float (Yahoo sometimes gives 0.xx, sometimes xx%)
        if short_percent_of_float > 0 and short_percent_of_float < 1:
            short_percent_of_float = short_percent_of_float * 100

        result = {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "fetch_time": datetime.now().isoformat(),

            "short_interest": {
                "shares_short": shares_short,
                "shares_short_prior": shares_short_prior,
                "short_change": short_change,
                "short_change_pct": round(short_change_pct, 2),
                "short_ratio_yahoo": short_ratio,  # Yahoo's days to cover
                "days_to_cover": round(days_to_cover, 2),
                "short_pct_float": round(si_pct_float, 2),
            },

            "float_data": {
                "float_shares": float_shares,
                "shares_outstanding": shares_outstanding,
            },

            "volume_data": {
                "avg_volume": avg_volume,
                "avg_volume_10d": avg_volume_10d,
            },

            "price_data": {
                "current_price": current_price,
                "market_cap": market_cap,
            },

            "error": None,
        }

        return result

    except Exception as e:
        return {
            "ticker": ticker,
            "fetch_time": datetime.now().isoformat(),
            "error": str(e),
        }


def calculate_squeeze_score(data: dict) -> dict:
    """
    Calculate squeeze potential score (0-100).

    Factors:
    - Short % of float (0-30 points)
    - Days to cover (0-25 points)
    - Short interest increasing (0-15 points)
    - Low float (0-15 points)
    - Small market cap (0-15 points)
    """
    if data.get("error"):
        return {"score": 0, "components": {}, "squeeze_potential": "Unknown"}

    si = data.get("short_interest", {})
    float_data = data.get("float_data", {})
    price_data = data.get("price_data", {})

    score = 0
    components = {}

    # Short % of float (0-30 points)
    si_pct = si.get("short_pct_float", 0)
    if si_pct >= 30:
        si_score = 30
    elif si_pct >= 20:
        si_score = 25
    elif si_pct >= 15:
        si_score = 20
    elif si_pct >= 10:
        si_score = 15
    elif si_pct >= 5:
        si_score = 10
    else:
        si_score = 0
    score += si_score
    components["short_pct_float"] = {"value": si_pct, "score": si_score, "max": 30}

    # Days to cover (0-25 points)
    dtc = si.get("days_to_cover", 0)
    if dtc >= 10:
        dtc_score = 25
    elif dtc >= 7:
        dtc_score = 20
    elif dtc >= 5:
        dtc_score = 15
    elif dtc >= 3:
        dtc_score = 10
    elif dtc >= 2:
        dtc_score = 5
    else:
        dtc_score = 0
    score += dtc_score
    components["days_to_cover"] = {"value": dtc, "score": dtc_score, "max": 25}

    # Short interest increasing (0-15 points)
    si_change = si.get("short_change_pct", 0)
    if si_change >= 20:
        change_score = 15
    elif si_change >= 10:
        change_score = 10
    elif si_change >= 5:
        change_score = 5
    elif si_change > 0:
        change_score = 2
    else:
        change_score = 0
    score += change_score
    components["si_change"] = {"value": si_change, "score": change_score, "max": 15}

    # Low float (0-15 points) - lower float = easier to squeeze
    float_shares = float_data.get("float_shares", 0)
    if float_shares > 0:
        if float_shares < 10_000_000:
            float_score = 15
        elif float_shares < 25_000_000:
            float_score = 12
        elif float_shares < 50_000_000:
            float_score = 8
        elif float_shares < 100_000_000:
            float_score = 4
        else:
            float_score = 0
    else:
        float_score = 0
    score += float_score
    components["low_float"] = {"value": float_shares, "score": float_score, "max": 15}

    # Small market cap (0-15 points) - smaller = more volatile
    market_cap = price_data.get("market_cap", 0)
    if market_cap > 0:
        if market_cap < 100_000_000:  # <$100M micro cap
            cap_score = 15
        elif market_cap < 500_000_000:  # <$500M small cap
            cap_score = 12
        elif market_cap < 2_000_000_000:  # <$2B
            cap_score = 8
        elif market_cap < 10_000_000_000:  # <$10B
            cap_score = 4
        else:
            cap_score = 0
    else:
        cap_score = 0
    score += cap_score
    components["small_cap"] = {"value": market_cap, "score": cap_score, "max": 15}

    # Determine squeeze potential category
    if score >= 70:
        potential = "High"
    elif score >= 50:
        potential = "Moderate"
    elif score >= 30:
        potential = "Low"
    else:
        potential = "Minimal"

    return {
        "score": score,
        "components": components,
        "squeeze_potential": potential,
    }


def generate_signals(data: dict, squeeze: dict) -> dict:
    """Generate trading signals based on short interest data."""
    if data.get("error"):
        return {}

    si = data.get("short_interest", {})
    signals = {}

    # High short interest
    si_pct = si.get("short_pct_float", 0)
    if si_pct >= 20:
        signals["high_short_interest"] = {
            "triggered": True,
            "value": si_pct,
            "message": f"High short interest: {si_pct:.1f}% of float",
        }

    # High days to cover
    dtc = si.get("days_to_cover", 0)
    if dtc >= 5:
        signals["high_days_to_cover"] = {
            "triggered": True,
            "value": dtc,
            "message": f"High days to cover: {dtc:.1f} days",
        }

    # Short interest increasing significantly
    si_change = si.get("short_change_pct", 0)
    if si_change >= 10:
        signals["shorts_increasing"] = {
            "triggered": True,
            "value": si_change,
            "message": f"Short interest increasing: +{si_change:.1f}%",
        }
    elif si_change <= -10:
        signals["shorts_decreasing"] = {
            "triggered": True,
            "value": si_change,
            "message": f"Short interest decreasing: {si_change:.1f}% (potential covering)",
        }

    # Squeeze candidate
    if squeeze.get("score", 0) >= 50:
        signals["squeeze_candidate"] = {
            "triggered": True,
            "value": squeeze["score"],
            "message": f"Squeeze potential: {squeeze['squeeze_potential']} (score: {squeeze['score']})",
        }

    return signals


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch short interest data")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols")
    parser.add_argument("--file", type=Path, help="File with tickers (one per line)")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent.parent / "data" / "short_interest.json")

    args = parser.parse_args()

    # Collect tickers
    tickers = []
    if args.tickers:
        tickers.extend([t.upper() for t in args.tickers])
    if args.file and args.file.exists():
        with open(args.file) as f:
            tickers.extend([line.strip().upper() for line in f if line.strip()])

    if not tickers:
        print("Error: No tickers specified", file=sys.stderr)
        print("Usage: python fetch_short_interest.py AAPL NVDA GME", file=sys.stderr)
        sys.exit(1)

    # Remove duplicates while preserving order
    tickers = list(dict.fromkeys(tickers))

    print(f"Fetching short interest for {len(tickers)} ticker(s)...\n")

    results = []
    for ticker in tickers:
        print(f"{ticker}:", end=" ", flush=True)

        data = fetch_short_interest(ticker)

        if data.get("error"):
            print(f"ERROR - {data['error']}")
            results.append(data)
            continue

        # Calculate squeeze score and signals
        squeeze = calculate_squeeze_score(data)
        signals = generate_signals(data, squeeze)

        data["squeeze"] = squeeze
        data["signals"] = signals
        results.append(data)

        # Print summary
        si = data["short_interest"]
        print(f"SI: {si['short_pct_float']:.1f}% | DTC: {si['days_to_cover']:.1f}d | "
              f"Change: {si['short_change_pct']:+.1f}% | "
              f"Squeeze: {squeeze['squeeze_potential']} ({squeeze['score']})")

        if signals:
            for sig_name, sig_data in signals.items():
                if sig_data.get("triggered"):
                    print(f"  -> {sig_data['message']}")

    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "fetch_time": datetime.now().isoformat(),
        "ticker_count": len(results),
        "tickers": results,
    }

    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nResults saved to {args.output}")

    # Print summary table
    print("\n" + "=" * 70)
    print("SHORT INTEREST SUMMARY")
    print("=" * 70)
    print(f"{'Ticker':<8} {'SI %':>8} {'DTC':>6} {'Change':>8} {'Squeeze':>10} {'Score':>6}")
    print("-" * 70)

    # Sort by squeeze score
    sorted_results = sorted(
        [r for r in results if not r.get("error")],
        key=lambda x: x.get("squeeze", {}).get("score", 0),
        reverse=True
    )

    for r in sorted_results:
        si = r["short_interest"]
        sq = r.get("squeeze", {})
        print(f"{r['ticker']:<8} {si['short_pct_float']:>7.1f}% {si['days_to_cover']:>6.1f} "
              f"{si['short_change_pct']:>+7.1f}% {sq.get('squeeze_potential', 'N/A'):>10} "
              f"{sq.get('score', 0):>6}")


if __name__ == "__main__":
    main()

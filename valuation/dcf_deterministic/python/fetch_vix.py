#!/usr/bin/env python3
"""
Fetch current VIX (CBOE Volatility Index) for dynamic ERP calculation.

The VIX measures implied volatility from S&P 500 options and serves as
a real-time gauge of market risk aversion. Higher VIX indicates greater
expected volatility and risk premium demanded by investors.

Historical VIX Statistics (1990-2024):
- Mean: ~19.5
- Median: ~17.5
- 10th percentile: ~12
- 90th percentile: ~28
- Max (2020 COVID crash): ~82

Usage:
    python fetch_vix.py
    python fetch_vix.py --output /tmp/vix.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[3]))

import yfinance as yf

from lib.python.retry import retry_with_backoff


# VIX historical statistics for context
VIX_STATS = {
    "historical_mean": 19.5,
    "historical_median": 17.5,
    "percentile_10": 12.0,
    "percentile_25": 14.5,
    "percentile_75": 22.0,
    "percentile_90": 28.0,
    "all_time_high": 82.69,  # March 2020
    "typical_range": (12.0, 30.0),
}


def fetch_current_vix() -> dict:
    """Fetch current VIX level from Yahoo Finance."""
    try:
        vix = yf.Ticker("^VIX")
        hist = retry_with_backoff(lambda: vix.history(period="5d"))

        if hist.empty:
            return {"error": "No VIX data available"}

        # Get the most recent close
        current_vix = float(hist["Close"].iloc[-1])
        prev_vix = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current_vix

        # Calculate change
        change = current_vix - prev_vix
        change_pct = (change / prev_vix * 100) if prev_vix > 0 else 0

        # Determine regime
        if current_vix < 15:
            regime = "low_volatility"
            regime_desc = "Calm markets, complacency possible"
        elif current_vix < 20:
            regime = "normal"
            regime_desc = "Normal market conditions"
        elif current_vix < 30:
            regime = "elevated"
            regime_desc = "Elevated uncertainty, above average risk"
        elif current_vix < 40:
            regime = "high"
            regime_desc = "High volatility, significant market stress"
        else:
            regime = "extreme"
            regime_desc = "Extreme fear, crisis conditions"

        # Calculate ERP adjustment factor (using default sensitivity of 0.4)
        erp_adjustment = (current_vix / VIX_STATS["historical_mean"]) ** 0.4

        return {
            "vix": round(current_vix, 2),
            "previous_close": round(prev_vix, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "timestamp": datetime.now().isoformat(),
            "regime": regime,
            "regime_description": regime_desc,
            "erp_adjustment_factor": round(erp_adjustment, 4),
            "historical_mean": VIX_STATS["historical_mean"],
            "percentile_context": {
                "below_median": current_vix < VIX_STATS["historical_median"],
                "above_75th": current_vix > VIX_STATS["percentile_75"],
                "above_90th": current_vix > VIX_STATS["percentile_90"],
            },
        }

    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="Fetch current VIX for dynamic ERP calculation"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output JSON file path (default: stdout)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only output the VIX value",
    )
    args = parser.parse_args()

    result = fetch_current_vix()

    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.quiet:
        print(result["vix"])
    elif args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"VIX data written to {args.output}")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

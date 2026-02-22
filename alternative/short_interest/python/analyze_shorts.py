#!/usr/bin/env python3
"""
Analyze short interest data and generate alerts.

This script reads fetched short interest data and generates alerts based on
configured thresholds. Output is compatible with the watchlist alert system.

Usage:
    python analyze_shorts.py --data data/short_interest.json --output output/short_alerts.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def load_short_data(filepath: Path) -> dict:
    """Load short interest data from JSON file."""
    with open(filepath) as f:
        return json.load(f)


def generate_ticker_alerts(ticker_data: dict, thresholds: dict = None) -> list:
    """
    Generate alerts for a single ticker based on short interest data.

    Args:
        ticker_data: Short interest data for one ticker
        thresholds: Custom alert thresholds (optional)

    Returns:
        List of alert dicts compatible with watchlist system
    """
    if thresholds is None:
        thresholds = {
            "si_pct_float": 15,         # Short % of float threshold
            "days_to_cover": 5,          # Days to cover threshold
            "si_change_pct": 10,         # SI change threshold (absolute)
            "squeeze_score": 50,         # Squeeze score threshold
        }

    ticker = ticker_data.get("ticker", "???")
    si = ticker_data.get("short_interest", {})
    squeeze = ticker_data.get("squeeze", {})
    alerts = []

    timestamp = ticker_data.get("fetch_time", datetime.now().isoformat())

    # High short interest alert
    si_pct = si.get("short_pct_float", 0)
    if si_pct >= thresholds["si_pct_float"]:
        alerts.append({
            "symbol": ticker,
            "type": "short_interest_high",
            "message": f"Short Interest: {si_pct:.1f}% of float shorted",
            "priority": 4 if si_pct >= 25 else 3,
            "priority_name": "high" if si_pct >= 25 else "default",
            "value": si_pct,
            "timestamp": timestamp,
        })

    # High days to cover alert
    dtc = si.get("days_to_cover", 0)
    if dtc >= thresholds["days_to_cover"]:
        alerts.append({
            "symbol": ticker,
            "type": "short_days_to_cover_high",
            "message": f"Short Interest: {dtc:.1f} days to cover",
            "priority": 4 if dtc >= 10 else 3,
            "priority_name": "high" if dtc >= 10 else "default",
            "value": dtc,
            "timestamp": timestamp,
        })

    # Short interest increasing
    si_change = si.get("short_change_pct", 0)
    if si_change >= thresholds["si_change_pct"]:
        alerts.append({
            "symbol": ticker,
            "type": "short_interest_increasing",
            "message": f"Short Interest: Increasing +{si_change:.1f}% from prior month",
            "priority": 3,
            "priority_name": "default",
            "value": si_change,
            "timestamp": timestamp,
        })

    # Short interest decreasing (potential covering)
    if si_change <= -thresholds["si_change_pct"]:
        alerts.append({
            "symbol": ticker,
            "type": "short_interest_decreasing",
            "message": f"Short Interest: Decreasing {si_change:.1f}% (potential covering)",
            "priority": 3,
            "priority_name": "default",
            "value": si_change,
            "timestamp": timestamp,
        })

    # Squeeze candidate alert
    squeeze_score = squeeze.get("score", 0)
    squeeze_potential = squeeze.get("squeeze_potential", "Minimal")
    if squeeze_score >= thresholds["squeeze_score"]:
        priority = 5 if squeeze_potential == "High" else 4
        priority_name = "urgent" if squeeze_potential == "High" else "high"
        alerts.append({
            "symbol": ticker,
            "type": "squeeze_candidate",
            "message": f"Squeeze Alert: {squeeze_potential} potential (score: {squeeze_score}/100)",
            "priority": priority,
            "priority_name": priority_name,
            "value": squeeze_score,
            "timestamp": timestamp,
        })

    return alerts


def generate_summary(ticker_data: dict) -> dict:
    """Generate a summary for a ticker's short interest."""
    ticker = ticker_data.get("ticker", "???")
    si = ticker_data.get("short_interest", {})
    squeeze = ticker_data.get("squeeze", {})
    signals = ticker_data.get("signals", {})
    float_data = ticker_data.get("float_data", {})
    price_data = ticker_data.get("price_data", {})

    summary = {
        "ticker": ticker,
        "name": ticker_data.get("name", ticker),
        "si_pct_float": si.get("short_pct_float", 0),
        "days_to_cover": si.get("days_to_cover", 0),
        "si_change_pct": si.get("short_change_pct", 0),
        "squeeze_score": squeeze.get("score", 0),
        "squeeze_potential": squeeze.get("squeeze_potential", "Unknown"),
        "float_shares": float_data.get("float_shares", 0),
        "market_cap": price_data.get("market_cap", 0),
        "signals_triggered": list(signals.keys()) if signals else [],
    }

    return summary


def format_market_cap(value: float) -> str:
    """Format market cap for display."""
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    elif value >= 1_000_000:
        return f"${value / 1_000_000:.0f}M"
    else:
        return f"${value:,.0f}"


def format_shares(value: float) -> str:
    """Format share count for display."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    else:
        return f"{value:,.0f}"


def print_report(summaries: list, alerts: list):
    """Print analysis report to console."""
    print("\n" + "=" * 70)
    print("Short Interest Analysis Report")
    print("=" * 70)

    print(f"\nTickers analyzed: {len(summaries)}")
    print(f"Alerts generated: {len(alerts)}")

    # Summary table
    print("\n{:<8} {:>8} {:>6} {:>8} {:>10} {:>6}".format(
        "Ticker", "SI %", "DTC", "Change", "Squeeze", "Score"
    ))
    print("-" * 70)

    for s in sorted(summaries, key=lambda x: x["squeeze_score"], reverse=True):
        print("{:<8} {:>7.1f}% {:>6.1f} {:>+7.1f}% {:>10} {:>6}".format(
            s["ticker"],
            s["si_pct_float"],
            s["days_to_cover"],
            s["si_change_pct"],
            s["squeeze_potential"],
            s["squeeze_score"]
        ))

    # Alerts
    if alerts:
        print("\n" + "-" * 70)
        print("ALERTS")
        print("-" * 70)
        for alert in sorted(alerts, key=lambda x: x["priority"], reverse=True):
            priority = alert["priority_name"].upper()
            print(f"[{priority}] {alert['symbol']}: {alert['message']}")

    # Squeeze candidates
    squeeze_candidates = [s for s in summaries if s["squeeze_score"] >= 50]
    if squeeze_candidates:
        print("\n" + "-" * 70)
        print("SQUEEZE CANDIDATES (Score >= 50)")
        print("-" * 70)
        print("{:<8} {:>8} {:>8} {:>12} {:>10}".format(
            "Ticker", "SI %", "DTC", "Float", "Mkt Cap"
        ))
        print("-" * 70)
        for s in sorted(squeeze_candidates, key=lambda x: x["squeeze_score"], reverse=True):
            print("{:<8} {:>7.1f}% {:>8.1f} {:>12} {:>10}".format(
                s["ticker"],
                s["si_pct_float"],
                s["days_to_cover"],
                format_shares(s["float_shares"]),
                format_market_cap(s["market_cap"])
            ))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Analyze short interest data")
    parser.add_argument("--data", type=Path,
                        default=Path(__file__).parent.parent / "data" / "short_interest.json",
                        help="Short interest data file")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent.parent / "output" / "short_alerts.json",
                        help="Output alerts file")
    parser.add_argument("--threshold-si", type=float, default=15,
                        help="Short %% of float threshold")
    parser.add_argument("--threshold-dtc", type=float, default=5,
                        help="Days to cover threshold")
    parser.add_argument("--threshold-squeeze", type=float, default=50,
                        help="Squeeze score threshold")
    parser.add_argument("--quiet", action="store_true", help="Suppress report output")

    args = parser.parse_args()

    if not args.data.exists():
        print(f"Error: Data file not found: {args.data}", file=sys.stderr)
        print("Run fetch_short_interest.py first to fetch data.", file=sys.stderr)
        sys.exit(1)

    # Load short interest data
    short_data = load_short_data(args.data)
    tickers = short_data.get("tickers", [])

    if not tickers:
        print("No ticker data found")
        sys.exit(0)

    # Configure thresholds
    thresholds = {
        "si_pct_float": args.threshold_si,
        "days_to_cover": args.threshold_dtc,
        "si_change_pct": 10,
        "squeeze_score": args.threshold_squeeze,
    }

    # Generate alerts and summaries
    all_alerts = []
    summaries = []

    for ticker_data in tickers:
        if ticker_data.get("error"):
            continue

        alerts = generate_ticker_alerts(ticker_data, thresholds)
        all_alerts.extend(alerts)

        summary = generate_summary(ticker_data)
        summaries.append(summary)

    # Print report
    if not args.quiet:
        print_report(summaries, all_alerts)

    # Save alerts
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "analysis_time": datetime.now().isoformat(),
        "ticker_count": len(summaries),
        "alert_count": len(all_alerts),
        "summaries": summaries,
        "alerts": all_alerts,
    }

    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nAlerts saved to {args.output}")

    # Also save in watchlist-compatible format
    watchlist_alerts = {
        "alert_count": len(all_alerts),
        "alerts": all_alerts,
    }
    watchlist_output = args.output.parent / "short_watchlist_alerts.json"
    with open(watchlist_output, "w") as f:
        json.dump(watchlist_alerts, f, indent=2)

    print(f"Watchlist-compatible alerts: {watchlist_output}")

    # Save squeeze candidates
    squeeze_candidates = [s for s in summaries if s["squeeze_score"] >= 50]
    if squeeze_candidates:
        squeeze_output = args.output.parent / "squeeze_candidates.json"
        with open(squeeze_output, "w") as f:
            json.dump({
                "analysis_time": datetime.now().isoformat(),
                "candidate_count": len(squeeze_candidates),
                "candidates": sorted(squeeze_candidates,
                                   key=lambda x: x["squeeze_score"],
                                   reverse=True)
            }, f, indent=2)
        print(f"Squeeze candidates: {squeeze_output}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Analyze Google Trends data and generate alerts.

This script reads fetched trends data and generates alerts based on
configured thresholds. Output is compatible with the watchlist alert system.

Usage:
    python analyze_trends.py --data data/trends_combined.json --output output/trends_alerts.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def load_trends_data(filepath: Path) -> dict:
    """Load combined trends data."""
    with open(filepath) as f:
        return json.load(f)


def calculate_attention_score(signals: dict) -> float:
    """
    Calculate composite attention score (0-100).

    Factors:
    - Brand momentum (current level and change)
    - Retail attention (stock search interest)
    - Rising queries activity
    """
    score = 50  # Baseline

    # Brand momentum contribution
    brand = signals.get("brand_momentum", {})
    if brand:
        current = brand.get("current", 50)
        change_7d = brand.get("change_7d_pct", 0)

        # Current level contribution (0-25 points)
        score += (current - 50) * 0.25

        # Momentum contribution (0-25 points)
        if change_7d > 0:
            score += min(change_7d, 50) * 0.5
        else:
            score += max(change_7d, -25) * 0.5

    # Retail attention contribution
    retail = signals.get("retail_attention", {})
    if retail:
        percentile = retail.get("percentile", 50)
        # Percentile contribution (0-20 points)
        score += (percentile - 50) * 0.2

    # Rising queries bonus
    rising = signals.get("rising_queries", [])
    if len(rising) >= 5:
        score += 5  # Active discussion bonus

    # Clamp to 0-100
    return max(0, min(100, score))


def generate_ticker_alerts(ticker_data: dict, thresholds: dict = None) -> list:
    """
    Generate alerts for a single ticker based on trends signals.

    Args:
        ticker_data: Trends data for one ticker
        thresholds: Custom alert thresholds (optional)

    Returns:
        List of alert dicts compatible with watchlist system
    """
    if thresholds is None:
        thresholds = {
            "brand_surge_pct": 25,      # 7-day change threshold
            "attention_score": 70,       # Attention score threshold
            "negative_spike": True,      # Alert on negative spikes
        }

    ticker = ticker_data.get("ticker", "???")
    signals = ticker_data.get("signals", {})
    alerts = []

    timestamp = ticker_data.get("timestamp", datetime.now().isoformat())

    # Brand surge alert
    brand = signals.get("brand_momentum", {})
    if brand.get("surge") or brand.get("change_7d_pct", 0) > thresholds["brand_surge_pct"]:
        alerts.append({
            "symbol": ticker,
            "type": "trends_brand_surge",
            "message": f"Google Trends: Brand search surge +{brand.get('change_7d_pct', 0):.1f}% (7d)",
            "priority": 3,
            "priority_name": "default",
            "value": brand.get("change_7d_pct", 0),
            "timestamp": timestamp,
        })

    # Attention score alert
    attention_score = calculate_attention_score(signals)
    if attention_score >= thresholds["attention_score"]:
        alerts.append({
            "symbol": ticker,
            "type": "trends_high_attention",
            "message": f"Google Trends: High retail attention (score: {attention_score:.0f}/100)",
            "priority": 3,
            "priority_name": "default",
            "value": attention_score,
            "timestamp": timestamp,
        })

    # Negative spike alert
    negative = signals.get("negative_sentiment", {})
    if thresholds.get("negative_spike") and negative.get("spike"):
        alerts.append({
            "symbol": ticker,
            "type": "trends_negative_spike",
            "message": f"Google Trends: Negative search spike '{negative.get('keyword', 'unknown')}'",
            "priority": 4,
            "priority_name": "high",
            "value": negative.get("current", 0),
            "timestamp": timestamp,
        })

    # Elevated retail attention (lower priority)
    retail = signals.get("retail_attention", {})
    if retail.get("elevated"):
        alerts.append({
            "symbol": ticker,
            "type": "trends_retail_elevated",
            "message": f"Google Trends: Elevated stock search interest (percentile: {retail.get('percentile', 0):.0f}%)",
            "priority": 2,
            "priority_name": "low",
            "value": retail.get("percentile", 0),
            "timestamp": timestamp,
        })

    return alerts


def generate_summary(ticker_data: dict) -> dict:
    """Generate a summary for a ticker's trends."""
    signals = ticker_data.get("signals", {})
    ticker = ticker_data.get("ticker", "???")

    attention_score = calculate_attention_score(signals)

    summary = {
        "ticker": ticker,
        "attention_score": round(attention_score, 1),
        "brand_current": signals.get("brand_momentum", {}).get("current", 0),
        "brand_change_7d": signals.get("brand_momentum", {}).get("change_7d_pct", 0),
        "retail_percentile": signals.get("retail_attention", {}).get("percentile", 0),
        "rising_queries": signals.get("rising_queries", [])[:3],
        "signals_detected": [],
    }

    # List detected signals
    if signals.get("brand_momentum", {}).get("surge"):
        summary["signals_detected"].append("brand_surge")
    if signals.get("retail_attention", {}).get("elevated"):
        summary["signals_detected"].append("retail_elevated")
    if signals.get("negative_sentiment", {}).get("spike"):
        summary["signals_detected"].append("negative_spike")

    return summary


def print_report(summaries: list, alerts: list):
    """Print analysis report to console."""
    print("\n" + "=" * 60)
    print("Google Trends Analysis Report")
    print("=" * 60)

    print(f"\nTickers analyzed: {len(summaries)}")
    print(f"Alerts generated: {len(alerts)}")

    # Summary table
    print("\n{:<8} {:>8} {:>10} {:>10} {:>15}".format(
        "Ticker", "Attn", "Brand 7d", "Retail %", "Signals"
    ))
    print("-" * 60)

    for s in sorted(summaries, key=lambda x: x["attention_score"], reverse=True):
        signals_str = ", ".join(s["signals_detected"][:2]) if s["signals_detected"] else "-"
        print("{:<8} {:>8.0f} {:>+9.1f}% {:>9.0f}% {:>15}".format(
            s["ticker"],
            s["attention_score"],
            s["brand_change_7d"],
            s["retail_percentile"],
            signals_str
        ))

    # Alerts
    if alerts:
        print("\n" + "-" * 60)
        print("ALERTS")
        print("-" * 60)
        for alert in sorted(alerts, key=lambda x: x["priority"], reverse=True):
            priority = alert["priority_name"].upper()
            print(f"[{priority}] {alert['symbol']}: {alert['message']}")

    # Rising queries highlights
    print("\n" + "-" * 60)
    print("RISING QUERIES")
    print("-" * 60)
    for s in summaries:
        if s["rising_queries"]:
            print(f"{s['ticker']}: {', '.join(s['rising_queries'])}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Analyze Google Trends data")
    parser.add_argument("--data", type=Path,
                        default=Path(__file__).parent.parent / "data" / "trends_combined.json",
                        help="Combined trends data file")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent.parent / "output" / "trends_alerts.json",
                        help="Output alerts file")
    parser.add_argument("--threshold-surge", type=float, default=25,
                        help="Brand surge threshold (7d change %%)")
    parser.add_argument("--threshold-attention", type=float, default=70,
                        help="Attention score threshold")
    parser.add_argument("--quiet", action="store_true", help="Suppress report output")

    args = parser.parse_args()

    if not args.data.exists():
        print(f"Error: Data file not found: {args.data}", file=sys.stderr)
        print("Run fetch_trends.py first to fetch data.", file=sys.stderr)
        sys.exit(1)

    # Load trends data
    trends_data = load_trends_data(args.data)
    tickers = trends_data.get("tickers", [])

    if not tickers:
        print("No ticker data found")
        sys.exit(0)

    # Configure thresholds
    thresholds = {
        "brand_surge_pct": args.threshold_surge,
        "attention_score": args.threshold_attention,
        "negative_spike": True,
    }

    # Generate alerts and summaries
    all_alerts = []
    summaries = []

    for ticker_data in tickers:
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
    watchlist_output = args.output.parent / "trends_watchlist_alerts.json"
    with open(watchlist_output, "w") as f:
        json.dump(watchlist_alerts, f, indent=2)

    print(f"Watchlist-compatible alerts: {watchlist_output}")


if __name__ == "__main__":
    main()

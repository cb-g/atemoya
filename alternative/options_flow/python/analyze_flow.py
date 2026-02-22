#!/usr/bin/env python3
"""
Analyze options flow data and generate alerts.

This script reads fetched options flow data and generates alerts based on
configured thresholds. Output is compatible with the watchlist alert system.

Usage:
    python analyze_flow.py --data data/options_flow.json --output output/flow_alerts.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def load_flow_data(filepath: Path) -> dict:
    """Load options flow data from JSON file."""
    with open(filepath) as f:
        return json.load(f)


def detect_bullish_flow(ticker_data: dict, threshold_ratio: float = 2.0) -> dict:
    """
    Detect bullish options flow.

    Args:
        ticker_data: Options flow data for one ticker
        threshold_ratio: Call/Put premium ratio threshold

    Returns:
        Dict with bullish flow info
    """
    prem = ticker_data.get("premium_summary", {})
    ratio = prem.get("call_put_premium_ratio", 1)
    call_premium = prem.get("total_call_premium", 0)

    if ratio >= threshold_ratio and call_premium > 1_000_000:
        return {
            "detected": True,
            "call_put_ratio": ratio,
            "call_premium": call_premium,
            "strength": "strong" if ratio >= 3 else "moderate",
        }

    return {"detected": False}


def detect_bearish_flow(ticker_data: dict, threshold_ratio: float = 2.0) -> dict:
    """
    Detect bearish options flow.

    Args:
        ticker_data: Options flow data for one ticker
        threshold_ratio: Put/Call premium ratio threshold

    Returns:
        Dict with bearish flow info
    """
    prem = ticker_data.get("premium_summary", {})
    call_premium = prem.get("total_call_premium", 0)
    put_premium = prem.get("total_put_premium", 0)

    if call_premium > 0:
        put_call_ratio = put_premium / call_premium
    elif put_premium > 0:
        put_call_ratio = 999
    else:
        put_call_ratio = 1

    if put_call_ratio >= threshold_ratio and put_premium > 1_000_000:
        return {
            "detected": True,
            "put_call_ratio": round(put_call_ratio, 2),
            "put_premium": put_premium,
            "strength": "strong" if put_call_ratio >= 3 else "moderate",
        }

    return {"detected": False}


def detect_unusual_activity(ticker_data: dict, min_score: int = 70) -> list:
    """
    Find highly unusual options activity.

    Returns:
        List of unusual activity items above threshold
    """
    unusual = ticker_data.get("unusual_activity", [])
    return [u for u in unusual if u.get("unusual_score", 0) >= min_score]


def detect_large_premium(ticker_data: dict, threshold: float = 500_000) -> list:
    """
    Find options with large premium.

    Returns:
        List of options with premium above threshold
    """
    unusual = ticker_data.get("unusual_activity", [])
    return [u for u in unusual if u.get("premium", 0) >= threshold]


def detect_high_vol_oi(ticker_data: dict, threshold: float = 5.0) -> list:
    """
    Find options with high volume/OI ratio (new positions).

    Returns:
        List of options with vol/OI above threshold
    """
    unusual = ticker_data.get("unusual_activity", [])
    return [u for u in unusual if u.get("vol_oi_ratio", 0) >= threshold]


def generate_ticker_alerts(ticker_data: dict, thresholds: dict = None) -> list:
    """
    Generate alerts for a single ticker based on options flow.

    Args:
        ticker_data: Options flow data for one ticker
        thresholds: Custom alert thresholds (optional)

    Returns:
        List of alert dicts compatible with watchlist system
    """
    if thresholds is None:
        thresholds = {
            "bullish_ratio": 2.0,
            "bearish_ratio": 2.0,
            "unusual_score": 70,
            "large_premium": 500_000,
            "high_vol_oi": 5.0,
        }

    ticker = ticker_data.get("ticker", "???")
    alerts = []

    timestamp = ticker_data.get("fetch_time", datetime.now().isoformat())

    # Bullish flow alert
    bullish = detect_bullish_flow(ticker_data, thresholds["bullish_ratio"])
    if bullish.get("detected"):
        ratio = bullish.get("call_put_ratio", 0)
        premium = bullish.get("call_premium", 0)
        strength = bullish.get("strength", "moderate")
        priority = 4 if strength == "strong" else 3

        alerts.append({
            "symbol": ticker,
            "type": "options_bullish_flow",
            "message": f"Options Flow: Bullish ({strength}) - C/P ratio {ratio:.1f}x, ${premium/1_000_000:.1f}M calls",
            "priority": priority,
            "priority_name": "high" if strength == "strong" else "default",
            "value": ratio,
            "timestamp": timestamp,
        })

    # Bearish flow alert
    bearish = detect_bearish_flow(ticker_data, thresholds["bearish_ratio"])
    if bearish.get("detected"):
        ratio = bearish.get("put_call_ratio", 0)
        premium = bearish.get("put_premium", 0)
        strength = bearish.get("strength", "moderate")
        priority = 4 if strength == "strong" else 3

        alerts.append({
            "symbol": ticker,
            "type": "options_bearish_flow",
            "message": f"Options Flow: Bearish ({strength}) - P/C ratio {ratio:.1f}x, ${premium/1_000_000:.1f}M puts",
            "priority": priority,
            "priority_name": "high" if strength == "strong" else "default",
            "value": ratio,
            "timestamp": timestamp,
        })

    # Unusual activity alerts
    unusual = detect_unusual_activity(ticker_data, thresholds["unusual_score"])
    if unusual:
        top = unusual[0]
        score = top.get("unusual_score", 0)
        opt_type = top.get("option_type", "")
        strike = top.get("strike", 0)
        expiry = top.get("expiry", "")
        premium = top.get("premium", 0)

        alerts.append({
            "symbol": ticker,
            "type": "options_unusual_activity",
            "message": f"Options Flow: Unusual {opt_type} ${strike} {expiry} (score: {score}, ${premium:,.0f})",
            "priority": 4 if score >= 80 else 3,
            "priority_name": "high" if score >= 80 else "default",
            "value": score,
            "timestamp": timestamp,
            "details": {
                "count": len(unusual),
                "top_strike": strike,
                "top_expiry": expiry,
                "top_premium": premium,
            },
        })

    # Large premium alerts (top 3)
    large = detect_large_premium(ticker_data, thresholds["large_premium"])
    for item in large[:3]:
        premium = item.get("premium", 0)
        if premium >= 1_000_000:  # Only alert on $1M+
            opt_type = item.get("option_type", "")
            strike = item.get("strike", 0)
            expiry = item.get("expiry", "")
            volume = item.get("volume", 0)

            sentiment = "bullish" if opt_type == "CALL" else "bearish"

            alerts.append({
                "symbol": ticker,
                "type": f"options_large_{opt_type.lower()}",
                "message": f"Options Flow: Large {opt_type} ${strike} {expiry} - ${premium/1_000_000:.1f}M ({volume:,} contracts)",
                "priority": 4,
                "priority_name": "high",
                "value": premium,
                "timestamp": timestamp,
            })

    # High Vol/OI ratio alert (new positions being opened)
    high_vol_oi = detect_high_vol_oi(ticker_data, thresholds["high_vol_oi"])
    if len(high_vol_oi) >= 3:  # Multiple new positions
        avg_ratio = sum(h.get("vol_oi_ratio", 0) for h in high_vol_oi) / len(high_vol_oi)
        alerts.append({
            "symbol": ticker,
            "type": "options_new_positions",
            "message": f"Options Flow: {len(high_vol_oi)} new positions detected (avg Vol/OI: {avg_ratio:.1f}x)",
            "priority": 3,
            "priority_name": "default",
            "value": avg_ratio,
            "timestamp": timestamp,
        })

    return alerts


def generate_summary(ticker_data: dict) -> dict:
    """Generate a summary for a ticker's options flow."""
    ticker = ticker_data.get("ticker", "???")
    vol = ticker_data.get("volume_summary", {})
    prem = ticker_data.get("premium_summary", {})

    # Detect signals
    bullish = detect_bullish_flow(ticker_data)
    bearish = detect_bearish_flow(ticker_data)
    unusual = detect_unusual_activity(ticker_data, 70)
    large = detect_large_premium(ticker_data, 500_000)

    signals = []
    if bullish.get("detected"):
        signals.append("bullish_flow")
    if bearish.get("detected"):
        signals.append("bearish_flow")
    if unusual:
        signals.append(f"unusual_{len(unusual)}")
    if large:
        signals.append(f"large_premium_{len(large)}")

    return {
        "ticker": ticker,
        "name": ticker_data.get("name", ticker),
        "spot_price": ticker_data.get("spot_price", 0),
        "total_call_premium": prem.get("total_call_premium", 0),
        "total_put_premium": prem.get("total_put_premium", 0),
        "call_put_ratio": prem.get("call_put_premium_ratio", 1),
        "put_call_volume_ratio": vol.get("put_call_ratio", 0),
        "unusual_count": ticker_data.get("unusual_activity_count", 0),
        "sentiment": ticker_data.get("sentiment", "neutral"),
        "signals": signals,
    }


def format_premium(value: float) -> str:
    """Format premium value for display."""
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"${value / 1_000:.0f}K"
    else:
        return f"${value:,.0f}"


def print_report(summaries: list, alerts: list):
    """Print analysis report to console."""
    print("\n" + "=" * 75)
    print("Options Flow Analysis Report")
    print("=" * 75)

    print(f"\nTickers analyzed: {len(summaries)}")
    print(f"Alerts generated: {len(alerts)}")

    # Summary table
    print("\n{:<8} {:>10} {:>10} {:>8} {:>8} {:>12}".format(
        "Ticker", "Call $", "Put $", "C/P", "Unusual", "Sentiment"
    ))
    print("-" * 75)

    for s in sorted(summaries, key=lambda x: x["call_put_ratio"], reverse=True):
        call_str = format_premium(s["total_call_premium"])
        put_str = format_premium(s["total_put_premium"])

        print("{:<8} {:>10} {:>10} {:>8.2f} {:>8} {:>12}".format(
            s["ticker"],
            call_str,
            put_str,
            s["call_put_ratio"],
            s["unusual_count"],
            s["sentiment"]
        ))

    # Alerts
    if alerts:
        print("\n" + "-" * 75)
        print("ALERTS")
        print("-" * 75)
        for alert in sorted(alerts, key=lambda x: x["priority"], reverse=True):
            priority = alert["priority_name"].upper()
            print(f"[{priority}] {alert['symbol']}: {alert['message']}")

    # Signal summary
    print("\n" + "-" * 75)
    print("SIGNAL SUMMARY")
    print("-" * 75)
    for s in summaries:
        if s["signals"]:
            print(f"{s['ticker']}: {', '.join(s['signals'])}")
        else:
            print(f"{s['ticker']}: No significant signals")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Analyze options flow data")
    parser.add_argument("--data", type=Path,
                        default=Path(__file__).parent.parent / "data" / "options_flow.json",
                        help="Options flow data file")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent.parent / "output" / "flow_alerts.json",
                        help="Output alerts file")
    parser.add_argument("--threshold-ratio", type=float, default=2.0,
                        help="Call/Put ratio threshold for flow alerts")
    parser.add_argument("--threshold-unusual", type=int, default=70,
                        help="Unusual score threshold")
    parser.add_argument("--threshold-premium", type=float, default=500_000,
                        help="Large premium threshold ($)")
    parser.add_argument("--quiet", action="store_true", help="Suppress report output")

    args = parser.parse_args()

    if not args.data.exists():
        print(f"Error: Data file not found: {args.data}", file=sys.stderr)
        print("Run fetch_flow.py first to fetch data.", file=sys.stderr)
        sys.exit(1)

    # Load flow data
    flow_data = load_flow_data(args.data)
    tickers = flow_data.get("tickers", [])

    if not tickers:
        print("No ticker data found")
        sys.exit(0)

    # Configure thresholds
    thresholds = {
        "bullish_ratio": args.threshold_ratio,
        "bearish_ratio": args.threshold_ratio,
        "unusual_score": args.threshold_unusual,
        "large_premium": args.threshold_premium,
        "high_vol_oi": 5.0,
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

    # Save alerts (remove details for cleaner output)
    clean_alerts = []
    for alert in all_alerts:
        clean_alert = {k: v for k, v in alert.items() if k != "details"}
        clean_alerts.append(clean_alert)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "analysis_time": datetime.now().isoformat(),
        "ticker_count": len(summaries),
        "alert_count": len(clean_alerts),
        "summaries": summaries,
        "alerts": clean_alerts,
    }

    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nAlerts saved to {args.output}")

    # Also save in watchlist-compatible format
    watchlist_alerts = {
        "alert_count": len(clean_alerts),
        "alerts": clean_alerts,
    }
    watchlist_output = args.output.parent / "flow_watchlist_alerts.json"
    with open(watchlist_output, "w") as f:
        json.dump(watchlist_alerts, f, indent=2)

    print(f"Watchlist-compatible alerts: {watchlist_output}")


if __name__ == "__main__":
    main()

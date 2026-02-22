#!/usr/bin/env python3
"""
Analyze SEC filings data and generate alerts.

This script reads fetched SEC filings and generates alerts based on
material events, activist positions, and other significant filings.
Output is compatible with the watchlist alert system.

Usage:
    python analyze_filings.py --data data/sec_filings.json --output output/filing_alerts.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def load_filings_data(filepath: Path) -> dict:
    """Load SEC filings data from JSON file."""
    with open(filepath) as f:
        return json.load(f)


def detect_material_events(ticker_data: dict) -> list:
    """
    Detect material 8-K events.

    Returns list of material event filings.
    """
    filings = ticker_data.get("filings", [])
    return [f for f in filings if f.get("importance", 0) >= 70 and f.get("form", "").startswith("8-K")]


def detect_earnings_filings(ticker_data: dict) -> list:
    """
    Detect earnings-related filings (Item 2.02).

    Returns list of earnings filings.
    """
    filings = ticker_data.get("filings", [])
    return [f for f in filings if f.get("signal_type") == "earnings"]


def detect_executive_changes(ticker_data: dict) -> list:
    """
    Detect executive/director changes (Item 5.02).

    Returns list of executive change filings.
    """
    filings = ticker_data.get("filings", [])
    return [f for f in filings if f.get("signal_type") == "executive_change"]


def detect_acquisitions(ticker_data: dict) -> list:
    """
    Detect acquisition/disposition filings (Item 2.01).

    Returns list of acquisition filings.
    """
    filings = ticker_data.get("filings", [])
    return [f for f in filings if f.get("signal_type") == "acquisition"]


def detect_activist_positions(ticker_data: dict) -> list:
    """
    Detect 13D activist filings.

    Returns list of activist position filings.
    """
    filings = ticker_data.get("filings", [])
    return [f for f in filings if f.get("signal_type") == "activist_13d"]


def detect_material_agreements(ticker_data: dict) -> list:
    """
    Detect material agreement filings (Item 1.01, 1.02).

    Returns list of agreement filings.
    """
    filings = ticker_data.get("filings", [])
    results = []
    for f in filings:
        items = f.get("items", [])
        for item in items:
            if item.get("item") in ["1.01", "1.02"]:
                results.append(f)
                break
    return results


def generate_ticker_alerts(ticker_data: dict, thresholds: dict = None) -> list:
    """
    Generate alerts for a single ticker based on SEC filings.

    Args:
        ticker_data: SEC filings data for one ticker
        thresholds: Custom alert thresholds (optional)

    Returns:
        List of alert dicts compatible with watchlist system
    """
    if thresholds is None:
        thresholds = {
            "importance_threshold": 70,
        }

    ticker = ticker_data.get("ticker", "???")
    alerts = []

    timestamp = ticker_data.get("fetch_time", datetime.now().isoformat())

    # Material event alerts
    material = detect_material_events(ticker_data)
    for filing in material[:3]:  # Limit to 3 most recent
        signal_type = filing.get("signal_type", "material_event")
        importance = filing.get("importance", 0)
        filing_date = filing.get("filing_date", "")
        items = filing.get("items", [])
        items_str = ", ".join(i.get("item", "") for i in items)

        # Determine alert details based on signal type
        if signal_type == "earnings":
            message = f"SEC Filing: 8-K Earnings release filed {filing_date}"
            priority = 4
        elif signal_type == "executive_change":
            message = f"SEC Filing: 8-K Executive/Director change filed {filing_date}"
            priority = 4
        elif signal_type == "acquisition":
            message = f"SEC Filing: 8-K Acquisition/Disposition filed {filing_date}"
            priority = 5
        elif signal_type == "material_agreement":
            message = f"SEC Filing: 8-K Material agreement filed {filing_date}"
            priority = 4
        elif signal_type == "reg_fd":
            message = f"SEC Filing: 8-K Regulation FD disclosure filed {filing_date}"
            priority = 3
        else:
            message = f"SEC Filing: 8-K Material event ({items_str}) filed {filing_date}"
            priority = 3

        alerts.append({
            "symbol": ticker,
            "type": f"sec_{signal_type or 'material_event'}",
            "message": message,
            "priority": priority,
            "priority_name": "urgent" if priority >= 5 else "high" if priority >= 4 else "default",
            "value": importance,
            "timestamp": timestamp,
            "filing_date": filing_date,
            "url": filing.get("url", ""),
        })

    # Activist position alerts (13D)
    activist = detect_activist_positions(ticker_data)
    for filing in activist[:2]:
        alerts.append({
            "symbol": ticker,
            "type": "sec_activist_position",
            "message": f"SEC Filing: 13D Activist position filed {filing.get('filing_date', '')}",
            "priority": 5,
            "priority_name": "urgent",
            "value": filing.get("importance", 85),
            "timestamp": timestamp,
            "filing_date": filing.get("filing_date", ""),
            "url": filing.get("url", ""),
        })

    # Annual/Quarterly report alerts
    for filing in ticker_data.get("filings", []):
        form = filing.get("form", "")
        if form.startswith("10-K"):
            alerts.append({
                "symbol": ticker,
                "type": "sec_annual_report",
                "message": f"SEC Filing: 10-K Annual report filed {filing.get('filing_date', '')}",
                "priority": 3,
                "priority_name": "default",
                "value": filing.get("importance", 60),
                "timestamp": timestamp,
                "filing_date": filing.get("filing_date", ""),
                "url": filing.get("url", ""),
            })
            break  # Only alert once

    return alerts


def generate_summary(ticker_data: dict) -> dict:
    """Generate a summary for a ticker's SEC filings."""
    ticker = ticker_data.get("ticker", "???")
    summary = ticker_data.get("summary", {})
    filings = ticker_data.get("filings", [])

    # Count by signal type
    signal_counts = {}
    for f in filings:
        sig = f.get("signal_type")
        if sig:
            signal_counts[sig] = signal_counts.get(sig, 0) + 1

    # Get most recent filing
    most_recent = filings[0] if filings else {}

    return {
        "ticker": ticker,
        "company": ticker_data.get("company", ticker),
        "total_filings": summary.get("total_filings", 0),
        "eight_k_count": summary.get("eight_k_count", 0),
        "material_events": summary.get("material_events", 0),
        "has_activist": summary.get("has_activist_filing", False),
        "has_earnings": summary.get("has_earnings", False),
        "signal_counts": signal_counts,
        "most_recent_date": most_recent.get("filing_date", ""),
        "most_recent_form": most_recent.get("form", ""),
    }


def print_report(summaries: list, alerts: list):
    """Print analysis report to console."""
    print("\n" + "=" * 75)
    print("SEC Filings Analysis Report")
    print("=" * 75)

    print(f"\nTickers analyzed: {len(summaries)}")
    print(f"Alerts generated: {len(alerts)}")

    # Summary table
    print("\n{:<8} {:>10} {:>8} {:>10} {:>10} {:>12}".format(
        "Ticker", "Total", "8-K", "Material", "Activist", "Recent"
    ))
    print("-" * 75)

    for s in sorted(summaries, key=lambda x: x["material_events"], reverse=True):
        activist_str = "Yes" if s["has_activist"] else "No"
        print("{:<8} {:>10} {:>8} {:>10} {:>10} {:>12}".format(
            s["ticker"],
            s["total_filings"],
            s["eight_k_count"],
            s["material_events"],
            activist_str,
            s["most_recent_date"]
        ))

    # Alerts
    if alerts:
        print("\n" + "-" * 75)
        print("ALERTS")
        print("-" * 75)
        for alert in sorted(alerts, key=lambda x: x["priority"], reverse=True):
            priority = alert["priority_name"].upper()
            print(f"[{priority}] {alert['symbol']}: {alert['message']}")

    # Signal breakdown
    print("\n" + "-" * 75)
    print("SIGNAL BREAKDOWN")
    print("-" * 75)
    for s in summaries:
        if s["signal_counts"]:
            signals = [f"{k}({v})" for k, v in s["signal_counts"].items()]
            print(f"{s['ticker']}: {', '.join(signals)}")
        else:
            print(f"{s['ticker']}: No significant signals")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Analyze SEC filings data")
    parser.add_argument("--data", type=Path,
                        default=Path(__file__).parent.parent / "data" / "sec_filings.json",
                        help="SEC filings data file")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent.parent / "output" / "filing_alerts.json",
                        help="Output alerts file")
    parser.add_argument("--quiet", action="store_true", help="Suppress report output")

    args = parser.parse_args()

    if not args.data.exists():
        print(f"Error: Data file not found: {args.data}", file=sys.stderr)
        print("Run fetch_filings.py first to fetch data.", file=sys.stderr)
        sys.exit(1)

    # Load filings data
    filings_data = load_filings_data(args.data)
    tickers = filings_data.get("tickers", [])

    if not tickers:
        print("No ticker data found")
        sys.exit(0)

    # Generate alerts and summaries
    all_alerts = []
    summaries = []

    for ticker_data in tickers:
        if ticker_data.get("error"):
            continue

        alerts = generate_ticker_alerts(ticker_data)
        all_alerts.extend(alerts)

        summary = generate_summary(ticker_data)
        summaries.append(summary)

    # Print report
    if not args.quiet:
        print_report(summaries, all_alerts)

    # Save alerts (clean for output)
    clean_alerts = []
    for alert in all_alerts:
        clean_alert = {k: v for k, v in alert.items()}
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
    watchlist_output = args.output.parent / "filing_watchlist_alerts.json"
    with open(watchlist_output, "w") as f:
        json.dump(watchlist_alerts, f, indent=2)

    print(f"Watchlist-compatible alerts: {watchlist_output}")


if __name__ == "__main__":
    main()

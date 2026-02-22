#!/usr/bin/env python3
"""
Analyze insider trading data and generate alerts.

This script reads fetched Form 4 data and generates alerts based on
configured thresholds. Output is compatible with the watchlist alert system.

Usage:
    python analyze_insider.py --data data/insider_transactions.json --output output/insider_alerts.json
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def load_insider_data(filepath: Path) -> dict:
    """Load insider transaction data from JSON file."""
    with open(filepath) as f:
        return json.load(f)


def detect_cluster_buying(transactions: list, days: int = 14) -> dict:
    """
    Detect cluster buying: multiple insiders buying in a short period.

    Args:
        transactions: List of transaction dicts
        days: Window to look for cluster activity

    Returns:
        Dict with cluster buying info
    """
    # Filter to open market purchases only
    buys = [t for t in transactions
            if t.get("transaction_type") == "open_market_purchase"]

    if not buys:
        return {"detected": False}

    # Group by date to find clustering
    buy_dates = defaultdict(list)
    for buy in buys:
        date = buy.get("filing_date", "")
        if date:
            buy_dates[date].append(buy)

    # Find dates with multiple insiders
    cluster_events = []
    unique_insiders = set()
    total_value = 0

    for date, day_buys in sorted(buy_dates.items()):
        for buy in day_buys:
            unique_insiders.add(buy.get("insider_name", ""))
            total_value += buy.get("value", 0)

    if len(unique_insiders) >= 2:
        return {
            "detected": True,
            "insiders": list(unique_insiders),
            "insider_count": len(unique_insiders),
            "total_value": total_value,
            "buy_count": len(buys),
        }

    return {"detected": False}


def detect_executive_buys(transactions: list) -> dict:
    """
    Detect buying by key executives (CEO, CFO, COO).

    Returns:
        Dict with executive buying info
    """
    executive_buys = []

    for trans in transactions:
        if trans.get("transaction_type") != "open_market_purchase":
            continue

        title = trans.get("insider_title", "").upper()
        importance = trans.get("insider_importance", 0)

        # CEO, CFO, COO, President
        if importance >= 80 or any(t in title for t in ["CEO", "CFO", "COO", "CHIEF", "PRESIDENT"]):
            executive_buys.append({
                "name": trans.get("insider_name", ""),
                "title": trans.get("insider_title", ""),
                "value": trans.get("value", 0),
                "shares": trans.get("shares", 0),
                "date": trans.get("filing_date", ""),
            })

    if executive_buys:
        total_value = sum(b["value"] for b in executive_buys)
        return {
            "detected": True,
            "buys": executive_buys,
            "total_value": total_value,
            "executives": list(set(b["name"] for b in executive_buys)),
        }

    return {"detected": False}


def detect_large_transactions(transactions: list, threshold: float = 500_000) -> list:
    """
    Find large open market transactions (buys or sells) above threshold.

    Only includes open market purchases and sales, not awards or exercises.

    Returns:
        List of large transactions
    """
    large = []

    for trans in transactions:
        trans_type = trans.get("transaction_type", "")
        # Only include meaningful open market transactions
        if trans_type not in ["open_market_purchase", "open_market_sale"]:
            continue

        value = abs(trans.get("value", 0))
        if value >= threshold:
            large.append({
                "name": trans.get("insider_name", ""),
                "title": trans.get("insider_title", ""),
                "type": trans_type,
                "direction": trans.get("direction", ""),
                "value": value,
                "shares": trans.get("shares", 0),
                "date": trans.get("filing_date", ""),
            })

    return sorted(large, key=lambda x: x["value"], reverse=True)


def calculate_buy_sell_sentiment(summary: dict) -> dict:
    """
    Calculate overall insider sentiment based on buy/sell ratio.

    Returns:
        Dict with sentiment analysis
    """
    buys_count = summary.get("buys_count", 0)
    sells_count = summary.get("sells_count", 0)
    buy_value = summary.get("total_buy_value", 0)
    sell_value = summary.get("total_sell_value", 0)
    ratio = summary.get("buy_sell_ratio", 0)

    # Determine sentiment
    if buys_count > 0 and sells_count == 0:
        sentiment = "strongly_bullish"
        score = 100
    elif ratio >= 2:
        sentiment = "bullish"
        score = 80
    elif ratio >= 1:
        sentiment = "slightly_bullish"
        score = 60
    elif ratio >= 0.5:
        sentiment = "neutral"
        score = 50
    elif ratio > 0:
        sentiment = "slightly_bearish"
        score = 40
    elif sells_count > 0 and buys_count == 0:
        sentiment = "bearish"
        score = 20
    else:
        sentiment = "neutral"
        score = 50

    return {
        "sentiment": sentiment,
        "score": score,
        "buy_sell_ratio": ratio,
        "net_value": buy_value - sell_value,
    }


def generate_ticker_alerts(ticker_data: dict, thresholds: dict = None) -> list:
    """
    Generate alerts for a single ticker based on insider activity.

    Args:
        ticker_data: Insider data for one ticker
        thresholds: Custom alert thresholds (optional)

    Returns:
        List of alert dicts compatible with watchlist system
    """
    if thresholds is None:
        thresholds = {
            "cluster_buy_insiders": 2,      # Minimum insiders for cluster
            "executive_buy_value": 100_000,  # Minimum value for exec buy alert
            "large_transaction": 500_000,    # Large transaction threshold
        }

    ticker = ticker_data.get("ticker", "???")
    transactions = ticker_data.get("transactions", [])
    summary = ticker_data.get("summary", {})
    alerts = []

    timestamp = ticker_data.get("fetch_time", datetime.now().isoformat())

    # Cluster buying detection
    cluster = detect_cluster_buying(transactions)
    if cluster.get("detected"):
        insider_count = cluster.get("insider_count", 0)
        total_value = cluster.get("total_value", 0)
        if insider_count >= thresholds["cluster_buy_insiders"]:
            alerts.append({
                "symbol": ticker,
                "type": "insider_cluster_buy",
                "message": f"Insider Alert: Cluster buying - {insider_count} insiders purchased (${total_value:,.0f})",
                "priority": 5,
                "priority_name": "urgent",
                "value": total_value,
                "timestamp": timestamp,
                "details": cluster,
            })

    # Executive buying detection
    exec_buys = detect_executive_buys(transactions)
    if exec_buys.get("detected"):
        total_value = exec_buys.get("total_value", 0)
        executives = exec_buys.get("executives", [])
        if total_value >= thresholds["executive_buy_value"]:
            exec_list = ", ".join(executives[:3])
            alerts.append({
                "symbol": ticker,
                "type": "insider_executive_buy",
                "message": f"Insider Alert: Executive buying - {exec_list} (${total_value:,.0f})",
                "priority": 4,
                "priority_name": "high",
                "value": total_value,
                "timestamp": timestamp,
                "details": exec_buys,
            })

    # Large transaction alerts
    large_trans = detect_large_transactions(transactions, thresholds["large_transaction"])
    for trans in large_trans[:3]:  # Limit to top 3
        direction = trans.get("direction", "")
        trans_type = "buy" if direction == "buy" else "sell"
        value = trans.get("value", 0)
        name = trans.get("name", "Unknown")
        title = trans.get("title", "")

        priority = 4 if direction == "buy" else 3
        priority_name = "high" if direction == "buy" else "default"

        alerts.append({
            "symbol": ticker,
            "type": f"insider_large_{trans_type}",
            "message": f"Insider Alert: Large {trans_type} by {name} ({title}) - ${value:,.0f}",
            "priority": priority,
            "priority_name": priority_name,
            "value": value,
            "timestamp": timestamp,
        })

    # Strong sentiment signal
    sentiment = calculate_buy_sell_sentiment(summary)
    if sentiment.get("sentiment") in ["strongly_bullish", "bullish"] and summary.get("buys_count", 0) > 0:
        alerts.append({
            "symbol": ticker,
            "type": "insider_bullish_sentiment",
            "message": f"Insider Alert: Bullish sentiment (B/S ratio: {sentiment['buy_sell_ratio']:.1f})",
            "priority": 3,
            "priority_name": "default",
            "value": sentiment.get("score", 50),
            "timestamp": timestamp,
        })

    return alerts


def generate_summary(ticker_data: dict) -> dict:
    """Generate a summary for a ticker's insider activity."""
    ticker = ticker_data.get("ticker", "???")
    transactions = ticker_data.get("transactions", [])
    summary = ticker_data.get("summary", {})

    # Detect signals
    cluster = detect_cluster_buying(transactions)
    exec_buys = detect_executive_buys(transactions)
    sentiment = calculate_buy_sell_sentiment(summary)
    large_trans = detect_large_transactions(transactions)

    # Get recent insider names
    recent_insiders = list(set(t.get("insider_name", "") for t in transactions[:10]))

    return {
        "ticker": ticker,
        "filings_count": summary.get("total_filings", 0),
        "unique_insiders": summary.get("unique_insiders", 0),
        "buys_count": summary.get("buys_count", 0),
        "sells_count": summary.get("sells_count", 0),
        "total_buy_value": summary.get("total_buy_value", 0),
        "total_sell_value": summary.get("total_sell_value", 0),
        "buy_sell_ratio": summary.get("buy_sell_ratio", 0),
        "net_activity": summary.get("net_activity", 0),
        "sentiment": sentiment.get("sentiment", "neutral"),
        "sentiment_score": sentiment.get("score", 50),
        "cluster_buying": cluster.get("detected", False),
        "executive_buying": exec_buys.get("detected", False),
        "large_transactions": len(large_trans),
        "recent_insiders": recent_insiders[:5],
    }


def format_value(value: float) -> str:
    """Format dollar value for display."""
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    elif abs(value) >= 1_000:
        return f"${value / 1_000:.0f}K"
    else:
        return f"${value:,.0f}"


def print_report(summaries: list, alerts: list):
    """Print analysis report to console."""
    print("\n" + "=" * 75)
    print("Insider Trading Analysis Report")
    print("=" * 75)

    print(f"\nTickers analyzed: {len(summaries)}")
    print(f"Alerts generated: {len(alerts)}")

    # Summary table
    print("\n{:<8} {:>8} {:>6} {:>6} {:>12} {:>12} {:>10}".format(
        "Ticker", "Filings", "Buys", "Sells", "Buy $", "Sell $", "Sentiment"
    ))
    print("-" * 75)

    for s in sorted(summaries, key=lambda x: x["sentiment_score"], reverse=True):
        buy_str = format_value(s["total_buy_value"])
        sell_str = format_value(s["total_sell_value"])
        sentiment = s["sentiment"].replace("_", " ").title()

        print("{:<8} {:>8} {:>6} {:>6} {:>12} {:>12} {:>10}".format(
            s["ticker"],
            s["filings_count"],
            s["buys_count"],
            s["sells_count"],
            buy_str,
            sell_str,
            sentiment[:10]
        ))

    # Alerts
    if alerts:
        print("\n" + "-" * 75)
        print("ALERTS")
        print("-" * 75)
        for alert in sorted(alerts, key=lambda x: x["priority"], reverse=True):
            priority = alert["priority_name"].upper()
            print(f"[{priority}] {alert['symbol']}: {alert['message']}")

    # Signals summary
    print("\n" + "-" * 75)
    print("SIGNAL SUMMARY")
    print("-" * 75)
    for s in summaries:
        signals = []
        if s.get("cluster_buying"):
            signals.append("Cluster Buy")
        if s.get("executive_buying"):
            signals.append("Exec Buy")
        if s.get("large_transactions", 0) > 0:
            signals.append(f"{s['large_transactions']} Large Trans")

        if signals:
            print(f"{s['ticker']}: {', '.join(signals)}")
        else:
            print(f"{s['ticker']}: No significant signals")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Analyze insider trading data")
    parser.add_argument("--data", type=Path,
                        default=Path(__file__).parent.parent / "data" / "insider_transactions.json",
                        help="Insider transactions data file")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent.parent / "output" / "insider_alerts.json",
                        help="Output alerts file")
    parser.add_argument("--threshold-cluster", type=int, default=2,
                        help="Minimum insiders for cluster alert")
    parser.add_argument("--threshold-large", type=float, default=500_000,
                        help="Large transaction threshold ($)")
    parser.add_argument("--quiet", action="store_true", help="Suppress report output")

    args = parser.parse_args()

    if not args.data.exists():
        print(f"Error: Data file not found: {args.data}", file=sys.stderr)
        print("Run fetch_form4.py first to fetch data.", file=sys.stderr)
        sys.exit(1)

    # Load insider data
    insider_data = load_insider_data(args.data)
    tickers = insider_data.get("tickers", [])

    if not tickers:
        print("No ticker data found")
        sys.exit(0)

    # Configure thresholds
    thresholds = {
        "cluster_buy_insiders": args.threshold_cluster,
        "executive_buy_value": 100_000,
        "large_transaction": args.threshold_large,
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
    watchlist_output = args.output.parent / "insider_watchlist_alerts.json"
    with open(watchlist_output, "w") as f:
        json.dump(watchlist_alerts, f, indent=2)

    print(f"Watchlist-compatible alerts: {watchlist_output}")


if __name__ == "__main__":
    main()

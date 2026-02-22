#!/usr/bin/env python3
"""
State Diffing for Watchlist Alerts

Compares current analysis with previous state to detect:
- New alerts (not in previous state)
- Resolved alerts (were in previous state, no longer triggered)
- Price changes (significant moves since last check)
- Signal changes (OBV divergence, volume surge, etc.)

Usage:
    python state_diff.py --current analysis.json --state state.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path) -> dict:
    """Load JSON file, return empty dict if not found."""
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def save_json(data: dict, path: Path):
    """Save JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def classify_alert(message: str) -> str:
    """Extract alert type from message pattern for diffing keys."""
    msg = message.lower()
    if "stop loss" in msg and ("triggered" in msg or "hit" in msg):
        return "stop_loss_hit"
    if "near stop" in msg:
        return "near_stop"
    if "buy target" in msg and "hit" in msg:
        return "buy_target_hit"
    if "approaching buy" in msg or "near buy" in msg:
        return "near_buy"
    if "sell target" in msg and "hit" in msg:
        return "sell_target_hit"
    if msg.startswith("up ") and "cost basis" in msg:
        return "pnl_gain"
    if msg.startswith("down ") and "cost basis" in msg:
        return "pnl_loss"
    return "unknown"


def extract_state_from_analysis(analysis: dict) -> dict:
    """Extract state info from portfolio analysis result.

    Expects flat JSON format from OCaml save_analysis:
        {"positions": [{"ticker": "PLTR", "current_price": 131.41,
                         "conviction_label": "moderately bullish", ...}],
         "alerts": [{"ticker": "PLTR", "priority": "HIGH", "message": "..."}]}
    """
    state = {
        "last_run": analysis.get("run_time", datetime.now(timezone.utc).isoformat()),
        "positions": {},
        "alerts": [],
    }

    for pos in analysis.get("positions", []):
        ticker = pos.get("ticker", "???")
        current_price = pos.get("current_price")

        state["positions"][ticker] = {
            "price": current_price if current_price is not None else 0,
            "pnl_pct": pos.get("pnl_pct"),
            "thesis_conviction": pos.get("conviction_label", "neutral"),
        }

        for alert in pos.get("alerts", []):
            message = alert.get("message", "")
            state["alerts"].append({
                "ticker": ticker,
                "type": classify_alert(message),
                "message": message,
                "priority": alert.get("priority", "NORMAL"),
            })

    return state


def diff_states(current: dict, previous: dict) -> dict:
    """
    Compare current state with previous state.

    Returns:
        {
            "new_alerts": [...],
            "resolved_alerts": [...],
            "price_changes": [...],
            "conviction_changes": [...],
        }
    """
    diff = {
        "new_alerts": [],
        "resolved_alerts": [],
        "price_changes": [],
        "conviction_changes": [],
        "summary": {},
    }

    current_positions = current.get("positions", {})
    previous_positions = previous.get("positions", {})

    # Compare positions
    for ticker, curr_data in current_positions.items():
        prev_data = previous_positions.get(ticker, {})

        # Price change
        curr_price = curr_data.get("price", 0)
        prev_price = prev_data.get("price", 0)

        if prev_price > 0 and curr_price > 0:
            pct_change = (curr_price - prev_price) / prev_price * 100
            if abs(pct_change) >= 2.0:  # 2% threshold for significant move
                diff["price_changes"].append({
                    "ticker": ticker,
                    "prev_price": prev_price,
                    "curr_price": curr_price,
                    "change_pct": pct_change,
                })

        # Conviction change
        curr_conviction = curr_data.get("thesis_conviction", "neutral")
        prev_conviction = prev_data.get("thesis_conviction", "neutral")

        if curr_conviction != prev_conviction:
            diff["conviction_changes"].append({
                "ticker": ticker,
                "prev": prev_conviction,
                "curr": curr_conviction,
            })

    # Compare alerts
    current_alert_keys = set()
    for alert in current.get("alerts", []):
        key = f"{alert.get('ticker')}:{alert.get('type')}"
        current_alert_keys.add(key)
        diff["new_alerts"].append(alert)

    previous_alert_keys = set()
    for alert in previous.get("alerts", []):
        key = f"{alert.get('ticker')}:{alert.get('type')}"
        previous_alert_keys.add(key)

    # Find truly new alerts (not in previous)
    diff["new_alerts"] = [
        a for a in current.get("alerts", [])
        if f"{a.get('ticker')}:{a.get('type')}" not in previous_alert_keys
    ]

    # Find resolved alerts (were in previous, not in current)
    diff["resolved_alerts"] = [
        a for a in previous.get("alerts", [])
        if f"{a.get('ticker')}:{a.get('type')}" not in current_alert_keys
    ]

    # Summary
    diff["summary"] = {
        "new_alerts": len(diff["new_alerts"]),
        "resolved_alerts": len(diff["resolved_alerts"]),
        "price_changes": len(diff["price_changes"]),
        "conviction_changes": len(diff["conviction_changes"]),
        "has_changes": any([
            diff["new_alerts"],
            diff["resolved_alerts"],
            diff["price_changes"],
            diff["conviction_changes"],
        ]),
    }

    return diff


def format_diff_report(diff: dict) -> str:
    """Format diff as human-readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append("WATCHLIST STATE CHANGES")
    lines.append("=" * 60)

    summary = diff.get("summary", {})
    if not summary.get("has_changes"):
        lines.append("\nNo significant changes since last run.")
        return "\n".join(lines)

    # New alerts
    new_alerts = diff.get("new_alerts", [])
    if new_alerts:
        lines.append(f"\n🚨 NEW ALERTS ({len(new_alerts)}):")
        for alert in new_alerts:
            priority = alert.get("priority", "Normal")
            ticker = alert.get("ticker", "???")
            message = alert.get("message", "")
            lines.append(f"  [{priority}] {ticker}: {message}")

    # Resolved alerts
    resolved = diff.get("resolved_alerts", [])
    if resolved:
        lines.append(f"\n✅ RESOLVED ALERTS ({len(resolved)}):")
        for alert in resolved:
            ticker = alert.get("ticker", "???")
            message = alert.get("message", "")
            lines.append(f"  {ticker}: {message}")

    # Price changes
    price_changes = diff.get("price_changes", [])
    if price_changes:
        lines.append(f"\n📊 PRICE CHANGES ({len(price_changes)}):")
        for pc in price_changes:
            ticker = pc.get("ticker", "???")
            prev = pc.get("prev_price", 0)
            curr = pc.get("curr_price", 0)
            pct = pc.get("change_pct", 0)
            arrow = "↑" if pct > 0 else "↓"
            lines.append(f"  {ticker}: ${prev:.2f} → ${curr:.2f} ({arrow}{abs(pct):.1f}%)")

    # Conviction changes
    conviction_changes = diff.get("conviction_changes", [])
    if conviction_changes:
        lines.append(f"\n📈 THESIS CHANGES ({len(conviction_changes)}):")
        for cc in conviction_changes:
            ticker = cc.get("ticker", "???")
            prev = cc.get("prev", "neutral")
            curr = cc.get("curr", "neutral")
            lines.append(f"  {ticker}: {prev} → {curr}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Compare watchlist states")
    parser.add_argument("--current", "-c", required=True, type=Path, help="Current analysis JSON")
    parser.add_argument("--state", "-s", required=True, type=Path, help="Previous state JSON")
    parser.add_argument("--output", "-o", type=Path, help="Output diff JSON")
    parser.add_argument("--update-state", "-u", action="store_true", help="Update state file with current")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    # Load files
    current_analysis = load_json(args.current)
    previous_state = load_json(args.state)

    # Extract current state from analysis
    current_state = extract_state_from_analysis(current_analysis)

    # Compute diff
    diff = diff_states(current_state, previous_state)

    # Output
    if args.json:
        print(json.dumps(diff, indent=2))
    else:
        print(format_diff_report(diff))

    # Save diff if requested
    if args.output:
        save_json(diff, args.output)
        print(f"\nDiff saved to {args.output}")

    # Update state file if requested
    if args.update_state:
        save_json(current_state, args.state)
        print(f"State updated: {args.state}")

    # Exit with code based on whether there are changes
    sys.exit(0 if diff["summary"]["has_changes"] else 0)


if __name__ == "__main__":
    main()

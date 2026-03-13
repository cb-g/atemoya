#!/usr/bin/env python3
"""
Send pre-earnings straddle scan results via ntfy.sh notification.

Reads signal_scan.csv and sends upcoming earnings trade ideas.
Reads NTFY_TOPIC from .env at project root.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[3]))
from lib.python.notify import send_notification, get_topic

DEFAULT_SCAN = Path(__file__).resolve().parents[1] / "output" / "signal_scan.csv"
MODULE_NAME = "Pre-Earnings Straddle"


def format_message(df: pd.DataFrame) -> str:
    """Format actionable signals into a compact notification body."""
    actionable = df[df["signal"].str.contains("BUY|SELL|IMMINENT")]
    if actionable.empty:
        return ""

    header = (
        "Ranked by urgency (days to earnings).\n"
        "SELL=straddle expensive. BUY=straddle cheap.\n"
        "Xd=days to earnings.\n"
        "---"
    )

    lines = []
    for _, row in actionable.iterrows():
        seg = f" [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
        icon = "\U0001f534" if "SELL" in row["signal"] else "\U0001f7e2"  # red/green circle
        lines.append(
            f"{icon} {row['ticker']}: {row['signal']} ({row['days_to_earnings']}d, "
            f"straddle={row['straddle_pct']:.1f}%){seg}"
        )

    return header + "\n" + "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Send pre-earnings straddle scan results via ntfy.sh"
    )
    parser.add_argument("--scan", default=str(DEFAULT_SCAN))
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    scan_path = Path(args.scan)
    if not scan_path.exists():
        print(f"Error: {scan_path} not found. Run scan_signals.py first.", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(scan_path)
    message = format_message(df)

    if not message:
        print("No actionable earnings signals to send.")
        return

    actionable_count = len(df[df["signal"].str.contains("BUY|SELL|IMMINENT")])
    title = f"{MODULE_NAME}: {actionable_count} earnings plays"

    if args.dry_run:
        print(f"Title: {title}")
        print(f"---")
        print(message)
        return

    topic = get_topic()
    if not topic:
        print("Error: NTFY_TOPIC not set in .env or environment", file=sys.stderr)
        sys.exit(1)

    print(f"Sending {actionable_count} signals via ntfy...")
    success = send_notification(
        topic=topic, message=message, title=title,
        tags=[],
    )
    if success:
        print("Notification sent.")
    else:
        print("Notification failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

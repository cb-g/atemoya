#!/usr/bin/env python3
"""
Send variance swap signal scan results via ntfy.sh notification.

Reads signal_scan.csv and sends actionable trade ideas.
Reads NTFY_TOPIC from .env at project root.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[3]))
from lib.python.notify import send_notification, get_topic

DEFAULT_SCAN = Path(__file__).resolve().parents[1] / "output" / "signal_scan.csv"
MODULE_NAME = "Variance Swaps"


def format_message(df: pd.DataFrame) -> str:
    """Format actionable signals into a compact notification body."""
    actionable = df[~df["signal"].str.contains("NEUTRAL")]
    if actionable.empty:
        return ""

    header = (
        "Ranked best to worst by |z-score|.\n"
        "SELL=vol expensive, short vol. BUY=vol cheap, long vol.\n"
        "'lean'=moderate conviction.\n"
        "---"
    )

    lines = []
    for _, row in actionable.iterrows():
        seg = f" [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
        direction = "SELL" if "SELL" in row["signal"] else "BUY"
        icon = "\U0001f534" if "SELL" in row["signal"] else "\U0001f7e2"  # red/green circle
        strength = "" if "LEAN" not in row["signal"] else " lean"
        lines.append(
            f"{icon} {row['ticker']}: {direction} var (z={row['max_abs_z']:.1f}{strength}) IV={row['atm_iv_latest']*100:.0f}%{seg}"
        )

    return header + "\n" + "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Send variance swap scan results via ntfy.sh"
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
        print("No actionable signals to send.")
        return

    actionable_count = len(df[~df["signal"].str.contains("NEUTRAL")])
    title = f"{MODULE_NAME}: {actionable_count} trade ideas"

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

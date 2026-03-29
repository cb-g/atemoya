#!/usr/bin/env python3
"""
Send skew signal scan results via ntfy.sh notification.

Reads signal_scan.csv and sends actionable trade ideas as a morning
notification. Designed to run from cron after the scanner completes.

Reads NTFY_TOPIC from .env at project root (same as watchlist module).
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[3]))
from lib.python.notify import send_notification, get_topic, get_server

DEFAULT_SCAN = Path(__file__).resolve().parents[1] / "output" / "signal_scan.csv"
MODULE_NAME = "Skew Trading"


def format_message(df: pd.DataFrame) -> str:
    """Format actionable signals into a compact notification body."""
    actionable = df[~df["signal"].str.contains("NEUTRAL")]
    if actionable.empty:
        return ""

    header = (
        "Ranked best to worst by |z-score|.\n"
        "RR=risk reversal, BF=butterfly.\n"
        "LONG=buy, SHORT=sell. 'lean'=moderate conviction.\n"
        "---"
    )

    lines = []
    for _, row in actionable.iterrows():
        seg = f" [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
        strat = "BF" if "WINGS" in row["signal"] else "RR"
        direction = "SHORT" if "SHORT" in row["signal"] else "LONG"
        icon = "\U0001f534" if "SHORT" in row["signal"] else "\U0001f7e2"  # red/green circle
        strength = "" if "LEAN" not in row["signal"] else " lean"
        lines.append(
            f"{icon} {row['ticker']}: {direction} {strat} (z={row['max_abs_z']:.1f}{strength}){seg}"
        )

    regime_line = ""
    if "macro_regime" in actionable.columns and actionable.iloc[0].get("macro_regime"):
        r = actionable.iloc[0]
        regime_line = f"\U0001f4ca Regime: {r['macro_regime']} | {r['risk_sentiment']}\n"

    return regime_line + header + "\n" + "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Send skew signal scan results via ntfy.sh"
    )
    parser.add_argument(
        "--scan", default=str(DEFAULT_SCAN),
        help="Path to signal_scan.csv",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print without sending")

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
        topic=topic,
        message=message,
        title=title,
        tags=[],
    )

    if success:
        print("Notification sent.")
    else:
        print("Notification failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

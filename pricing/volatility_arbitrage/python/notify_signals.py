#!/usr/bin/env python3
"""
Send volatility arbitrage scan results via ntfy.sh notification.

Reads signal_scan.csv and sends actionable IV vs RV divergence trade ideas.
Reads NTFY_TOPIC from .env at project root.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[3]))
from lib.python.notify import send_notification, get_topic

DEFAULT_SCAN = Path(__file__).resolve().parents[1] / "output" / "signal_scan.csv"
MODULE_NAME = "Vol Arbitrage"


def format_message(df: pd.DataFrame) -> str:
    """Format actionable signals into a compact notification body."""
    actionable = df[~df["signal"].str.contains("NEUTRAL")]
    if actionable.empty:
        return ""

    header = (
        "Ranked by |z-score| (most extreme first).\n"
        "SELL=IV expensive vs RV, short vol.\n"
        "BUY=IV cheap vs RV, long vol.\n"
        "'lean'=moderate conviction.\n"
        "---"
    )

    lines = []
    for _, row in actionable.iterrows():
        seg = f" [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
        direction = "SELL" if "SELL" in row["signal"] else "BUY"
        icon = "\U0001f534" if "SELL" in row["signal"] else "\U0001f7e2"  # red=sell, green=buy
        strength = "" if "LEAN" not in row["signal"] else " lean"
        z_str = f" z={row['spread_z']:+.1f}" if not np.isnan(row.get('spread_z', np.nan)) else ""
        lines.append(
            f"{icon} {row['ticker']}: {direction} vol{strength} "
            f"IV/RV={row['iv_rv_ratio']:.2f}{z_str} "
            f"IV={row['atm_iv']*100:.0f}%{seg}"
        )

    return header + "\n" + "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Send vol arb scan results via ntfy.sh"
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
        print("No actionable vol arb signals to send.")
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

#!/usr/bin/env python3
"""
Send forward factor scan results via ntfy.sh notification.

Reads signal_scan.csv and sends actionable calendar spread trade ideas.
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
MODULE_NAME = "Forward Factor"


def format_message(df: pd.DataFrame) -> str:
    """Format actionable signals into a compact notification body."""
    actionable = df[~df["signal"].str.contains("NEUTRAL")]
    if actionable.empty:
        return ""

    header = (
        "Ranked by forward factor (highest first).\n"
        "SELL CAL=sell front, buy back (calendar spread).\n"
        "FF>=1.0 extreme, >=0.5 strong, >=0.2 valid.\n"
        "'lean'=valid but not strong.\n"
        "---"
    )

    lines = []
    for _, row in actionable.iterrows():
        seg = f" [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
        icon = "\U0001f534" if row["forward_factor"] >= 0.50 else "\U0001f7e1"  # red=strong, yellow=valid
        strength = ""
        if row["forward_factor"] >= 1.0:
            strength = " EXTREME"
        elif row["forward_factor"] >= 0.5:
            strength = " strong"
        z_str = f" z={row['ff_z']:+.1f}" if not np.isnan(row.get('ff_z', np.nan)) else ""
        lines.append(
            f"{icon} {row['ticker']}: FF={row['forward_factor']:.2f}{strength} "
            f"[{row['dte_pair']}]{z_str}{seg}"
        )

    regime_line = ""
    if "macro_regime" in actionable.columns and actionable.iloc[0].get("macro_regime"):
        r = actionable.iloc[0]
        regime_line = f"\U0001f4ca Regime: {r['macro_regime']} | {r['risk_sentiment']}\n"

    return regime_line + header + "\n" + "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Send forward factor scan results via ntfy.sh"
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
        print("No actionable forward factor signals to send.")
        return

    actionable_count = len(df[~df["signal"].str.contains("NEUTRAL")])
    title = f"{MODULE_NAME}: {actionable_count} calendar spread ideas"

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

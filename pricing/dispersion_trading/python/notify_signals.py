#!/usr/bin/env python3
"""
Send dispersion trading scan results via ntfy.sh notification.

Reads signal_scan.csv and sends correlation mispricing trade ideas.
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
MODULE_NAME = "Dispersion"


def format_message(df: pd.DataFrame) -> str:
    """Format signal into a compact notification body."""
    if df.empty:
        return ""

    row = df.iloc[0]
    if "NEUTRAL" in row["signal"]:
        return ""

    header = (
        "Index vs constituent IV divergence.\n"
        "LONG=buy constituents, sell index (corr cheap).\n"
        "SHORT=sell constituents, buy index (corr expensive).\n"
        "---"
    )

    icon = "\U0001f7e2" if "LONG" in row["signal"] else "\U0001f534"
    z_str = f" z={row['dispersion_z']:+.1f}" if not np.isnan(row.get('dispersion_z', np.nan)) else ""

    line = (
        f"{icon} {row['index']}: {row['signal']}{z_str}\n"
        f"  Disp={row['dispersion_level']*100:+.1f}% "
        f"Impl={row['implied_correlation']:.2f} "
        f"Real={row['realized_correlation']:.2f}"
    )

    regime_line = ""
    if "macro_regime" in row and row.get("macro_regime"):
        regime_line = f"\U0001f4ca Regime: {row['macro_regime']} | {row['risk_sentiment']}\n"

    return regime_line + header + "\n" + line


def main():
    parser = argparse.ArgumentParser(
        description="Send dispersion trading scan results via ntfy.sh"
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
        print("No actionable dispersion signals to send.")
        return

    title = f"{MODULE_NAME}: correlation mispricing detected"

    if args.dry_run:
        print(f"Title: {title}")
        print(f"---")
        print(message)
        return

    topic = get_topic()
    if not topic:
        print("Error: NTFY_TOPIC not set in .env or environment", file=sys.stderr)
        sys.exit(1)

    print(f"Sending dispersion signal via ntfy...")
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

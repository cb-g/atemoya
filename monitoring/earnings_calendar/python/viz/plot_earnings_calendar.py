#!/usr/bin/env python3
"""
Earnings Calendar Visualization

Creates a 2-panel dashboard:
1. Timeline of upcoming earnings, color-coded by urgency
2. Historical EPS surprise % per ticker (last 4 quarters)

Usage:
    python plot_earnings_calendar.py --input data/earnings_calendar.json
    python plot_earnings_calendar.py -i data/earnings_calendar.json -o output/
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

setup_dark_mode()

C = {
    "green": COLORS["green"],
    "red": COLORS["red"],
    "yellow": COLORS["yellow"],
    "blue": COLORS["blue"],
    "gray": COLORS["gray"],
    "fg": COLORS["fg"],
    "bg": COLORS["bg"],
    "bg_light": COLORS["bg_light"],
    "cyan": COLORS["cyan"],
    "orange": COLORS["orange"],
}


def urgency_color(days: int) -> str:
    """Return color based on days until earnings."""
    if days <= 3:
        return C["red"]
    elif days <= 7:
        return C["orange"]
    elif days <= 14:
        return C["yellow"]
    else:
        return C["green"]


def draw_upcoming_timeline(ax, tickers_data: list, days_ahead: int):
    """Draw horizontal timeline of upcoming earnings."""
    ax.set_title("Upcoming Earnings Calendar", fontsize=12, fontweight="bold",
                 color=C["fg"], pad=10)

    # Filter to tickers with valid upcoming earnings
    upcoming = []
    for t in tickers_data:
        up = t.get("upcoming")
        if (up and isinstance(up, dict) and up.get("date")
                and up.get("days_away") is not None
                and not up.get("error")):
            try:
                date_obj = datetime.strptime(up["date"], "%Y-%m-%d")
            except ValueError:
                continue
            upcoming.append({
                "ticker": t["ticker"],
                "date": date_obj,
                "days_away": up["days_away"],
                "timing": up.get("timing") or "Unknown",
                "eps_est": up.get("eps_estimate_avg"),
            })

    if not upcoming:
        ax.text(0.5, 0.5, "No upcoming earnings found",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=12, color=C["gray"])
        ax.set_facecolor(C["bg_light"])
        return

    # Sort by date (soonest first)
    upcoming.sort(key=lambda x: x["date"])

    today = datetime.now()
    max_date = max(u["date"] for u in upcoming)
    x_end = max(max_date, today + timedelta(days=days_ahead)) + timedelta(days=3)

    for i, u in enumerate(upcoming):
        color = urgency_color(u["days_away"])

        # Marker
        ax.scatter([u["date"]], [i], s=180, c=color, marker="D",
                   zorder=5, edgecolors="none")

        # Days + timing label
        timing_str = u["timing"] if u["timing"] != "Unknown" else ""
        label = f'{u["days_away"]}d {timing_str}'.strip()
        ax.annotate(label, (u["date"], i), textcoords="offset points",
                    xytext=(14, 0), fontsize=9, color=C["fg"], va="center")

        # EPS estimate
        if u["eps_est"] is not None:
            ax.annotate(f'EPS est: ${u["eps_est"]:.2f}', (u["date"], i),
                        textcoords="offset points", xytext=(14, -13),
                        fontsize=7, color=C["gray"], va="center")

    # Today line
    ax.axvline(x=today, color=C["cyan"], linewidth=1.2, linestyle="--",
               alpha=0.7, label="Today")

    ax.set_yticks(range(len(upcoming)))
    ax.set_yticklabels([u["ticker"] for u in upcoming], fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=10))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
    ax.set_xlim(today - timedelta(days=1), x_end)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.15, color=C["gray"])
    ax.legend(loc="upper right", fontsize=8)


def draw_surprise_history(ax, tickers_data: list):
    """Draw EPS surprise history as horizontal bar chart."""
    ax.set_title("EPS Surprise History (Avg Last 4 Quarters)", fontsize=12,
                 fontweight="bold", color=C["fg"], pad=10)

    # Collect tickers with surprise data
    valid = []
    for t in tickers_data:
        history = t.get("history", [])
        surprises = [h for h in history if h.get("surprise_pct") is not None][:4]
        if surprises:
            avg_surprise = np.mean([s["surprise_pct"] for s in surprises])
            valid.append({
                "ticker": t["ticker"],
                "avg_surprise": avg_surprise,
                "n_quarters": len(surprises),
            })

    if not valid:
        ax.text(0.5, 0.5, "No EPS surprise data available",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=12, color=C["gray"])
        ax.set_facecolor(C["bg_light"])
        return

    # Sort by avg surprise descending
    valid.sort(key=lambda x: x["avg_surprise"], reverse=True)

    tickers_labels = [v["ticker"] for v in valid]
    y_positions = np.arange(len(valid))
    bar_height = 0.55

    for i, v in enumerate(valid):
        avg = v["avg_surprise"]
        color = C["green"] if avg >= 0 else C["red"]
        ax.barh(i, avg, height=bar_height, color=color, alpha=0.8, edgecolor="none")

        x_offset = 0.3 if avg >= 0 else -0.3
        ha = "left" if avg >= 0 else "right"
        ax.text(avg + x_offset, i, f"{avg:+.1f}%", va="center", ha=ha,
                fontsize=9, color=C["fg"])

    ax.axvline(x=0, color=C["gray"], linewidth=0.5, alpha=0.5)
    ax.set_yticks(y_positions)
    ax.set_yticklabels(tickers_labels, fontsize=9)
    ax.set_xlabel("Avg EPS Surprise (%)", fontsize=9, color=C["gray"])
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.15, color=C["gray"])


def plot_earnings_calendar(data: dict, output_path: str):
    """Create the 2-panel earnings calendar dashboard."""
    tickers_data = data.get("tickers", [])
    days_ahead = data.get("days_ahead", 14)
    fetch_time = data.get("fetch_time", "")[:10]

    fig, (ax_top, ax_bottom) = plt.subplots(
        2, 1, figsize=(14, 9),
        gridspec_kw={"height_ratios": [1.2, 1], "hspace": 0.35},
    )
    fig.suptitle(f"Earnings Calendar Dashboard  \u2014  {fetch_time}",
                 fontsize=14, fontweight="bold", color=C["fg"])

    draw_upcoming_timeline(ax_top, tickers_data, days_ahead)
    draw_surprise_history(ax_bottom, tickers_data)

    fig.subplots_adjust(top=0.92)
    save_figure(fig, output_path, dpi=150)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Plot earnings calendar dashboard")
    parser.add_argument("--input", "-i", required=True,
                        help="Input earnings calendar JSON")
    parser.add_argument("--output-dir", "-o",
                        default=str(Path(__file__).resolve().parents[2] / "output"),
                        help="Output directory")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        project_root = Path(__file__).parents[4]
        input_path = project_root / input_path

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        print("Run fetch_earnings_calendar.py first.")
        sys.exit(1)

    with open(input_path) as f:
        data = json.load(f)

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        project_root = Path(__file__).parents[4]
        output_dir = project_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = str(output_dir / "earnings_calendar.png")
    plot_earnings_calendar(data, output_path)


if __name__ == "__main__":
    main()

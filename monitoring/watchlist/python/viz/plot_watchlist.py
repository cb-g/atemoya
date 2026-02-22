#!/usr/bin/env python3
"""
Watchlist Portfolio Visualization

Creates a 2x2 dashboard showing:
1. Portfolio P&L overview
2. Thesis conviction scores
3. Alert summary
4. Price targets vs current
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
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


def load_result(path: str) -> dict:
    """Load watchlist analysis result JSON file."""
    with open(path) as f:
        return json.load(f)


def draw_pnl_overview(ax, positions: list):
    """Draw P&L bar chart for positions with market data."""
    ax.set_title("Position P&L Overview", fontsize=11, fontweight="bold", color=C["fg"])

    pos_with_pnl = [p for p in positions if p.get("pnl_pct") is not None]

    if not pos_with_pnl:
        ax.text(
            0.5, 0.5, "No P&L data available",
            ha="center", va="center", transform=ax.transAxes,
            fontsize=12, color=C["gray"],
        )
        ax.set_facecolor(C["bg_light"])
        return

    tickers = [p["ticker"] for p in pos_with_pnl]
    pnl_pcts = [p["pnl_pct"] for p in pos_with_pnl]

    colors = [C["green"] if p >= 0 else C["red"] for p in pnl_pcts]

    y_pos = np.arange(len(tickers))
    bars = ax.barh(y_pos, pnl_pcts, color=colors, alpha=0.8, edgecolor="none", height=0.6)

    for bar, pnl in zip(bars, pnl_pcts):
        x_pos = bar.get_width() + 0.5 if pnl >= 0 else bar.get_width() - 0.5
        ax.text(
            x_pos, bar.get_y() + bar.get_height() / 2,
            f"{pnl:+.1f}%", va="center",
            ha="left" if pnl >= 0 else "right", fontsize=9, color=C["fg"],
        )

    ax.axvline(x=0, color=C["gray"], linewidth=0.5, alpha=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(tickers)
    ax.set_xlabel("P&L (%)")
    ax.invert_yaxis()


def draw_thesis_scores(ax, positions: list):
    """Draw thesis conviction scores as diverging bar chart."""
    ax.set_title("Thesis Conviction Scores", fontsize=11, fontweight="bold", color=C["fg"])

    tickers = [p["ticker"] for p in positions]
    bull_scores = [p["bull_score"] for p in positions]
    bear_scores = [-p["bear_score"] for p in positions]

    y_pos = np.arange(len(tickers))

    ax.barh(y_pos, bull_scores, color=C["green"], alpha=0.8, label="Bull", height=0.6)
    ax.barh(y_pos, bear_scores, color=C["red"], alpha=0.8, label="Bear", height=0.6)

    ax.axvline(x=0, color=C["gray"], linewidth=1, alpha=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(tickers)
    ax.set_xlabel("Thesis Score")
    ax.legend(loc="lower right", fontsize=8)
    ax.invert_yaxis()

    for i, p in enumerate(positions):
        conv = p["conviction_label"]
        ax.text(0.98, i, conv, va="center", ha="right", fontsize=8, color=C["gray"],
                transform=ax.get_yaxis_transform())


def draw_alerts_summary(ax, alerts: list):
    """Draw alerts summary."""
    ax.axis("off")
    ax.set_facecolor(C["bg_light"])
    ax.set_title("Active Alerts", fontsize=11, fontweight="bold", color=C["fg"])

    if not alerts:
        ax.text(
            0.5, 0.5, "No alerts triggered",
            ha="center", va="center", transform=ax.transAxes,
            fontsize=12, color=C["green"],
        )
        return

    priority_colors = {
        "URGENT": C["red"],
        "HIGH": C["orange"],
        "NORMAL": C["blue"],
        "INFO": C["gray"],
    }

    y_start = 0.92
    y_step = min(0.11, 0.85 / max(len(alerts[:8]), 1))
    for i, alert in enumerate(alerts[:8]):
        priority = alert.get("priority", "INFO")
        color = priority_colors.get(priority, C["gray"])
        ticker = alert.get("ticker", "N/A")
        message = alert.get("message", "Alert")

        if len(message) > 45:
            message = message[:42] + "..."

        ax.text(
            0.02, y_start - i * y_step, f"[{priority}]",
            color=color, fontweight="bold", fontsize=8,
            transform=ax.transAxes,
        )
        ax.text(
            0.20, y_start - i * y_step, f"{ticker}: {message}",
            fontsize=8, transform=ax.transAxes, color=C["fg"],
        )

    if len(alerts) > 8:
        ax.text(
            0.5, 0.03, f"...and {len(alerts) - 8} more alerts",
            ha="center", fontsize=9, color=C["gray"], transform=ax.transAxes,
        )


def draw_price_targets(ax, positions: list):
    """Draw price targets vs current price, normalized per row."""
    ax.set_title("Price Targets vs Current", fontsize=11, fontweight="bold", color=C["fg"])

    valid = []
    for p in positions:
        market = p.get("market")
        levels = p.get("levels", {})
        if market and (levels.get("buy_target") or levels.get("sell_target")):
            valid.append({
                "ticker": p["ticker"],
                "current": market["current_price"],
                "buy": levels.get("buy_target"),
                "sell": levels.get("sell_target"),
                "stop": levels.get("stop_loss"),
            })

    if not valid:
        ax.text(
            0.5, 0.5, "No price targets set",
            ha="center", va="center", transform=ax.transAxes,
            fontsize=12, color=C["gray"],
        )
        return

    ax.set_xlim(-0.05, 1.15)
    ax.set_ylim(-0.5, len(valid) - 0.5)
    ax.set_xticks([])
    ax.set_yticks([])

    for i, pos in enumerate(valid[:6]):
        y = len(valid) - i - 1
        current = pos["current"]

        prices = [v for v in [pos["stop"], pos["buy"], current, pos["sell"]] if v is not None]
        min_p, max_p = min(prices), max(prices)
        range_p = max_p - min_p if max_p > min_p else current * 0.1
        pad_min = min_p - range_p * 0.1
        pad_max = max_p + range_p * 0.1
        span = pad_max - pad_min if pad_max > pad_min else 1.0

        def norm(v):
            return 0.12 + (v - pad_min) / span * 0.85

        ax.plot(
            [norm(pad_min), norm(pad_max)], [y, y],
            color=C["bg_light"], linewidth=8, solid_capstyle="round",
        )

        ax.scatter([norm(current)], [y], s=120, c=C["blue"], marker="|", zorder=5)

        if pos["buy"]:
            ax.scatter([norm(pos["buy"])], [y], s=80, c=C["green"], marker="^", zorder=4)
        if pos["sell"]:
            ax.scatter([norm(pos["sell"])], [y], s=80, c=C["orange"], marker="v", zorder=4)
        if pos["stop"]:
            ax.scatter([norm(pos["stop"])], [y], s=80, c=C["red"], marker="x", zorder=4)

        ax.text(0.0, y, pos["ticker"], ha="left", va="center", fontsize=9, fontweight="bold", color=C["fg"])
        ax.text(norm(current), y + 0.35, f"${current:.0f}", ha="center", va="bottom", fontsize=7, color=C["blue"])

    ax.scatter([], [], c=C["blue"], marker="|", s=80, label="Current")
    ax.scatter([], [], c=C["green"], marker="^", s=50, label="Buy Target")
    ax.scatter([], [], c=C["orange"], marker="v", s=50, label="Sell Target")
    ax.scatter([], [], c=C["red"], marker="x", s=50, label="Stop Loss")
    ax.legend(loc="upper right", fontsize=7, ncol=2)


def plot_watchlist(data: dict, output_path: str):
    """Create the full watchlist visualization."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Portfolio Watchlist Dashboard", fontsize=14, fontweight="bold", color=C["fg"])

    positions = data.get("positions", [])
    alerts = data.get("alerts", [])

    draw_pnl_overview(axes[0, 0], positions)
    draw_thesis_scores(axes[0, 1], positions)
    draw_alerts_summary(axes[1, 0], alerts)
    draw_price_targets(axes[1, 1], positions)

    plt.tight_layout()
    save_figure(fig, output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Plot watchlist analysis")
    parser.add_argument("--input", required=True, help="Input watchlist JSON file")
    parser.add_argument("--output", help="Output path")
    args = parser.parse_args()

    data = load_result(args.input)

    if args.output:
        output_path = args.output
    else:
        output_dir = Path(__file__).resolve().parent.parent.parent / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / "watchlist_dashboard.svg")

    plot_watchlist(data, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Plot liquidity analysis results.
"""

import json
import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure
from lib.python.retry import retry_with_backoff

setup_dark_mode()


def load_results(output_dir: Path) -> dict:
    """Load liquidity analysis results from OCaml output."""
    results_file = output_dir / "liquidity_results.json"
    if not results_file.exists():
        raise FileNotFoundError(f"Results not found: {results_file}. Run OCaml liquidity analysis first.")

    with open(results_file) as f:
        return json.load(f)


def plot_liquidity_dashboard(results: list, output_dir: Path):
    """Create comprehensive liquidity dashboard."""

    if not results:
        print("No results to plot")
        return

    # Sort by liquidity score
    results.sort(key=lambda x: x['liquidity_score'], reverse=True)

    tickers = [r['ticker'] for r in results]
    liq_scores = [r['liquidity_score'] for r in results]
    rel_volumes = [r['relative_volume'] for r in results]
    signal_scores = [r['signal_score'] for r in results]
    amihud = [min(r['amihud_ratio'], 10) for r in results]  # Cap for display

    # Create figure
    fig = plt.figure(figsize=(16, 12))
    fig.suptitle("Liquidity Analysis Dashboard", fontsize=14, fontweight="bold", color="white")
    fig.patch.set_facecolor(COLORS['bg'])

    gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)

    # 1. Liquidity Score Bar Chart (top left)
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor(COLORS['bg_light'])

    colors = []
    for score in liq_scores:
        if score >= 70:
            colors.append(COLORS['green'])  # Green
        elif score >= 50:
            colors.append(COLORS['yellow'])  # Yellow
        else:
            colors.append(COLORS['red'])  # Red

    bars = ax1.barh(tickers, liq_scores, color=colors, edgecolor="none")
    ax1.axvline(x=50, color="white", linestyle="--", linewidth=1, alpha=0.5)
    ax1.axvline(x=70, color=COLORS['green'], linestyle="--", linewidth=1, alpha=0.5)
    ax1.set_xlabel("Liquidity Score (0-100)", color="white")
    ax1.set_title("Liquidity Ranking", color="white", fontsize=11)
    ax1.set_xlim(0, 100)
    ax1.tick_params(colors="white")
    for spine in ax1.spines.values():
        spine.set_color(COLORS['gray'])

    # Add score labels
    for bar, score in zip(bars, liq_scores):
        ax1.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
                 f"{score:.0f}", va="center", ha="left", color="white", fontsize=9)

    # 2. Relative Volume (top right)
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor(COLORS['bg_light'])

    rv_colors = [COLORS['red'] if rv > 2 else COLORS['yellow'] if rv > 1.5 else COLORS['green'] for rv in rel_volumes]
    bars2 = ax2.barh(tickers, rel_volumes, color=rv_colors, edgecolor="none")
    ax2.axvline(x=1.0, color="white", linestyle="-", linewidth=1, alpha=0.5)
    ax2.axvline(x=2.0, color=COLORS['red'], linestyle="--", linewidth=1, alpha=0.5, label="Surge (2x)")
    ax2.set_xlabel("Relative Volume (x avg)", color="white")
    ax2.set_title("Volume Activity", color="white", fontsize=11)
    ax2.tick_params(colors="white")
    ax2.legend(facecolor=COLORS['bg_light'], edgecolor=COLORS['gray'], labelcolor="white", fontsize=8)
    for spine in ax2.spines.values():
        spine.set_color(COLORS['gray'])

    # 3. Signal Score (bottom left)
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.set_facecolor(COLORS['bg_light'])

    sig_colors = [COLORS['green'] if s > 10 else COLORS['red'] if s < -10 else COLORS['yellow'] for s in signal_scores]
    bars3 = ax3.barh(tickers, signal_scores, color=sig_colors, edgecolor="none")
    ax3.axvline(x=0, color="white", linestyle="-", linewidth=1, alpha=0.5)
    ax3.axvline(x=10, color=COLORS['green'], linestyle="--", linewidth=0.5, alpha=0.5)
    ax3.axvline(x=-10, color=COLORS['red'], linestyle="--", linewidth=0.5, alpha=0.5)
    ax3.set_xlabel("Signal Score", color="white")
    ax3.set_title("Predictive Signal Strength", color="white", fontsize=11)
    ax3.tick_params(colors="white")
    for spine in ax3.spines.values():
        spine.set_color(COLORS['gray'])

    # Add signal labels — inside bar if it's long enough, outside otherwise
    x_min, x_max = ax3.get_xlim()
    bar_threshold = (x_max - x_min) * 0.25
    for bar, result in zip(bars3, results):
        signal = result['composite_signal']
        x_pos = bar.get_width()
        y_pos = bar.get_y() + bar.get_height() / 2
        if abs(x_pos) > bar_threshold:
            # Label inside bar
            ha = "right" if x_pos >= 0 else "left"
            offset = -1 if x_pos >= 0 else 1
            ax3.text(x_pos + offset, y_pos, signal,
                     va="center", ha=ha, color="white", fontsize=8, fontweight="bold")
        else:
            # Label outside bar
            ha = "left" if x_pos >= 0 else "right"
            offset = 1 if x_pos >= 0 else -1
            ax3.text(x_pos + offset, y_pos, signal,
                     va="center", ha=ha, color="white", fontsize=8)

    # 4. Summary Table (bottom right)
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor(COLORS['bg_light'])
    ax4.axis("off")
    ax4.set_title("Liquidity Summary", color="white", fontsize=11, pad=10)

    # Build table
    table_data = []
    headers = ["Ticker", "Score", "Tier", "Signal"]

    for r in results[:10]:  # Top 10
        table_data.append([
            r['ticker'],
            f"{r['liquidity_score']:.0f}",
            r['liquidity_tier'],
            r['composite_signal'],
        ])

    table = ax4.table(
        cellText=table_data,
        colLabels=headers,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.5)

    # Style table
    for key in table.get_celld().keys():
        cell = table.get_celld()[key]
        cell.set_facecolor(COLORS['bg_light'])
        cell.set_edgecolor(COLORS['gray'])
        cell.set_text_props(color="white")

        if key[0] == 0:  # Header
            cell.set_facecolor(COLORS['bg_dark'])
            cell.set_text_props(fontweight="bold", color="white")
        elif key[1] == 2:  # Tier column
            row_idx = key[0] - 1
            if row_idx < len(results):
                tier = results[row_idx]['liquidity_tier']
                if tier in ['Excellent', 'Good']:
                    cell.set_facecolor(COLORS['green'])
                elif tier == 'Fair':
                    cell.set_facecolor(COLORS['yellow'])
                else:
                    cell.set_facecolor(COLORS['red'])
        elif key[1] == 3:  # Signal column
            row_idx = key[0] - 1
            if row_idx < len(results):
                sig = results[row_idx]['composite_signal']
                if 'Bullish' in sig:
                    cell.set_facecolor(COLORS['green'])
                elif 'Bearish' in sig:
                    cell.set_facecolor(COLORS['red'])

    plt.tight_layout(rect=[0, 0.02, 1, 0.96])

    # Save
    output_file = output_dir / "liquidity_dashboard.png"
    save_figure(fig, output_file, dpi=150)
    plt.close()


def plot_single_ticker(ticker: str, output_dir: Path):
    """Plot detailed analysis for a single ticker."""
    import yfinance as yf

    print(f"Fetching data for {ticker}...")
    stock = yf.Ticker(ticker)
    hist = retry_with_backoff(lambda: stock.history(period="6mo"))

    if hist.empty:
        print(f"No data for {ticker}")
        return

    close = hist['Close']
    volume = hist['Volume']

    # Calculate OBV
    direction = np.sign(close.diff())
    signed_volume = volume * direction
    obv = signed_volume.cumsum()

    # Calculate A/D
    high = hist['High']
    low = hist['Low']
    clv = ((close - low) - (high - close)) / (high - low + 1e-10)
    ad = (clv * volume).cumsum()

    # Create figure
    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
    fig.suptitle(f"Liquidity Analysis: {ticker}", fontsize=14, fontweight="bold", color="white")
    fig.patch.set_facecolor(COLORS['bg'])

    for ax in axes:
        ax.set_facecolor(COLORS['bg_light'])
        ax.tick_params(colors="white")
        for spine in ax.spines.values():
            spine.set_color(COLORS['gray'])

    # 1. Price
    axes[0].plot(close.index, close.values, color=COLORS['green'], linewidth=1.5)
    axes[0].set_ylabel("Price ($)", color="white")
    axes[0].set_title("Price", color="white", fontsize=10)

    # 2. Volume with average
    avg_vol = volume.rolling(20).mean()
    axes[1].bar(volume.index, volume.values, color=COLORS['blue'], alpha=0.7, width=0.8)
    axes[1].plot(avg_vol.index, avg_vol.values, color=COLORS['yellow'], linewidth=1.5, label="20-day avg")
    axes[1].set_ylabel("Volume", color="white")
    axes[1].set_title("Volume", color="white", fontsize=10)
    axes[1].legend(facecolor=COLORS['bg_light'], edgecolor=COLORS['gray'], labelcolor="white", fontsize=8)

    # Highlight volume surges
    surge_threshold = avg_vol * 2
    surge_mask = volume > surge_threshold
    if surge_mask.any():
        surge_dates = volume.index[surge_mask]
        for date in surge_dates:
            axes[1].axvline(x=date, color=COLORS['red'], linestyle="--", alpha=0.5)

    # 3. OBV
    axes[2].plot(obv.index, obv.values, color=COLORS['magenta'], linewidth=1.5)
    axes[2].axhline(y=0, color="white", linestyle="-", linewidth=0.5, alpha=0.3)
    axes[2].set_ylabel("OBV", color="white")
    axes[2].set_title("On-Balance Volume", color="white", fontsize=10)

    # 4. Accumulation/Distribution
    axes[3].plot(ad.index, ad.values, color=COLORS['magenta'], linewidth=1.5)
    axes[3].axhline(y=0, color="white", linestyle="-", linewidth=0.5, alpha=0.3)
    axes[3].set_ylabel("A/D", color="white")
    axes[3].set_title("Accumulation/Distribution", color="white", fontsize=10)
    axes[3].set_xlabel("Date", color="white")

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    # Save
    output_file = output_dir / f"{ticker}_liquidity_detail.png"
    save_figure(fig, output_file, dpi=150)
    plt.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Plot liquidity analysis results")
    parser.add_argument("--ticker", help="Plot detailed chart for single ticker")
    parser.add_argument("--output-dir", default="pricing/liquidity/output")

    args = parser.parse_args()
    output_dir = Path(args.output_dir)

    if args.ticker:
        plot_single_ticker(args.ticker.upper(), output_dir)
    else:
        data = load_results(output_dir)
        plot_liquidity_dashboard(data['results'], output_dir)


if __name__ == "__main__":
    main()

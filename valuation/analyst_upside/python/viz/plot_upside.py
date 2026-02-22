#!/usr/bin/env python3
"""
Visualize analyst price target scan results.

Creates one figure per scan:
- Top upside opportunities (horizontal bars by recommendation)
- Dispersion vs upside scatter (conviction map)
"""

import argparse
import sys
from pathlib import Path
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure


def load_result(filepath: Path) -> dict:
    """Load scan results from JSON."""
    with open(filepath) as f:
        return json.load(f)


def _hbar_label(ax, bar, label, max_val, fontsize=9):
    """Place label inside right of horizontal bar, or outside if bar is too short."""
    val = bar.get_width()
    cy = bar.get_y() + bar.get_height() / 2
    if abs(val) < abs(max_val) * 0.15:
        ax.text(val + abs(max_val) * 0.02, cy, label, va='center', ha='left',
                fontsize=fontsize, fontweight='bold')
    else:
        ax.text(val - abs(max_val) * 0.02, cy, label, va='center', ha='right',
                fontsize=fontsize, fontweight='bold', color=COLORS['bg'])


def _rec_color(rec: str) -> str:
    """Map recommendation to theme color."""
    mapping = {
        'strong_buy': COLORS['green'],
        'buy': COLORS['cyan'],
        'hold': COLORS['yellow'],
        'underperform': COLORS['orange'],
        'sell': COLORS['red'],
    }
    return mapping.get(rec, COLORS['gray'])


_SECTOR_COLORS = [
    COLORS['magenta'], COLORS['orange'], COLORS['red'], COLORS['purple'],
    COLORS['blue'], COLORS['fg'], COLORS['gray'], COLORS['yellow'],
]


def plot_upside(data: dict, output_file: Path):
    """Main figure: upside bars + dispersion scatter."""
    setup_dark_mode()

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    fig.subplots_adjust(wspace=0.35)

    results = data['results']
    if not results:
        print("No results to plot")
        return

    # Limit to top 15 for the bar chart
    top_n = results[:15]

    # --- Plot 1: Top Upside (left) ---
    ax = axes[0]

    tickers = [r['ticker'] for r in reversed(top_n)]
    upsides = [r['upside'] * 100 for r in reversed(top_n)]
    recs = [r.get('recommendation', 'N/A') for r in reversed(top_n)]
    bar_colors = [_rec_color(r) for r in recs]

    bars = ax.barh(tickers, upsides, color=bar_colors, alpha=0.8,
                   edgecolor=COLORS['fg'], height=0.6)

    max_val = max(upsides) if upsides else 1
    for bar, val in zip(bars, upsides):
        _hbar_label(ax, bar, f'{val:+.1f}%', max_val, fontsize=8)

    ax.axvline(0, color=COLORS['fg'], linewidth=0.5, alpha=0.5)
    ax.set_xlabel('Upside (%)')
    ax.set_title('Top Analyst Upside', fontsize=11, fontweight='bold')
    ax.grid(True, alpha=0.2, axis='x')

    # Recommendation legend — only include present ones
    present_recs = set(recs)
    rec_labels = {
        'strong_buy': 'Strong Buy', 'buy': 'Buy', 'hold': 'Hold',
        'underperform': 'Underperform', 'sell': 'Sell',
    }
    rec_handles = [
        mpatches.Patch(color=_rec_color(r), alpha=0.8, label=rec_labels.get(r, r))
        for r in rec_labels if r in present_recs
    ]
    if rec_handles:
        ax.legend(handles=rec_handles, loc='best', fontsize=7)

    # --- Plot 2: Dispersion vs Upside (right) ---
    ax = axes[1]

    valid = [r for r in results if r.get('dispersion') is not None]
    if valid:
        x = [r['upside'] * 100 for r in valid]
        y = [r['dispersion'] for r in valid]

        # Color by sector
        sectors = list(set(r.get('sector', 'N/A') for r in valid))
        sector_color_map = {s: _SECTOR_COLORS[i % len(_SECTOR_COLORS)] for i, s in enumerate(sectors)}
        colors = [sector_color_map[r.get('sector', 'N/A')] for r in valid]

        ax.scatter(x, y, c=colors, s=60, alpha=0.8, edgecolors=COLORS['fg'], linewidth=0.5)

        # Label each point
        for r, xi, yi in zip(valid, x, y):
            ax.annotate(r['ticker'], (xi, yi), textcoords='offset points',
                        xytext=(5, 5), fontsize=7, alpha=0.9)

        # Quadrant lines at medians
        med_x = np.median(x)
        med_y = np.median(y)
        ax.axvline(med_x, color=COLORS['fg'], linestyle=':', alpha=0.3, linewidth=1)
        ax.axhline(med_y, color=COLORS['fg'], linestyle=':', alpha=0.3, linewidth=1)

        # Quadrant labels
        ax.text(0.95, 0.05, 'High conviction\nhigh upside', transform=ax.transAxes,
                ha='right', va='bottom', fontsize=7, alpha=0.5, color=COLORS['green'])
        ax.text(0.05, 0.05, 'High conviction\nlow upside', transform=ax.transAxes,
                ha='left', va='bottom', fontsize=7, alpha=0.5, color=COLORS['yellow'])

        # Sector legend
        sector_handles = [
            mpatches.Patch(color=sector_color_map[s], alpha=0.8, label=s)
            for s in sectors
        ]
        ax.legend(handles=sector_handles, loc='best', fontsize=6)

    ax.set_xlabel('Upside (%)')
    ax.set_ylabel('Dispersion (analyst disagreement)')
    ax.set_title('Conviction Map', fontsize=11, fontweight='bold')
    ax.grid(True, alpha=0.2)

    scan_date = data.get('scan_date', '')[:10]
    n = data.get('results_count', len(results))
    fig.suptitle(f'Analyst Price Targets — {n} stocks ({scan_date})',
                 fontsize=14, fontweight='bold', color=COLORS['fg'], y=0.98)

    save_figure(fig, output_file, dpi=300)
    plt.close()
    print(f"Saved: {output_file}")


def print_summary(data: dict):
    """Print scan summary to console."""
    results = data['results']
    if not results:
        print("No results.")
        return

    print(f"\n{'='*60}")
    print(f"  ANALYST PRICE TARGET SCAN")
    print(f"{'='*60}")
    print(f"  Date:       {data.get('scan_date', 'N/A')[:10]}")
    print(f"  Universe:   {data.get('universe_size', '?')} stocks scanned")
    print(f"  Results:    {data.get('results_count', len(results))} passed filters")
    print(f"  Min Analysts: {data.get('min_analysts', '?')}")
    print()

    avg_upside = sum(r['upside'] for r in results) / len(results)
    print(f"  Avg Upside: {avg_upside*100:+.1f}%")
    print(f"  Top Pick:   {results[0]['ticker']} ({results[0]['upside']*100:+.1f}%)")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description='Visualize analyst upside scan')
    parser.add_argument('-i', '--input', type=str, required=True,
                        help='Input JSON result file')
    parser.add_argument('-o', '--output-dir', type=str,
                        default='valuation/analyst_upside/output',
                        help='Output directory for plots')

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = load_result(input_path)

    print_summary(data)
    plot_upside(data, output_dir / "analyst_upside.png")


if __name__ == '__main__':
    main()

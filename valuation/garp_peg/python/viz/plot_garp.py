#!/usr/bin/env python3
"""
Visualization for GARP/PEG analysis results.
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, save_figure, KANAGAWA_DRAGON as COLORS

setup_dark_mode()


def load_result(filepath):
    """Load GARP result from JSON file."""
    with open(filepath) as f:
        return json.load(f)


def load_comparison(filepath):
    """Load comparison results from JSON file."""
    with open(filepath) as f:
        return json.load(f)


def plot_single_result(result, output_dir):
    """Plot dashboard for single ticker GARP analysis."""
    ticker = result['ticker']

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'GARP Analysis: {ticker}', fontsize=16, fontweight='bold')

    # 1. Score breakdown (top left)
    ax1 = axes[0, 0]
    score = result['garp_score']
    categories = ['PEG\n(0-30)', 'Growth\n(0-25)', 'Quality\n(0-20)',
                  'Balance\nSheet\n(0-15)', 'ROE\n(0-10)']
    scores = [score['peg_score'], score['growth_score'], score['quality_score'],
              score['balance_sheet_score'], score['roe_score']]
    max_scores = [30, 25, 20, 15, 10]

    x = np.arange(len(categories))
    width = 0.6

    # Colors based on percentage of max
    colors = []
    for s, m in zip(scores, max_scores):
        pct = s / m
        if pct >= 0.7:
            colors.append(COLORS['green'])
        elif pct >= 0.4:
            colors.append(COLORS['yellow'])
        else:
            colors.append(COLORS['red'])

    bars = ax1.bar(x, scores, width, color=colors, edgecolor=COLORS['fg'], linewidth=0.5)
    ax1.bar(x, [m - s for s, m in zip(scores, max_scores)], width,
            bottom=scores, color=COLORS['gray'], alpha=0.3, edgecolor=COLORS['fg'], linewidth=0.5)

    ax1.set_ylabel('Score')
    ax1.set_title(f'GARP Score Breakdown: {score["total_score"]:.0f}/100 (Grade: {score["grade"]})')
    ax1.set_xticks(x)
    ax1.set_xticklabels(categories)
    ax1.set_ylim(0, 35)

    # Add score labels on bars
    for bar, s in zip(bars, scores):
        height = bar.get_height()
        ax1.annotate(f'{s:.0f}',
                     xy=(bar.get_x() + bar.get_width() / 2, height),
                     xytext=(0, 3),
                     textcoords="offset points",
                     ha='center', va='bottom', fontsize=10, fontweight='bold')

    # 2. PEG gauge (top right)
    ax2 = axes[0, 1]
    peg_metrics = result['peg_metrics']
    peg = peg_metrics['peg_forward'] if peg_metrics['peg_forward'] > 0 else peg_metrics['peg_trailing']

    # Create gauge-like visualization
    if peg > 0:
        # Define zones
        zones = [
            (0, 0.5, COLORS['green'], 'Very\nUndervalued'),
            (0.5, 1.0, COLORS['cyan'], 'Undervalued'),
            (1.0, 1.5, COLORS['yellow'], 'Fair'),
            (1.5, 2.0, COLORS['orange'], 'Expensive'),
            (2.0, 3.0, COLORS['red'], 'Very\nExpensive'),
        ]

        for start, end, color, label in zones:
            ax2.barh(0, end - start, left=start, height=0.3, color=color, alpha=0.7)

        # Mark current PEG
        peg_clamped = min(peg, 3.0)
        ax2.axvline(x=peg_clamped, color=COLORS['fg'], linewidth=3, linestyle='-')
        ax2.plot(peg_clamped, 0, 'o', color=COLORS['fg'], markersize=15)

        ax2.set_xlim(0, 3)
        ax2.set_ylim(-0.5, 0.5)
        ax2.set_xlabel('PEG Ratio')
        ax2.set_title(f'PEG: {peg:.2f} ({peg_metrics["peg_assessment"]})')
        ax2.set_yticks([])

        # Add zone labels
        for start, end, color, label in zones:
            mid = (start + end) / 2
            ax2.text(mid, -0.35, label, ha='center', va='top', fontsize=8)
    else:
        ax2.text(0.5, 0.5, 'PEG not available\n(negative earnings or no growth)',
                 ha='center', va='center', fontsize=12, transform=ax2.transAxes)
        ax2.set_title('PEG Ratio')

    # 3. Quality metrics (bottom left)
    ax3 = axes[1, 0]
    quality = result['quality_metrics']

    metrics = ['FCF Conv.', 'D/E Ratio', 'ROE', 'ROA']
    values = [quality['fcf_conversion'] * 100,
              quality['debt_to_equity'] * 100,
              quality['roe'] * 100,
              quality['roa'] * 100]

    # Determine colors based on quality
    q_colors = []
    # FCF Conversion (higher is better)
    q_colors.append(COLORS['green'] if values[0] > 80 else COLORS['yellow'] if values[0] > 50 else COLORS['red'])
    # D/E Ratio (lower is better, now in %)
    q_colors.append(COLORS['green'] if values[1] < 50 else COLORS['yellow'] if values[1] < 100 else COLORS['red'])
    # ROE (higher is better)
    q_colors.append(COLORS['green'] if values[2] > 15 else COLORS['yellow'] if values[2] > 10 else COLORS['red'])
    # ROA (higher is better)
    q_colors.append(COLORS['green'] if values[3] > 10 else COLORS['yellow'] if values[3] > 5 else COLORS['red'])

    x = np.arange(len(metrics))
    bars = ax3.bar(x, [abs(v) for v in values], color=q_colors, edgecolor=COLORS['fg'], linewidth=0.5)

    ax3.set_ylabel('Value')
    ax3.set_title(f'Quality: {quality["earnings_quality"]} | Balance Sheet: {quality["balance_sheet_strength"]}')
    ax3.set_xticks(x)
    ax3.set_xticklabels(metrics)

    # Add value labels
    for bar, v in zip(bars, values):
        height = bar.get_height()
        label = f'{v:.1f}%' if bar.get_x() != 1 else f'{v:.2f}'
        ax3.annotate(label,
                     xy=(bar.get_x() + bar.get_width() / 2, height),
                     xytext=(0, 3),
                     textcoords="offset points",
                     ha='center', va='bottom', fontsize=10)

    # 4. Valuation summary (bottom right)
    ax4 = axes[1, 1]
    ax4.axis('off')

    # Build summary text
    summary_lines = [
        f"Ticker: {ticker}",
        f"Price: ${result['price']:.2f}",
        "",
        f"P/E (Trailing): {peg_metrics['pe_trailing']:.1f}x",
        f"P/E (Forward): {peg_metrics['pe_forward']:.1f}x",
        f"Growth Rate: {peg_metrics['growth_rate_used']:.1f}%",
        f"Source: {peg_metrics['growth_source']}",
        "",
        f"PEG (Forward): {peg_metrics['peg_forward']:.2f}",
        f"PEGY: {peg_metrics['pegy']:.2f}",
        "",
    ]

    if result['implied_fair_pe']:
        summary_lines.append(f"Implied Fair P/E: {result['implied_fair_pe']:.1f}x")
    if result['implied_fair_price']:
        summary_lines.append(f"Implied Fair Price: ${result['implied_fair_price']:.2f}")
    if result['upside_downside_pct']:
        ud = result['upside_downside_pct']
        direction = "Upside" if ud >= 0 else "Downside"
        summary_lines.append(f"{direction}: {abs(ud):.1f}%")

    summary_lines.extend([
        "",
        f"Signal: {result['signal']}",
    ])

    summary_text = '\n'.join(summary_lines)

    # Signal color
    signal_colors = {
        'Strong Buy': COLORS['green'],
        'Buy': COLORS['cyan'],
        'Hold': COLORS['yellow'],
        'Caution': COLORS['orange'],
        'Avoid': COLORS['red'],
        'N/A': COLORS['gray'],
    }
    signal_color = signal_colors.get(result['signal'], COLORS['gray'])

    ax4.text(0.1, 0.95, summary_text, transform=ax4.transAxes,
             fontsize=11, verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor=COLORS['bg_light'], edgecolor=COLORS['gray']))

    # Add signal badge
    ax4.add_patch(mpatches.FancyBboxPatch(
        (0.5, 0.05), 0.45, 0.15, transform=ax4.transAxes,
        boxstyle="round,pad=0.02", facecolor=signal_color, edgecolor=COLORS['fg'], linewidth=2
    ))
    ax4.text(0.725, 0.125, result['signal'], transform=ax4.transAxes,
             ha='center', va='center', fontsize=14, fontweight='bold', color=COLORS['bg'])

    plt.tight_layout()
    plt.subplots_adjust(top=0.92)

    output_file = Path(output_dir) / f'{ticker}_garp_analysis.png'
    save_figure(fig, output_file, dpi=150)
    plt.close()


def plot_comparison(comparison, output_dir):
    """Plot comparison chart for multiple tickers."""
    results = comparison['results']
    if not results:
        print("No results to compare")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('GARP Comparison', fontsize=16, fontweight='bold')

    tickers = [r['ticker'] for r in results]
    scores = [r['total_score'] for r in results]
    pegs = [r['peg_forward'] if r['peg_forward'] > 0 else r['peg_trailing'] for r in results]
    signals = [r['signal'] for r in results]

    # Signal colors
    signal_colors = {
        'Strong Buy': COLORS['green'],
        'Buy': COLORS['cyan'],
        'Hold': COLORS['yellow'],
        'Caution': COLORS['orange'],
        'Avoid': COLORS['red'],
        'N/A': COLORS['gray'],
    }
    colors = [signal_colors.get(s, COLORS['gray']) for s in signals]

    # 1. Score comparison (left)
    ax1 = axes[0]
    x = np.arange(len(tickers))
    bars = ax1.bar(x, scores, color=colors, edgecolor=COLORS['fg'], linewidth=0.5)

    ax1.set_ylabel('GARP Score')
    ax1.set_title('GARP Score by Ticker')
    ax1.set_xticks(x)
    ax1.set_xticklabels(tickers, rotation=90, ha='center')
    ax1.set_ylim(0, 100)
    ax1.axhline(y=60, color='green', linestyle='--', alpha=0.5, label='Good (60+)')
    ax1.axhline(y=40, color='orange', linestyle='--', alpha=0.5, label='Fair (40+)')

    # Add score labels
    for bar, s, g in zip(bars, scores, [r['grade'] for r in results]):
        height = bar.get_height()
        ax1.annotate(f'{s:.0f}\n({g})',
                     xy=(bar.get_x() + bar.get_width() / 2, height),
                     xytext=(0, 3),
                     textcoords="offset points",
                     ha='center', va='bottom', fontsize=10)

    ax1.legend(loc='upper right')

    # 2. PEG comparison (right)
    ax2 = axes[1]

    # Filter out zero PEGs
    valid_data = [(t, p, c) for t, p, c in zip(tickers, pegs, colors) if p > 0]
    if valid_data:
        v_tickers, v_pegs, v_colors = zip(*valid_data)
        x = np.arange(len(v_tickers))
        bars = ax2.bar(x, v_pegs, color=v_colors, edgecolor=COLORS['fg'], linewidth=0.5)

        ax2.set_ylabel('PEG Ratio')
        ax2.set_title('PEG Ratio by Ticker (lower is better)')
        ax2.set_xticks(x)
        ax2.set_xticklabels(v_tickers, rotation=90, ha='center')
        ax2.axhline(y=1.0, color='green', linestyle='--', alpha=0.5, label='Fair Value (1.0)')
        ax2.axhline(y=2.0, color='red', linestyle='--', alpha=0.5, label='Expensive (2.0)')

        # Add PEG labels
        for bar, p in zip(bars, v_pegs):
            height = bar.get_height()
            ax2.annotate(f'{p:.2f}',
                         xy=(bar.get_x() + bar.get_width() / 2, height),
                         xytext=(0, 3),
                         textcoords="offset points",
                         ha='center', va='bottom', fontsize=10)

        ax2.legend(loc='upper right')
    else:
        ax2.text(0.5, 0.5, 'No valid PEG data', ha='center', va='center',
                 fontsize=12, transform=ax2.transAxes)

    plt.tight_layout()
    plt.subplots_adjust(top=0.90)

    output_file = Path(output_dir) / 'garp_comparison.png'
    save_figure(fig, output_file, dpi=150)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Plot GARP analysis results")
    parser.add_argument("--result", help="Path to single result JSON file")
    parser.add_argument("--comparison", help="Path to comparison JSON file")
    parser.add_argument("--output", default="valuation/garp_peg/output", help="Output directory for plots")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.result:
        result = load_result(args.result)
        plot_single_result(result, output_dir)

    if args.comparison:
        comparison = load_comparison(args.comparison)
        plot_comparison(comparison, output_dir)

    if not args.result and not args.comparison:
        # Try to find results in output directory
        result_files = list(Path(args.output).glob('garp_result_*.json'))
        for rf in result_files:
            result = load_result(rf)
            plot_single_result(result, output_dir)

        comp_file = Path(args.output) / 'garp_comparison.json'
        if comp_file.exists():
            comparison = load_comparison(comp_file)
            plot_comparison(comparison, output_dir)


if __name__ == "__main__":
    main()

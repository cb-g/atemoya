#!/usr/bin/env python3
"""
Growth Analysis Visualization

Creates a 2x2 dashboard showing:
1. Growth metrics radar chart
2. Rule of 40 gauge
3. Margin trajectory
4. Score breakdown
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

setup_dark_mode()


def load_result(path: str) -> dict:
    """Load growth result JSON file."""
    with open(path) as f:
        return json.load(f)


def draw_growth_radar(ax, metrics: dict, valuation: dict):
    """Draw growth metrics as a radar/spider chart."""
    ax.set_title('Growth Profile', fontsize=11, fontweight='bold')

    categories = ['Revenue\nGrowth', 'Earnings\nGrowth', 'Gross\nMargin', 'Op.\nMargin', 'FCF\nMargin']

    # Normalize values to 0-100 scale
    values = [
        min(metrics.get('revenue_growth_pct', 0), 100),  # Cap at 100%
        min(metrics.get('earnings_growth_pct', 0) if metrics.get('earnings_growth_pct', 0) > 0 else 0, 100),
        metrics.get('gross_margin_pct', 0) if 'gross_margin_pct' in (valuation.get('margin_analysis') or metrics) else 0,
        metrics.get('operating_margin_pct', 0) if 'operating_margin_pct' in (valuation.get('margin_analysis') or metrics) else 0,
        metrics.get('fcf_margin_pct', 0) if 'fcf_margin_pct' in (valuation.get('margin_analysis') or metrics) else 0,
    ]

    # Get margin values from margin_analysis if available
    if 'margin_analysis' in valuation:
        ma = valuation['margin_analysis']
        values[2] = ma.get('gross_margin_pct', values[2])
        values[3] = ma.get('operating_margin_pct', values[3])
        values[4] = ma.get('fcf_margin_pct', values[4])

    # Clamp all values to 0 (negatives cause polygon to cross origin)
    values = [max(0, v) for v in values]

    # Number of variables
    N = len(categories)
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]  # Complete the loop
    values += values[:1]

    # Draw radar
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, size=8)

    ax.plot(angles, values, 'o-', linewidth=2, color=COLORS['cyan'])
    ax.fill(angles, values, alpha=0.25, color=COLORS['cyan'])

    # Set radial limits
    ax.set_ylim(0, 100)


def draw_rule_of_40(ax, metrics: dict):
    """Draw Rule of 40 gauge."""
    ax.set_title('Rule of 40 Analysis', fontsize=11, fontweight='bold')
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.set_aspect('equal')
    ax.axis('off')

    rule_of_40 = metrics.get('rule_of_40', 0)
    tier = metrics.get('rule_of_40_tier', 'Unknown')

    # Color based on Rule of 40 score
    if rule_of_40 >= 40:
        color = COLORS['green']
        assessment = 'EXCELLENT'
    elif rule_of_40 >= 30:
        color = COLORS['blue']
        assessment = 'GOOD'
    elif rule_of_40 >= 20:
        color = COLORS['yellow']
        assessment = 'FAIR'
    else:
        color = COLORS['red']
        assessment = 'POOR'

    # Draw gauge arc
    theta1, theta2 = 0, 180
    arc = mpatches.Arc((5, 2), 6, 6, angle=0, theta1=theta1, theta2=theta2,
                        linewidth=20, color=COLORS['gray'])
    ax.add_patch(arc)

    # Fill based on score (0-80 range mapped to 0-180 degrees)
    fill_angle = min(rule_of_40, 80) / 80 * 180
    arc_fill = mpatches.Arc((5, 2), 6, 6, angle=0, theta1=0, theta2=fill_angle,
                             linewidth=20, color=color)
    ax.add_patch(arc_fill)

    # Score in center
    ax.text(5, 2.5, f'{rule_of_40:.0f}', ha='center', va='center',
            fontsize=28, fontweight='bold', color=color)
    ax.text(5, 1.5, assessment, ha='center', va='center',
            fontsize=12, fontweight='bold', color='gray')

    # Threshold line at 40
    ax.text(5, 5.5, 'Revenue Growth + FCF Margin', ha='center', fontsize=9, color='gray')

    # Breakdown
    rev_growth = metrics.get('revenue_growth_pct', 0)
    fcf_margin = metrics.get('fcf_margin_pct', 0) if 'fcf_margin_pct' in metrics else 0
    ax.text(2, 0.5, f'Rev Growth: {rev_growth:.1f}%', ha='center', fontsize=9)
    ax.text(8, 0.5, f'FCF Margin: {fcf_margin:.1f}%', ha='center', fontsize=9)


def draw_margin_trajectory(ax, margin_analysis: dict):
    """Draw margin trajectory visualization."""
    ax.set_title('Margin Analysis', fontsize=11, fontweight='bold')

    margins = ['Gross', 'Operating', 'FCF']
    values = [
        margin_analysis.get('gross_margin_pct', 0),
        margin_analysis.get('operating_margin_pct', 0),
        margin_analysis.get('fcf_margin_pct', 0)
    ]

    colors = [COLORS['blue'], COLORS['green'], COLORS['magenta']]
    bars = ax.bar(margins, values, color=colors, alpha=0.7, edgecolor=COLORS['gray'])

    # Value labels
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f'{val:.1f}%', ha='center', fontsize=10, fontweight='bold')

    ax.set_ylabel('Margin (%)')
    ax.set_ylim(0, max(values) * 1.3 if values else 100)

    # Trajectory badge
    trajectory = margin_analysis.get('margin_trajectory', 'Unknown')
    traj_color = COLORS['green'] if trajectory == 'Expanding' else COLORS['yellow'] if trajectory == 'Stable' else COLORS['red']
    ax.text(0.98, 0.98, f'Trajectory:\n{trajectory}',
            transform=ax.transAxes, ha='right', va='top', fontsize=9, fontweight='bold',
            bbox=dict(boxstyle='round', facecolor=traj_color, alpha=0.3))

    # Operating leverage
    op_lev = margin_analysis.get('operating_leverage', 0)
    if op_lev > 0:
        ax.text(0.02, 0.98, f'Op. Leverage: {op_lev:.2f}x',
                transform=ax.transAxes, ha='left', va='top', fontsize=9,
                bbox=dict(boxstyle='round', facecolor=COLORS['yellow'], alpha=0.3))


def draw_score_breakdown(ax, score: dict, signal: str, valuation: dict):
    """Draw score breakdown as horizontal bars."""
    ax.set_title(f'Growth Score: {score["total_score"]:.0f}/100 ({score["grade"]})',
                 fontsize=11, fontweight='bold')

    components = ['Revenue Growth', 'Earnings Growth', 'Margin', 'Efficiency', 'Quality']
    max_scores = [25, 25, 20, 15, 15]
    actual_scores = [
        score.get('revenue_growth_score', 0),
        score.get('earnings_growth_score', 0),
        score.get('margin_score', 0),
        score.get('efficiency_score', 0),
        score.get('quality_score', 0)
    ]

    y_pos = np.arange(len(components))

    # Background bars
    ax.barh(y_pos, max_scores, color=COLORS['bg_light'], edgecolor=COLORS['gray'], alpha=0.5)
    # Actual scores
    colors = [COLORS['green'] if a >= m*0.7 else COLORS['yellow'] if a >= m*0.4 else COLORS['red']
              for a, m in zip(actual_scores, max_scores)]
    bars = ax.barh(y_pos, actual_scores, color=colors, edgecolor=COLORS['gray'], alpha=0.8)

    # Score labels
    for i, (actual, maximum) in enumerate(zip(actual_scores, max_scores)):
        ax.text(maximum + 0.5, i, f'{actual:.0f}/{maximum}', va='center', fontsize=9)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(components)
    ax.set_xlim(0, 30)
    ax.set_xlabel('Score')

    # Signal badge
    signal_color = COLORS['green'] if 'Strong' in signal else COLORS['blue'] if 'Growth' in signal else COLORS['yellow']
    ax.text(0.98, 0.02, signal, transform=ax.transAxes, ha='right', va='bottom',
            fontsize=10, fontweight='bold',
            bbox=dict(boxstyle='round', facecolor=signal_color, alpha=0.3))


def plot_growth(data: dict, output_path: str):
    """Create the full growth analysis visualization."""
    fig = plt.figure(figsize=(12, 10))
    ticker = data['ticker']
    company = data.get('company_name', ticker)
    fig.suptitle(f'Growth Analysis - {ticker} ({company})', fontsize=14, fontweight='bold')

    # Create grid: radar chart needs polar projection
    ax1 = fig.add_subplot(2, 2, 1, projection='polar')  # Radar
    ax2 = fig.add_subplot(2, 2, 2)  # Rule of 40
    ax3 = fig.add_subplot(2, 2, 3)  # Margins
    ax4 = fig.add_subplot(2, 2, 4)  # Score

    # 1. Growth radar (top-left)
    draw_growth_radar(ax1, data['growth_metrics'], data)

    # 2. Rule of 40 (top-right)
    draw_rule_of_40(ax2, data['growth_metrics'])

    # 3. Margin trajectory (bottom-left)
    draw_margin_trajectory(ax3, data['margin_analysis'])

    # 4. Score breakdown (bottom-right)
    draw_score_breakdown(ax4, data['score'], data['signal'], data['valuation'])

    plt.tight_layout()
    save_figure(fig, output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def plot_comparison(comparison: dict, output_path: str):
    """Plot comparison chart for multiple tickers."""
    results = comparison['results']
    if not results:
        print("No results to compare")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('Growth Stock Comparison', fontsize=16, fontweight='bold')

    tickers = [r['ticker'] for r in results]
    scores = [r['score'] for r in results]
    rule40s = [r['rule_of_40'] for r in results]
    signals = [r['signal'] for r in results]

    # Signal colors
    signal_colors = {
        'Strong Growth': COLORS['green'],
        'Growth Buy': COLORS['cyan'],
        'Growth Hold': COLORS['yellow'],
        'Growth Caution': COLORS['orange'],
        'Not a Growth Stock': COLORS['red'],
    }
    colors = [signal_colors.get(s, COLORS['gray']) for s in signals]

    # 1. Growth Score comparison (left)
    ax1 = axes[0]
    x = np.arange(len(tickers))
    bars = ax1.bar(x, scores, color=colors, edgecolor=COLORS['fg'], linewidth=0.5)

    ax1.set_ylabel('Growth Score')
    ax1.set_title('Growth Score by Ticker')
    ax1.set_xticks(x)
    ax1.set_xticklabels(tickers, rotation=90, ha='center')
    ax1.set_ylim(0, 100)
    ax1.axhline(y=60, color='green', linestyle='--', alpha=0.5, label='Strong (60+)')
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

    # 2. Rule of 40 comparison (right)
    ax2 = axes[1]
    x = np.arange(len(tickers))
    bars = ax2.bar(x, rule40s, color=colors, edgecolor=COLORS['fg'], linewidth=0.5)

    ax2.set_ylabel('Rule of 40')
    ax2.set_title('Rule of 40 by Ticker (higher is better)')
    ax2.set_xticks(x)
    ax2.set_xticklabels(tickers, rotation=90, ha='center')
    ax2.axhline(y=40, color='green', linestyle='--', alpha=0.5, label='Excellent (40+)')
    ax2.axhline(y=20, color='orange', linestyle='--', alpha=0.5, label='Fair (20+)')

    # Add value labels
    for bar, v in zip(bars, rule40s):
        height = bar.get_height()
        ax2.annotate(f'{v:.0f}',
                     xy=(bar.get_x() + bar.get_width() / 2, max(height, 0)),
                     xytext=(0, 3),
                     textcoords="offset points",
                     ha='center', va='bottom', fontsize=10)

    ax2.legend(loc='upper right')

    plt.tight_layout()
    plt.subplots_adjust(top=0.90)

    save_figure(fig, output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Plot growth analysis')
    parser.add_argument('--input', help='Input growth result JSON file (single ticker)')
    parser.add_argument('--comparison', help='Input growth comparison JSON file (multi-ticker)')
    parser.add_argument('--output', help='Output PNG path')
    args = parser.parse_args()

    if not args.input and not args.comparison:
        parser.error("Either --input or --comparison is required")

    # Plot comparison if provided
    if args.comparison:
        comparison = load_result(args.comparison)
        if args.output:
            output_path = args.output
        else:
            output_dir = Path(__file__).resolve().parent.parent.parent / "output" / "plots"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / 'growth_comparison.png')
        plot_comparison(comparison, output_path)

    # Plot single ticker if provided
    if args.input:
        data = load_result(args.input)
        ticker = data['ticker']

        if args.output and not args.comparison:
            output_path = args.output
        else:
            output_dir = Path(__file__).resolve().parent.parent.parent / "output" / "plots"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f'{ticker}_growth_analysis.png')

        plot_growth(data, output_path)

    return 0


if __name__ == '__main__':
    sys.exit(main())

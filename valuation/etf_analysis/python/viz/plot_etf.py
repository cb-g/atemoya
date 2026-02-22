#!/usr/bin/env python3
"""
ETF Analysis Visualization

Creates a 2x2 dashboard showing:
1. Quality score breakdown
2. Key metrics summary
3. Premium/discount gauge
4. Derivatives-specific analysis (if applicable)
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


def load_result(path: str) -> dict:
    """Load ETF analysis result JSON file."""
    with open(path) as f:
        return json.load(f)


def _bar_label(ax, bar, val, fmt="{:.0f}", threshold=0.15):
    """Place label inside top of tall bars, above short bars."""
    max_h = max(b.get_height() for b in ax.patches) if ax.patches else 1
    if bar.get_height() > max_h * threshold:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() - max_h * 0.04,
                fmt.format(val), ha='center', va='top', fontsize=9,
                color=COLORS['fg'])
    else:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max_h * 0.02,
                fmt.format(val), ha='center', va='bottom', fontsize=9,
                color=COLORS['fg'])


def draw_quality_score(ax, score: dict, signal: str):
    """Draw quality score breakdown as horizontal bars."""
    ax.set_title(f'ETF Quality Score: {score["total_score"]:.0f}/100 ({score["grade"]})',
                 fontsize=11, fontweight='bold')

    components = ['Cost', 'Tracking', 'Liquidity', 'Size']
    max_scores = [30, 30, 25, 15]
    actual_scores = [
        score.get('cost_score', 0),
        score.get('tracking_score', 0),
        score.get('liquidity_score', 0),
        score.get('size_score', 0)
    ]

    y_pos = np.arange(len(components))

    # Background bars
    ax.barh(y_pos, max_scores, color=COLORS['bg_light'], edgecolor=COLORS['gray'],
            alpha=0.5, height=0.7)
    # Actual scores
    bar_colors = [
        COLORS['green'] if a >= m * 0.7
        else COLORS['yellow'] if a >= m * 0.4
        else COLORS['red']
        for a, m in zip(actual_scores, max_scores)
    ]
    ax.barh(y_pos, actual_scores, color=bar_colors, edgecolor=COLORS['gray'],
            alpha=0.85, height=0.7)

    # Score labels
    for i, (actual, maximum) in enumerate(zip(actual_scores, max_scores)):
        ax.text(maximum + 0.5, i, f'{actual:.0f}/{maximum}', va='center', fontsize=9,
                color=COLORS['fg'])

    ax.set_yticks(y_pos)
    ax.set_yticklabels(components)
    ax.set_xlim(0, 35)
    ax.set_xlabel('Score')

    # Signal badge
    signal_colors = {
        'High Quality': COLORS['green'],
        'Good Quality': COLORS['blue'],
        'Acceptable': COLORS['yellow'],
        'Use Caution': COLORS['magenta'],
        'Avoid': COLORS['red'],
    }
    sig_color = signal_colors.get(signal, COLORS['gray'])
    ax.text(0.98, 0.02, signal, transform=ax.transAxes, ha='right', va='bottom',
            fontsize=10, fontweight='bold',
            bbox=dict(boxstyle='round', facecolor=sig_color, alpha=0.3,
                      edgecolor=COLORS['gray']))


def draw_key_metrics(ax, data: dict):
    """Draw key metrics as a formatted table."""
    ax.set_title('Key Metrics', fontsize=11, fontweight='bold')
    ax.axis('off')

    er_pct = data.get('expense_ratio_pct', 0)
    spread_pct = data.get('bid_ask_spread_pct', 0)
    dist_yield = data.get('distribution_yield_pct', 0)
    aum = data.get('aum', 0)
    liquidity = data.get('liquidity_tier', 'N/A')
    cost_tier = data.get('cost_tier', 'N/A')

    tracking = data.get('tracking')
    te_pct = tracking.get('tracking_error_pct', 0) if tracking else 0
    td_pct = tracking.get('tracking_difference_pct', 0) if tracking else 0

    if aum >= 1e9:
        aum_str = f'${aum / 1e9:.1f}B'
    elif aum >= 1e6:
        aum_str = f'${aum / 1e6:.0f}M'
    else:
        aum_str = 'N/A'

    rows = [
        ['Expense Ratio', f'{er_pct:.2f}%' if er_pct > 0 else 'N/A'],
        ['Bid-Ask Spread', f'{spread_pct:.3f}%'],
        ['Distribution Yield', f'{dist_yield:.2f}%' if dist_yield > 0 else 'N/A'],
        ['Tracking Error', f'{te_pct:.2f}%' if te_pct > 0 else 'N/A'],
        ['Tracking Diff', f'{td_pct:+.2f}%' if tracking else 'N/A'],
        ['AUM', aum_str],
        ['Cost Tier', cost_tier],
        ['Liquidity', liquidity],
    ]

    table = ax.table(cellText=rows, loc='center', cellLoc='left',
                     colWidths=[0.55, 0.45])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.5)

    for i in range(len(rows)):
        table[(i, 0)].set_facecolor(COLORS['bg_light'])
        table[(i, 0)].set_text_props(fontweight='bold', color=COLORS['fg'])
        table[(i, 0)].set_edgecolor(COLORS['gray'])
        table[(i, 1)].set_facecolor(COLORS['bg'])
        table[(i, 1)].set_text_props(color=COLORS['fg'])
        table[(i, 1)].set_edgecolor(COLORS['gray'])


def draw_premium_discount(ax, premium_pct: float):
    """Draw premium/discount gauge."""
    ax.set_title('Premium/Discount to NAV', fontsize=11, fontweight='bold')
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_aspect('equal')
    ax.axis('off')

    # Determine color
    if abs(premium_pct) < 0.1:
        color = COLORS['green']
        status = 'AT NAV'
    elif premium_pct > 0:
        color = COLORS['red'] if premium_pct > 1 else COLORS['yellow']
        status = 'PREMIUM'
    else:
        color = COLORS['blue'] if premium_pct > -1 else COLORS['green']
        status = 'DISCOUNT'

    # Draw gauge
    circle = plt.Circle((5, 6), 2.0, color=color, alpha=0.3)
    ax.add_patch(circle)
    circle_border = plt.Circle((5, 6), 2.0, fill=False, color=color, linewidth=3)
    ax.add_patch(circle_border)

    # Value in center
    ax.text(5, 6.3, f'{premium_pct:+.2f}%', ha='center', va='center',
            fontsize=18, fontweight='bold', color=color)
    ax.text(5, 5.0, status, ha='center', va='center',
            fontsize=12, color=COLORS['gray'])

    # Scale at bottom
    ax.plot([1, 9], [2, 2], color=COLORS['bg_light'], linewidth=10, solid_capstyle='round')

    # Mark position on scale (-2% to +2% range)
    scale_pos = 5 + premium_pct * 2
    scale_pos = max(1, min(9, scale_pos))
    ax.scatter([scale_pos], [2], s=100, c=color, zorder=5)

    ax.text(1, 1.2, '-2%', ha='center', fontsize=8, color=COLORS['gray'])
    ax.text(5, 1.2, '0%', ha='center', fontsize=8, color=COLORS['gray'])
    ax.text(9, 1.2, '+2%', ha='center', fontsize=8, color=COLORS['gray'])


def draw_derivatives_analysis(ax, deriv_type: str, deriv_analysis: dict):
    """Draw derivatives-specific analysis if applicable."""
    ax.axis('off')

    if not deriv_analysis or deriv_type == 'Standard':
        ax.set_title('ETF Summary', fontsize=11, fontweight='bold')
        ax.text(0.5, 0.5, 'Standard ETF\nNo derivatives overlay',
                ha='center', va='center', transform=ax.transAxes,
                fontsize=12, color=COLORS['gray'])
        return

    ax.set_title(f'{deriv_type} ETF Analysis', fontsize=11, fontweight='bold')

    rows = []
    da_type = deriv_analysis.get('type', '')

    if da_type == 'covered_call' or 'Covered Call' in deriv_type:
        rows = [
            ['Distribution Yield', f"{deriv_analysis.get('distribution_yield_pct', 0):.2f}%"],
            ['Upside Capture', f"{deriv_analysis.get('upside_capture', 0):.1f}%"],
            ['Downside Capture', f"{deriv_analysis.get('downside_capture', 0):.1f}%"],
            ['Yield vs Benchmark', f"{deriv_analysis.get('yield_vs_benchmark', 0):.1f}x"],
            ['Capture Efficiency', f"{deriv_analysis.get('capture_efficiency', 0):+.1f}%"],
        ]

    elif da_type == 'buffer' or 'Buffer' in deriv_type:
        rows = [
            ['Buffer Level', f"{deriv_analysis.get('buffer_level', 0):.0f}%"],
            ['Cap Level', f"{deriv_analysis.get('cap_level', 0):.0f}%"],
            ['Remaining Buffer', f"{deriv_analysis.get('remaining_buffer', 0):.1f}%"],
            ['Days to Outcome', str(deriv_analysis.get('days_to_outcome', 'N/A'))],
            ['Status', deriv_analysis.get('buffer_status', 'N/A')],
        ]

    elif da_type == 'volatility' or 'Volatility' in deriv_type:
        rows = [
            ['Term Structure', deriv_analysis.get('term_structure', 'N/A')],
            ['Roll Yield (Monthly)', f"{deriv_analysis.get('roll_yield_monthly_pct', 0):.2f}%"],
            ['Roll Yield (Annual)', f"{deriv_analysis.get('roll_yield_annual_pct', 0):.1f}%"],
            ['Decay Warning', 'Yes' if deriv_analysis.get('decay_warning') else 'No'],
        ]

    if rows:
        table = ax.table(cellText=rows, loc='center', cellLoc='left',
                         colWidths=[0.55, 0.45])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.8)

        for i in range(len(rows)):
            table[(i, 0)].set_facecolor(COLORS['bg_light'])
            table[(i, 0)].set_text_props(fontweight='bold', color=COLORS['fg'])
            table[(i, 0)].set_edgecolor(COLORS['gray'])
            table[(i, 1)].set_facecolor(COLORS['bg'])
            table[(i, 1)].set_text_props(color=COLORS['fg'])
            table[(i, 1)].set_edgecolor(COLORS['gray'])


def plot_etf(data: dict, output_path: str):
    """Create the full ETF analysis visualization."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    ticker = data.get('ticker', 'Unknown')
    name = data.get('name', ticker)
    signal = data.get('signal', 'Acceptable')

    fig.suptitle(f'ETF Analysis \u2014 {ticker} ({name})', fontsize=14, fontweight='bold')

    # 1. Quality score (top-left)
    draw_quality_score(axes[0, 0], data.get('score', {}), signal)

    # 2. Key metrics (top-right)
    draw_key_metrics(axes[0, 1], data)

    # 3. Premium/discount (bottom-left)
    draw_premium_discount(axes[1, 0], data.get('premium_discount_pct', 0))

    # 4. Derivatives analysis (bottom-right)
    draw_derivatives_analysis(axes[1, 1],
                              data.get('derivatives_type', 'Standard'),
                              data.get('derivatives_analysis'))

    plt.tight_layout()
    save_figure(fig, output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Plot ETF analysis')
    parser.add_argument('--input', required=True, help='Input ETF result JSON file')
    parser.add_argument('--output', help='Output path')
    args = parser.parse_args()

    data = load_result(args.input)
    ticker = data.get('ticker', 'UNKNOWN')

    if args.output:
        output_path = args.output
    else:
        output_dir = Path(__file__).resolve().parent.parent.parent / "output" / "plots"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f'{ticker}_etf_analysis.svg')

    plot_etf(data, output_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())

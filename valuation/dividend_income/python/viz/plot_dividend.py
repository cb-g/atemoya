#!/usr/bin/env python3
"""
Dividend Income Analysis Visualization

Creates a 2x2 dashboard showing:
1. Safety score breakdown (horizontal bars)
2. Yield comparison with tiers
3. Dividend growth trajectory
4. DDM valuation comparison
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
    """Load dividend result JSON file."""
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


def draw_safety_score(ax, safety: dict, ticker: str):
    """Draw safety score breakdown as horizontal bars."""
    ax.set_title(f'Dividend Safety: {safety["total_score"]:.0f}/100 ({safety["grade"]})',
                 fontsize=11, fontweight='bold')

    components = ['Payout', 'Coverage', 'Streak', 'Balance Sheet', 'Stability']
    max_scores = [25, 25, 25, 15, 10]
    actual_scores = [
        safety['payout_score'],
        safety['coverage_score'],
        safety['streak_score'],
        safety['balance_sheet_score'],
        safety['stability_score']
    ]

    y_pos = np.arange(len(components))

    # Background bars (max possible)
    ax.barh(y_pos, max_scores, color=COLORS['bg_light'], edgecolor=COLORS['gray'],
            alpha=0.5, height=0.7)

    # Actual scores — green/yellow/red from theme
    bar_colors = [
        COLORS['green'] if a >= m * 0.7
        else COLORS['yellow'] if a >= m * 0.4
        else COLORS['red']
        for a, m in zip(actual_scores, max_scores)
    ]
    bars = ax.barh(y_pos, actual_scores, color=bar_colors, edgecolor=COLORS['gray'],
                   alpha=0.85, height=0.7)

    # Score labels
    for i, (actual, maximum) in enumerate(zip(actual_scores, max_scores)):
        ax.text(maximum + 0.5, i, f'{actual:.0f}/{maximum}', va='center', fontsize=9,
                color=COLORS['fg'])

    ax.set_yticks(y_pos)
    ax.set_yticklabels(components)
    ax.set_xlim(0, 30)
    ax.set_xlabel('Score')


def draw_yield_gauge(ax, metrics: dict, current_price: float):
    """Draw yield tier visualization."""
    ax.set_title('Dividend Yield Analysis', fontsize=11, fontweight='bold')

    yield_pct = metrics['yield_pct']

    tiers = ['Low\n(<2%)', 'Average\n(2-3%)', 'Good\n(3-4%)', 'High\n(4-6%)', 'Very High\n(>6%)']
    tier_ranges = [(0, 2), (2, 3), (3, 4), (4, 6), (6, 10)]
    tier_colors = [COLORS['red'], COLORS['yellow'], COLORS['green'], COLORS['blue'], COLORS['magenta']]

    # Determine which tier the current yield falls in
    current_tier_idx = 0
    for i, (low, high) in enumerate(tier_ranges):
        if low <= yield_pct < high:
            current_tier_idx = i
            break
        if yield_pct >= high:
            current_tier_idx = i

    # Draw bars — highlight current tier, mute others
    x_pos = np.arange(len(tiers))
    bar_heights = [2, 3, 4, 6, 8]
    bar_colors = [COLORS['bg_light']] * len(tiers)
    bar_colors[current_tier_idx] = tier_colors[current_tier_idx]

    bars = ax.bar(x_pos, bar_heights, color=bar_colors, alpha=0.7,
                  edgecolor=COLORS['gray'], width=0.7)

    # Current yield line
    ax.axhline(y=yield_pct, color=COLORS['red'], linestyle='--', linewidth=2,
               label=f'Current: {yield_pct:.2f}%')

    ax.set_xticks(x_pos)
    ax.set_xticklabels(tiers, fontsize=8)
    ax.set_ylabel('Yield (%)')
    ax.set_ylim(0, 10)
    ax.legend(loc='best', fontsize=8)

    # Annual dividend annotation
    ann_div = metrics['annual_dividend']
    ax.text(0.02, 0.98, f'Annual: ${ann_div:.2f}', transform=ax.transAxes,
            va='top', fontsize=9,
            bbox=dict(boxstyle='round', facecolor=COLORS['bg_light'], alpha=0.7,
                      edgecolor=COLORS['gray']))


def draw_dividend_growth(ax, growth: dict):
    """Draw dividend growth trajectory."""
    status = growth.get('dividend_status', 'Unknown')
    consecutive = growth.get('consecutive_increases', 0)
    ax.set_title(f'Dividend Growth \u2014 {status} ({consecutive}yr streak)',
                 fontsize=11, fontweight='bold')

    periods = ['1Y', '3Y', '5Y', '10Y']
    rates = [
        growth.get('dgr_1y', 0) * 100,
        growth.get('dgr_3y', 0) * 100,
        growth.get('dgr_5y', 0) * 100,
        growth.get('dgr_10y', 0) * 100
    ]

    bar_colors = [COLORS['green'] if r > 0 else COLORS['red'] for r in rates]
    bars = ax.bar(periods, rates, color=bar_colors, alpha=0.85,
                  edgecolor=COLORS['gray'], width=0.6)

    # Value labels
    for bar, rate in zip(bars, rates):
        _bar_label(ax, bar, rate, fmt="{:.1f}%")

    ax.axhline(y=0, color=COLORS['gray'], linestyle='-', linewidth=0.5)
    ax.set_ylabel('CAGR (%)')



def draw_valuation(ax, ddm: dict, current_price: float):
    """Draw DDM valuation comparison."""
    ax.set_title('DDM Valuation vs Market Price', fontsize=11, fontweight='bold')

    methods = ['Gordon\nGrowth', 'Two-Stage\nDDM', 'H-Model', 'Average\nFair Value']
    values = [
        ddm.get('gordon_growth_value', 0),
        ddm.get('two_stage_value', 0),
        ddm.get('h_model_value', 0),
        ddm.get('average_fair_value', 0)
    ]

    # Filter out None/0 values
    valid_methods = []
    valid_values = []
    for m, v in zip(methods, values):
        if v and v > 0:
            valid_methods.append(m)
            valid_values.append(v)

    if not valid_values:
        ax.text(0.5, 0.5, 'Insufficient data\nfor DDM valuation', ha='center', va='center',
                transform=ax.transAxes, fontsize=12, color=COLORS['gray'])
        return

    x_pos = np.arange(len(valid_methods))
    bar_colors = [COLORS['green'] if v > current_price else COLORS['red'] for v in valid_values]
    bars = ax.bar(x_pos, valid_values, color=bar_colors, alpha=0.85,
                  edgecolor=COLORS['gray'], width=0.6)

    # Current price line
    ax.axhline(y=current_price, color=COLORS['cyan'], linestyle='--', linewidth=2,
               label=f'Market: ${current_price:.2f}')

    # Value labels
    for bar, val in zip(bars, valid_values):
        _bar_label(ax, bar, val, fmt="${:.0f}")

    ax.set_xticks(x_pos)
    ax.set_xticklabels(valid_methods, fontsize=8)
    ax.set_ylabel('Fair Value ($)')
    ax.legend(loc='best', fontsize=8)

    # DDM valuation badge (valuation-specific, not the income signal)
    upside = ddm.get('upside_downside_pct', 0)
    if upside and upside > 10:
        val_label = 'Undervalued'
        val_color = COLORS['green']
    elif upside and upside < -10:
        val_label = 'Overvalued'
        val_color = COLORS['red']
    else:
        val_label = 'Fair Value'
        val_color = COLORS['yellow']
    ax.text(0.02, 0.98, f'{val_label}\n({upside:+.1f}%)',
            transform=ax.transAxes, va='top', fontsize=9, fontweight='bold',
            bbox=dict(boxstyle='round', facecolor=val_color, alpha=0.3,
                      edgecolor=COLORS['gray']))


def plot_dividend(data: dict, output_path: str):
    """Create the full dividend analysis visualization."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    ticker = data['ticker']
    company = data.get('company_name', ticker)
    signal = data['signal']
    fig.suptitle(f'Dividend Analysis \u2014 {ticker} ({company}) \u2014 {signal}',
                 fontsize=14, fontweight='bold')

    # 1. Safety score breakdown (top-left)
    draw_safety_score(axes[0, 0], data['safety_score'], ticker)

    # 2. Yield gauge (top-right)
    draw_yield_gauge(axes[0, 1], data['dividend_metrics'], data['current_price'])

    # 3. Dividend growth (bottom-left)
    draw_dividend_growth(axes[1, 0], data['growth_metrics'])

    # 4. DDM valuation (bottom-right)
    draw_valuation(axes[1, 1], data['ddm_valuation'], data['current_price'])

    plt.tight_layout()
    save_figure(fig, output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Plot dividend income analysis')
    parser.add_argument('--input', required=True, help='Input dividend result JSON file')
    parser.add_argument('--output', help='Output path')
    args = parser.parse_args()

    data = load_result(args.input)
    ticker = data['ticker']

    if args.output:
        output_path = args.output
    else:
        output_dir = Path(__file__).resolve().parent.parent.parent / "output" / "plots"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f'{ticker}_dividend_analysis.svg')

    plot_dividend(data, output_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())

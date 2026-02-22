#!/usr/bin/env python3
"""
Visualize normalized multiples analysis.

Creates two figures per ticker:
1. Valuation Overview: Percentile ranks, Implied price spread
2. Quality & Signal: Quality adjustment breakdown, Price vs implied value
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
    """Load multiples result from JSON."""
    with open(filepath) as f:
        return json.load(f)


def _bar_label(ax, bar, label, max_val, fontsize=10):
    """Place label inside top of vertical bar, or above if bar is too short."""
    val = bar.get_height()
    cx = bar.get_x() + bar.get_width() / 2
    if val < max_val * 0.15:
        ax.text(cx, val + max_val * 0.02, label, ha='center', va='bottom',
                fontsize=fontsize, fontweight='bold')
    else:
        ax.text(cx, val - max_val * 0.02, label, ha='center', va='top',
                fontsize=fontsize, fontweight='bold', color=COLORS['bg'])


def _hbar_label(ax, bar, label, max_val, fontsize=9):
    """Place label inside right of horizontal bar, or outside if bar is too short."""
    val = bar.get_width()
    cy = bar.get_y() + bar.get_height() / 2
    if val < max_val * 0.15:
        ax.text(val + max_val * 0.02, cy, label, va='center', ha='left',
                fontsize=fontsize, fontweight='bold')
    else:
        ax.text(val - max_val * 0.02, cy, label, va='center', ha='right',
                fontsize=fontsize, fontweight='bold', color=COLORS['bg'])


def _signal_color(signal: str) -> str:
    """Map signal string to theme color."""
    mapping = {
        'Deep Value': COLORS['green'],
        'Undervalued': COLORS['cyan'],
        'Fair Value': COLORS['yellow'],
        'Overvalued': COLORS['orange'],
        'Expensive': COLORS['red'],
    }
    return mapping.get(signal, COLORS['gray'])


def plot_valuation_overview(data: dict, output_file: Path):
    """Figure 1: Percentile ranks + Implied price spread."""
    setup_dark_mode()

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    fig.subplots_adjust(wspace=0.35)

    ticker = data['ticker']
    price = data['current_price']
    signal = data['overall_signal']

    # Collect all valid multiples
    all_multiples = data['price_multiples'] + data['ev_multiples']
    valid = [m for m in all_multiples if m['is_valid'] and m['value'] > 0]

    # --- Plot 1: Percentile Ranks (left) ---
    ax = axes[0]

    names = [f"{m['name']} ({m['time_window']})" for m in valid]
    percentiles = [m['percentile_rank'] for m in valid]
    signals = [m['signal'] for m in valid]
    bar_colors = [_signal_color(s) for s in signals]

    bars = ax.barh(names, percentiles, color=bar_colors, alpha=0.8, edgecolor=COLORS['fg'])

    for bar, pct in zip(bars, percentiles):
        _hbar_label(ax, bar, f'{pct:.0f}%', 100, fontsize=8)

    # Zone lines
    ax.axvline(25, color=COLORS['green'], linestyle=':', alpha=0.4, linewidth=1)
    ax.axvline(40, color=COLORS['cyan'], linestyle=':', alpha=0.4, linewidth=1)
    ax.axvline(60, color=COLORS['yellow'], linestyle=':', alpha=0.4, linewidth=1)
    ax.axvline(75, color=COLORS['orange'], linestyle=':', alpha=0.4, linewidth=1)

    # Adjusted percentile marker
    adj_pct = data['quality_adjusted_percentile']
    ax.axvline(adj_pct, color=COLORS['magenta'], linestyle='--', linewidth=2,
               label=f'Adj. {adj_pct:.0f}%ile')

    # Signal zone legend
    signal_handles = [
        mpatches.Patch(color=COLORS['green'], alpha=0.8, label='Deep Value (<25)'),
        mpatches.Patch(color=COLORS['cyan'], alpha=0.8, label='Undervalued (25-40)'),
        mpatches.Patch(color=COLORS['yellow'], alpha=0.8, label='Fair Value (40-60)'),
        mpatches.Patch(color=COLORS['orange'], alpha=0.8, label='Overvalued (60-75)'),
        mpatches.Patch(color=COLORS['red'], alpha=0.8, label='Expensive (75+)'),
    ]
    # Only include signals that appear in the data
    present_signals = set(signals)
    signal_map = {
        'Deep Value': 0, 'Undervalued': 1, 'Fair Value': 2,
        'Overvalued': 3, 'Expensive': 4,
    }
    legend_handles = [signal_handles[signal_map[s]] for s in signal_map if s in present_signals]
    # Add the adj %ile line handle
    legend_handles.append(ax.get_legend_handles_labels()[0][-1])

    ax.set_xlim(0, 105)
    ax.set_xlabel('Percentile Rank')
    ax.set_title('Multiples vs Sector Benchmarks', fontsize=11, fontweight='bold')
    ax.legend(handles=legend_handles, loc='best', fontsize=7)
    ax.grid(True, alpha=0.2, axis='x')

    # --- Plot 2: Implied Price Spread (right) ---
    ax = axes[1]

    impl_names = []
    impl_values = []
    for m in valid:
        if m['implied_price'] is not None and m['implied_price'] > 0:
            impl_names.append(f"{m['name']} ({m['time_window']})")
            impl_values.append(m['implied_price'])

    if impl_values:
        max_price = max(max(impl_values), price) * 1.1
        bar_colors_impl = [COLORS['green'] if v >= price else COLORS['red'] for v in impl_values]

        bars = ax.barh(impl_names, impl_values, color=bar_colors_impl, alpha=0.8,
                       edgecolor=COLORS['fg'])

        for bar, val in zip(bars, impl_values):
            _hbar_label(ax, bar, f'${val:.0f}', max_price, fontsize=8)

        ax.axvline(price, color=COLORS['yellow'], linestyle='--', linewidth=2,
                   label=f'Price ${price:.2f}')

        median_impl = data['median_implied_price']
        if median_impl and median_impl > 0:
            ax.axvline(median_impl, color=COLORS['magenta'], linestyle=':', linewidth=2,
                       label=f'Median ${median_impl:.0f}')

        # Add upside/downside legend entries
        impl_handles = list(ax.get_legend_handles_labels()[0])
        has_upside = any(v >= price for v in impl_values)
        has_downside = any(v < price for v in impl_values)
        if has_upside:
            impl_handles.append(mpatches.Patch(color=COLORS['green'], alpha=0.8, label='Upside'))
        if has_downside:
            impl_handles.append(mpatches.Patch(color=COLORS['red'], alpha=0.8, label='Downside'))

        ax.set_xlabel('Implied Price ($)')
        ax.legend(handles=impl_handles, loc='best', fontsize=7)
    else:
        ax.text(0.5, 0.5, 'No valid implied prices', ha='center', va='center',
                transform=ax.transAxes, fontsize=12)

    ax.set_title('Implied Price by Method', fontsize=11, fontweight='bold')
    ax.grid(True, alpha=0.2, axis='x')

    fig.suptitle(f'{ticker} — Normalized Multiples ({signal})',
                 fontsize=14, fontweight='bold', color=COLORS['fg'], y=0.98)

    save_figure(fig, output_file, dpi=300)
    plt.close()
    print(f"Saved: {output_file}")


def plot_quality_signal(data: dict, output_file: Path):
    """Figure 2: Quality adjustment + Price vs implied value."""
    setup_dark_mode()

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    fig.subplots_adjust(wspace=0.35)

    ticker = data['ticker']
    price = data['current_price']

    # --- Plot 1: Quality Adjustment (left) ---
    ax = axes[0]

    qa = data['quality_adjustment']
    labels = ['Growth', 'Margin', 'Return', 'Total']
    values = [
        qa['growth_premium_pct'],
        qa['margin_premium_pct'],
        qa['return_premium_pct'],
        qa['total_fair_premium_pct']
    ]
    bar_colors = [COLORS['green'] if v >= 0 else COLORS['red'] for v in values]

    bars = ax.barh(labels, values, color=bar_colors, alpha=0.8,
                   edgecolor=COLORS['fg'], height=0.6)
    max_abs = max(abs(v) for v in values) if values else 1
    for bar, val in zip(bars, values):
        cy = bar.get_y() + bar.get_height() / 2
        if abs(val) >= max_abs * 0.15:
            # Inside the bar, near the end
            ha = 'right' if val >= 0 else 'left'
            x = val - max_abs * 0.02 if val >= 0 else val + max_abs * 0.02
            ax.text(x, cy, f'{val:+.1f}%', ha=ha, va='center',
                    fontsize=10, fontweight='bold', color=COLORS['bg'])
        else:
            # Outside the bar
            x = val + max_abs * 0.03 if val >= 0 else val - max_abs * 0.03
            ax.text(x, cy, f'{val:+.1f}%', ha='left' if val >= 0 else 'right',
                    va='center', fontsize=10, fontweight='bold')

    ax.axvline(0, color=COLORS['fg'], linewidth=0.5, alpha=0.5)
    ax.set_xlabel('Premium (%)')
    ax.set_title('Quality Adjustment', fontsize=11, fontweight='bold')
    ax.grid(True, alpha=0.2, axis='x')

    qa_handles = [
        mpatches.Patch(color=COLORS['green'], alpha=0.8, label='Justifies premium'),
        mpatches.Patch(color=COLORS['red'], alpha=0.8, label='Justifies discount'),
    ]
    ax.legend(handles=qa_handles, loc='best', fontsize=7)

    # --- Plot 2: Price vs Implied (right) ---
    ax = axes[1]

    avg_impl = data['average_implied_price']
    median_impl = data['median_implied_price']
    raw_pct = data['composite_percentile']
    adj_pct = data['quality_adjusted_percentile']

    bar_labels = ['Current Price', 'Median Implied', 'Average Implied']
    bar_values = [price, median_impl or 0, avg_impl or 0]
    bar_colors = [
        COLORS['yellow'],
        COLORS['green'] if (median_impl or 0) > price else COLORS['red'],
        COLORS['green'] if (avg_impl or 0) > price else COLORS['red'],
    ]

    bars = ax.bar(bar_labels, bar_values, color=bar_colors, alpha=0.8,
                  edgecolor=COLORS['fg'], width=0.6)
    for bar, val in zip(bars, bar_values):
        _bar_label(ax, bar, f'${val:.0f}', max(bar_values))

    ax.margins(x=0.15)

    pv_handles = [
        mpatches.Patch(color=COLORS['yellow'], alpha=0.8, label='Current price'),
        mpatches.Patch(color=COLORS['green'], alpha=0.8, label='Implied > price'),
        mpatches.Patch(color=COLORS['red'], alpha=0.8, label='Implied < price'),
    ]
    ax.legend(handles=pv_handles, loc='best', fontsize=7)

    # Show percentile shift in subtitle
    ax.text(0.5, 0.92, f'Raw {raw_pct:.0f}%ile → Adj {adj_pct:.0f}%ile',
            ha='center', fontsize=10, color=COLORS['magenta'],
            transform=ax.transAxes)

    ax.set_ylabel('$/Share')
    ax.set_title('Price vs Implied Value', fontsize=11, fontweight='bold')
    ax.grid(True, alpha=0.2, axis='y')

    signal = data['overall_signal']
    confidence = data['confidence']
    fig.suptitle(f'{ticker} — Quality & Signal ({signal}, {confidence:.0f}% conf.)',
                 fontsize=14, fontweight='bold', color=COLORS['fg'], y=0.98)

    save_figure(fig, output_file, dpi=300)
    plt.close()
    print(f"Saved: {output_file}")


def print_summary(data: dict):
    """Print summary to console."""
    ticker = data['ticker']
    price = data['current_price']
    signal = data['overall_signal']
    confidence = data['confidence']
    raw_pct = data['composite_percentile']
    adj_pct = data['quality_adjusted_percentile']
    avg_impl = data['average_implied_price']
    median_impl = data['median_implied_price']
    cheapest = data['cheapest_multiple']
    most_exp = data['most_expensive_multiple']

    upside_avg = ((avg_impl - price) / price * 100) if avg_impl and price > 0 else 0
    upside_med = ((median_impl - price) / price * 100) if median_impl and price > 0 else 0

    print(f"\n{'='*40}")
    print(f"  {ticker} NORMALIZED MULTIPLES")
    print(f"{'='*40}")
    print(f"  Price:          ${price:.2f}")
    print(f"  Signal:         {signal}")
    print(f"  Confidence:     {confidence:.0f}%")
    print(f"  Raw %ile:       {raw_pct:.0f}")
    print(f"  Adj %ile:       {adj_pct:.0f}")
    print()
    print(f"  Avg Implied:    ${avg_impl:.2f} ({upside_avg:+.1f}%)")
    print(f"  Median Implied: ${median_impl:.2f} ({upside_med:+.1f}%)")
    print(f"  Cheapest:       {cheapest}")
    print(f"  Most Expensive: {most_exp}")
    print(f"{'='*40}\n")


def plot_comparison(data: dict, output_file: Path):
    """Comparison figure for comparative analysis across tickers."""
    setup_dark_mode()

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    fig.subplots_adjust(wspace=0.35)

    tickers = data['tickers']

    # --- Plot 1: Value & Quality-Adjusted Scores (left) ---
    ax = axes[0]

    value_scores = {r['ticker']: r['score'] for r in data['value_score_ranking']}
    qa_scores = {r['ticker']: r['score'] for r in data['quality_adjusted_ranking']}

    x = np.arange(len(tickers))
    w = 0.35
    vs = [value_scores.get(t, 0) for t in tickers]
    qa = [qa_scores.get(t, 0) for t in tickers]

    bars1 = ax.bar(x - w/2, vs, w, color=COLORS['cyan'], alpha=0.8,
                   edgecolor=COLORS['fg'], label='Value Score')
    bars2 = ax.bar(x + w/2, qa, w, color=COLORS['magenta'], alpha=0.8,
                   edgecolor=COLORS['fg'], label='Quality-Adjusted')

    max_val = max(max(vs, default=0), max(qa, default=0))
    for bar, val in zip(list(bars1) + list(bars2), vs + qa):
        _bar_label(ax, bar, f'{val:.0f}', max_val, fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(tickers, rotation=90, ha='center')
    ax.set_ylabel('Score')
    ax.set_title('Value & Quality Scores', fontsize=11, fontweight='bold')
    ax.legend(loc='best', fontsize=7)
    ax.grid(True, alpha=0.2, axis='y')

    # --- Plot 2: Key Multiples (right) ---
    ax = axes[1]

    # Build grouped horizontal bars for P/E NTM, EV/EBITDA, PEG
    metrics = [
        ('P/E NTM', {r['ticker']: r['value'] for r in data['pe_ntm_ranking']}),
        ('EV/EBITDA', {r['ticker']: r['value'] for r in data['ev_ebitda_ranking']}),
        ('PEG', {r['ticker']: r['value'] for r in data['peg_ranking']}),
    ]

    y = np.arange(len(tickers))
    h = 0.25
    colors_list = [COLORS['cyan'], COLORS['yellow'], COLORS['green']]

    for i, (metric_name, vals) in enumerate(metrics):
        bar_vals = []
        for t in tickers:
            v = vals.get(t, 0)
            # Skip invalid/negative values
            bar_vals.append(max(v, 0))
        ax.barh(y + (i - 1) * h, bar_vals, h, color=colors_list[i], alpha=0.8,
                edgecolor=COLORS['fg'], label=metric_name)

    ax.set_yticks(y)
    ax.set_yticklabels(tickers)
    ax.set_xlabel('Multiple Value')
    ax.set_title('Key Multiples Comparison', fontsize=11, fontweight='bold')
    ax.legend(loc='best', fontsize=7)
    ax.grid(True, alpha=0.2, axis='x')

    best_val = data.get('best_value', '')
    best_qa = data.get('best_quality_adjusted', '')
    subtitle = f'Best Value: {best_val} | Best Quality-Adj: {best_qa}'
    fig.suptitle(f'Normalized Multiples — Comparative Analysis',
                 fontsize=14, fontweight='bold', color=COLORS['fg'], y=0.98)
    fig.text(0.5, 0.92, subtitle, ha='center', fontsize=10, color=COLORS['magenta'])

    save_figure(fig, output_file, dpi=300)
    plt.close()
    print(f"Saved: {output_file}")


def print_comparison_summary(data: dict):
    """Print comparative analysis summary to console."""
    print(f"\n{'='*50}")
    print(f"  NORMALIZED MULTIPLES — COMPARATIVE ANALYSIS")
    print(f"{'='*50}")
    print(f"  Tickers: {', '.join(data['tickers'])}")
    print(f"  Best Value:        {data['best_value']}")
    print(f"  Best Quality-Adj:  {data['best_quality_adjusted']}")
    print(f"  Best PEG:          {data['best_peg']}")
    print()
    print("  Quality-Adjusted Ranking:")
    for r in data['quality_adjusted_ranking']:
        print(f"    {r['ticker']:>6s}  {r['score']:6.1f}")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(description='Visualize normalized multiples')
    parser.add_argument('-i', '--input', type=str, required=True,
                        help='Input JSON result file')
    parser.add_argument('-o', '--output-dir', type=str,
                        default='valuation/normalized_multiples/output/plots',
                        help='Output directory for plots')
    parser.add_argument('--comparison', action='store_true',
                        help='Input is a comparison JSON (not single ticker)')

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = load_result(input_path)

    if args.comparison:
        print_comparison_summary(data)
        plot_comparison(data, output_dir / "multiples_comparison.png")
    else:
        ticker = data['ticker']
        print_summary(data)
        plot_valuation_overview(data, output_dir / f"{ticker}_multiples_valuation.png")
        plot_quality_signal(data, output_dir / f"{ticker}_multiples_quality.png")


if __name__ == '__main__':
    main()

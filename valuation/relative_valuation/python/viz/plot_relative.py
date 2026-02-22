#!/usr/bin/env python3
"""
Relative Valuation Visualization

Creates a 2x2 dashboard showing:
1. Peer similarity scores
2. Multiple comparison (target vs peer median)
3. Implied price waterfall
4. Summary assessment
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

setup_dark_mode()


def load_result(path: str) -> dict:
    """Load relative valuation result JSON file."""
    with open(path) as f:
        return json.load(f)


def _kanagawa_gradient(n, base_color=None):
    """Generate a gradient from COLORS['bg_light'] to a base color."""
    if base_color is None:
        base_color = COLORS['blue']
    lo = mcolors.to_rgb(COLORS['bg_light'])
    hi = mcolors.to_rgb(base_color)
    return [
        mcolors.to_hex(tuple(lo[j] + (hi[j] - lo[j]) * t for j in range(3)))
        for t in np.linspace(0.3, 1.0, n)
    ]


def draw_peer_similarity(ax, peers: list, ticker: str):
    """Draw peer similarity scores as horizontal bars."""
    ax.set_title('Peer Group Similarity Scores', fontsize=11, fontweight='bold')

    if not peers:
        ax.text(0.5, 0.5, 'No peers found', ha='center', va='center',
                transform=ax.transAxes, fontsize=12, color=COLORS['gray'])
        return

    # Sort by total score descending
    peers_sorted = sorted(peers, key=lambda x: x['total_score'], reverse=True)[:8]

    tickers = [p['ticker'] for p in peers_sorted]
    scores = [p['total_score'] for p in peers_sorted]

    y_pos = np.arange(len(tickers))
    gradient = _kanagawa_gradient(len(tickers), COLORS['cyan'])

    bars = ax.barh(y_pos, scores, color=gradient, edgecolor=COLORS['bg_light'], alpha=0.85)

    # Score labels
    for bar, score in zip(bars, scores):
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
                f'{score:.0f}', va='center', fontsize=9, color=COLORS['fg'])

    ax.set_yticks(y_pos)
    ax.set_yticklabels(tickers)
    ax.set_xlabel('Similarity Score')
    ax.set_xlim(0, 100)
    ax.invert_yaxis()


def draw_multiple_comparison(ax, comparisons: list, ticker: str):
    """Draw target vs peer median multiples."""
    ax.set_title('Valuation Multiples: Target vs Peers', fontsize=11, fontweight='bold')

    if not comparisons:
        ax.text(0.5, 0.5, 'No comparison data', ha='center', va='center',
                transform=ax.transAxes, fontsize=12, color=COLORS['gray'])
        return

    # Select key multiples
    key_multiples = ['P/E (Forward)', 'EV/EBITDA', 'P/S', 'P/FCF']
    filtered = [c for c in comparisons if c['multiple'] in key_multiples]

    if not filtered:
        filtered = comparisons[:4]

    multiples = [c['multiple'].replace(' ', '\n') for c in filtered]
    target_vals = [c['target_value'] for c in filtered]
    peer_vals = [c['peer_median'] for c in filtered]
    premiums = [c['premium_pct'] for c in filtered]

    x = np.arange(len(multiples))
    width = 0.35

    ax.bar(x - width/2, target_vals, width, label=ticker,
           color=COLORS['blue'], alpha=0.85, edgecolor=COLORS['bg_light'])
    ax.bar(x + width/2, peer_vals, width, label='Peer Median',
           color=COLORS['gray'], alpha=0.85, edgecolor=COLORS['bg_light'])

    ax.set_xticks(x)
    ax.set_xticklabels(multiples, fontsize=8)
    ax.set_ylabel('Multiple')
    ax.legend(loc='upper right', fontsize=8)

    # Premium/discount annotations
    for i, (t, p, prem) in enumerate(zip(target_vals, peer_vals, premiums)):
        color = COLORS['red'] if prem > 20 else COLORS['green'] if prem < -10 else COLORS['yellow']
        label = f'{abs(prem):.0f}% premium' if prem > 0 else f'{abs(prem):.0f}% discount'
        ax.annotate(label, xy=(i, max(t, p)),
                    ha='center', va='bottom', fontsize=8, color=color, fontweight='bold')


def draw_implied_price_waterfall(ax, valuations: list, current_price: float, ticker: str):
    """Draw implied prices from different methods."""
    ax.set_title('Implied Fair Value by Method', fontsize=11, fontweight='bold')

    if not valuations:
        ax.text(0.5, 0.5, 'No valuation data', ha='center', va='center',
                transform=ax.transAxes, fontsize=12, color=COLORS['gray'])
        return

    # Filter out extreme outliers
    valid = [v for v in valuations if 0 < v['implied_price'] < current_price * 5]
    if not valid:
        valid = valuations[:5]

    methods = [v['method'].replace(' ', '\n') for v in valid]
    prices = [v['implied_price'] for v in valid]
    upsides = [v['upside_pct'] for v in valid]

    x = np.arange(len(methods))
    bar_colors = [COLORS['green'] if u > 0 else COLORS['red'] for u in upsides]

    bars = ax.bar(x, prices, color=bar_colors, alpha=0.75, edgecolor=COLORS['bg_light'])

    # Current price line
    ax.axhline(y=current_price, color=COLORS['blue'], linestyle='--', linewidth=2,
               label=f'Market: ${current_price:.2f}')

    # Price labels — position inside bar if it would overlap with title
    max_price = max(prices) if prices else 0
    for bar, price, upside in zip(bars, prices, upsides):
        label = f'${price:.0f}\n({upside:+.0f}%)'
        if price > max_price * 0.75:
            # Place inside bar to avoid title overlap
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 0.85,
                    label, ha='center', va='top', fontsize=8,
                    color=COLORS['bg'])
        else:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max_price * 0.02,
                    label, ha='center', va='bottom', fontsize=8,
                    color=COLORS['fg'])

    ax.set_xticks(x)
    ax.set_xticklabels(methods, fontsize=7)
    ax.set_ylabel('Implied Price ($)')
    ax.legend(loc='upper right', fontsize=8)


def draw_summary(ax, data: dict):
    """Draw summary assessment."""
    ax.axis('off')
    ax.set_title('Relative Valuation Summary', fontsize=11, fontweight='bold')

    ticker = data['ticker']
    score = data['relative_score']
    assessment = data['assessment']
    signal = data['signal']
    avg_price = data['average_implied_price']
    current = data['current_price']
    upside = (avg_price / current - 1) * 100 if avg_price and current else 0.0

    # Assessment color
    if 'Undervalued' in assessment:
        color = COLORS['green']
    elif 'Overvalued' in assessment:
        color = COLORS['red']
    else:
        color = COLORS['yellow']

    # Large assessment display
    ax.text(0.5, 0.75, assessment.upper(), ha='center', va='center',
            fontsize=20, fontweight='bold', color=color,
            transform=ax.transAxes)

    ax.text(0.5, 0.55, f'Score: {score:.0f}/100', ha='center', va='center',
            fontsize=14, transform=ax.transAxes)

    if avg_price:
        ax.text(0.5, 0.35, f'Avg Implied: ${avg_price:.2f}', ha='center', va='center',
                fontsize=12, transform=ax.transAxes)
        ax.text(0.5, 0.2, f'vs Market ${current:.2f} ({upside:+.1f}%)', ha='center', va='center',
                fontsize=11, color=COLORS['gray'], transform=ax.transAxes)
    else:
        ax.text(0.5, 0.35, 'Insufficient peer multiples', ha='center', va='center',
                fontsize=12, color=COLORS['gray'], transform=ax.transAxes)
        ax.text(0.5, 0.2, f'Market: ${current:.2f}', ha='center', va='center',
                fontsize=11, color=COLORS['gray'], transform=ax.transAxes)

    # Signal badge
    signal_colors = {
        'Strong Buy': COLORS['green'],
        'Buy': COLORS['green'],
        'Hold': COLORS['yellow'],
        'Caution': COLORS['orange'],
        'Sell': COLORS['red'],
    }
    sig_color = signal_colors.get(signal, COLORS['gray'])
    ax.text(0.5, 0.05, f'Signal: {signal}', ha='center', va='center',
            fontsize=12, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.5', facecolor=sig_color, alpha=0.3,
                      edgecolor=sig_color),
            transform=ax.transAxes)


def plot_relative(data: dict, output_path: str):
    """Create the full relative valuation visualization."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    ticker = data['ticker']
    company = data.get('company_name', ticker)
    fig.suptitle(f'Relative Valuation - {ticker} ({company})', fontsize=14, fontweight='bold')

    # 1. Peer similarity (top-left)
    draw_peer_similarity(axes[0, 0], data.get('peer_similarities', []), ticker)

    # 2. Multiple comparison (top-right)
    draw_multiple_comparison(axes[0, 1], data.get('multiple_comparisons', []), ticker)

    # 3. Implied price waterfall (bottom-left)
    draw_implied_price_waterfall(axes[1, 0], data.get('implied_valuations', []),
                                  data['current_price'], ticker)

    # 4. Summary (bottom-right)
    draw_summary(axes[1, 1], data)

    plt.tight_layout()
    save_figure(fig, output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Plot relative valuation')
    parser.add_argument('--input', required=True, help='Input relative valuation JSON file')
    parser.add_argument('--output', help='Output PNG path')
    args = parser.parse_args()

    data = load_result(args.input)
    ticker = data['ticker']

    if args.output:
        output_path = args.output
    else:
        output_dir = Path(__file__).resolve().parent.parent.parent / "output" / "plots"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f'{ticker}_relative_valuation.png')

    plot_relative(data, output_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""
Perpetual Futures Pricing Visualization

Creates a 2x2 dashboard showing:
1. Basis and funding rate analysis
2. Theoretical vs market price comparison
3. Arbitrage signal gauge
4. Everlasting option payoff (if applicable)
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
    """Load analysis result JSON file."""
    with open(path) as f:
        return json.load(f)


def draw_basis_analysis(ax, market: dict, theoretical: dict):
    """Draw basis and funding rate comparison."""
    ax.set_title('Basis & Funding Analysis', fontsize=11, fontweight='bold')

    # Compare market vs theoretical funding
    categories = ['Market\nFunding', 'Fair\nFunding', 'Basis\n(bps)']

    market_funding = market.get('funding_rate', 0) * 100  # Convert to %
    fair_funding = theoretical.get('fair_funding_rate', 0) * 100
    basis_bps = theoretical.get('basis_pct', 0) * 100  # basis_pct is already %

    values = [market_funding, fair_funding, basis_bps]
    C = COLORS
    colors = [C['blue'], C['green'], C['magenta']]

    bars = ax.bar(categories, values, color=colors, alpha=0.7, edgecolor=C['fg'])

    # Value labels: inside tall bars (vertical), above short bars (horizontal)
    max_val = max(abs(v) for v in values) if values else 1
    for bar, val in zip(bars, values):
        if abs(val) > max_val * 0.15:
            # Tall bar: label inside, vertical
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 0.5,
                    f'{val:.3f}%', ha='center', va='center', fontsize=9,
                    fontweight='bold', rotation=90, color=C['fg'])
        else:
            # Short bar: label above, horizontal
            y_pos = bar.get_height() + max_val * 0.02
            ax.text(bar.get_x() + bar.get_width()/2, y_pos,
                    f'{val:.3f}%', ha='center', va='bottom', fontsize=9,
                    fontweight='bold', color=C['fg'])

    ax.axhline(y=0, color=C['fg'], linestyle='-', linewidth=0.5)
    ax.set_ylabel('Rate (%)')

    # Funding interval
    interval = market.get('funding_interval_hours', 8)
    ax.text(0.98, 0.98, f'Funding: every {interval}h', transform=ax.transAxes,
            ha='right', va='top', fontsize=9, color=C['fg'])


def draw_price_comparison(ax, market: dict, theoretical: dict):
    """Draw market vs theoretical price comparison."""
    ax.set_title('Price Comparison', fontsize=11, fontweight='bold')

    prices = {
        'Spot': market.get('spot', 0),
        'Index': market.get('index_price', 0),
        'Mark': market.get('mark_price', 0),
        'Theoretical': theoretical.get('futures_price', 0),
    }

    # Filter out zero values
    prices = {k: v for k, v in prices.items() if v > 0}

    if not prices:
        ax.text(0.5, 0.5, 'No price data', ha='center', va='center',
                transform=ax.transAxes, fontsize=12, color='gray')
        return

    names = list(prices.keys())
    values = list(prices.values())

    C = COLORS
    colors = [C['blue'], C['green'], C['red'], C['magenta']][:len(names)]
    bars = ax.bar(names, values, color=colors, alpha=0.7, edgecolor=C['fg'])

    # Value labels inside bars, vertical
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 0.5,
                f'${val:,.0f}', ha='center', va='center', fontsize=9,
                fontweight='bold', rotation=90, color=COLORS['fg'])

    ax.set_ylabel('Price ($)')

    # Mispricing annotation
    spot = market.get('spot', 0)
    if spot > 0:
        basis = theoretical.get('basis', 0)
        ax.text(0.02, 0.98, f'Basis: ${basis:+.2f}', transform=ax.transAxes,
                ha='left', va='top', fontsize=9,
                bbox=dict(boxstyle='round', facecolor=COLORS['bg_light'], edgecolor=COLORS['gray'], alpha=0.8))


def draw_arbitrage_signal(ax, mispricing: float, mispricing_pct: float, signal: str):
    """Draw arbitrage signal gauge."""
    ax.set_title('Arbitrage Signal', fontsize=11, fontweight='bold')
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.set_aspect('equal')
    ax.axis('off')

    # Signal color
    C = COLORS
    if signal == 'LONG':
        color = C['green']
        desc = 'Futures underpriced\nGo LONG perpetual'
    elif signal == 'SHORT':
        color = C['red']
        desc = 'Futures overpriced\nGo SHORT perpetual'
    else:
        color = C['gray']
        desc = 'No significant\nmispricing detected'

    # Draw signal indicator
    circle = plt.Circle((5, 5), 1.8, color=color, alpha=0.3)
    ax.add_patch(circle)
    circle_border = plt.Circle((5, 5), 1.8, fill=False, color=color, linewidth=3)
    ax.add_patch(circle_border)

    ax.text(5, 5, signal, ha='center', va='center',
            fontsize=16, fontweight='bold', color=color)

    # Mispricing details
    ax.text(5, 2.4, desc, ha='center', va='center', fontsize=12, color=C['fg'])
    ax.text(5, 1.0, f'Mispricing: {mispricing_pct:+.3f}%', ha='center', va='center',
            fontsize=13, fontweight='bold', color=C['fg'])


def draw_summary_table(ax, market: dict, theoretical: dict):
    """Draw summary statistics table."""
    ax.axis('off')
    ax.set_title('Analysis Summary', fontsize=11, fontweight='bold')

    symbol = market.get('symbol', 'N/A')
    timestamp = market.get('timestamp', 'N/A')
    oi = market.get('open_interest')
    vol = market.get('volume_24h')
    perfect_iota = theoretical.get('perfect_iota', 0)

    rows = [
        ['Symbol', symbol],
        ['Timestamp', timestamp[:19] if len(timestamp) > 19 else timestamp],
        ['Perfect ι (f=x)', f'{perfect_iota:.4f}'],
        ['Open Interest', f'${oi:,.0f}' if oi else 'N/A'],
        ['24h Volume', f'${vol:,.0f}' if vol else 'N/A'],
    ]

    table = ax.table(cellText=rows, loc='center', cellLoc='left',
                     colWidths=[0.5, 0.5])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.8)

    # Style
    for i in range(len(rows)):
        table[(i, 0)].set_facecolor(COLORS['bg_light'])
        table[(i, 0)].set_text_props(fontweight='bold', color=COLORS['fg'])
        table[(i, 1)].set_facecolor(COLORS['bg'])
        table[(i, 1)].set_text_props(color=COLORS['fg'])


def plot_perpetual(data: dict, output_path: str):
    """Create the full perpetual futures visualization."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    market = data.get('market', {})
    theoretical = data.get('theoretical', {})
    symbol = market.get('symbol', 'Unknown')

    fig.suptitle(f'Perpetual Futures Analysis - {symbol}', fontsize=14, fontweight='bold')

    # 1. Basis analysis (top-left)
    draw_basis_analysis(axes[0, 0], market, theoretical)

    # 2. Price comparison (top-right)
    draw_price_comparison(axes[0, 1], market, theoretical)

    # 3. Arbitrage signal (bottom-left)
    draw_arbitrage_signal(axes[1, 0],
                          data.get('mispricing', 0),
                          data.get('mispricing_pct', 0),
                          data.get('arbitrage_signal', 'NEUTRAL'))

    # 4. Summary table (bottom-right)
    draw_summary_table(axes[1, 1], market, theoretical)

    plt.tight_layout()
    save_figure(fig, output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Plot perpetual futures analysis')
    parser.add_argument('--input', required=True, help='Input analysis JSON file')
    parser.add_argument('--output', help='Output PNG path')
    args = parser.parse_args()

    data = load_result(args.input)

    symbol = data.get('market', {}).get('symbol', 'UNKNOWN')
    # Clean symbol for filename
    symbol_clean = symbol.replace('/', '_').replace('-', '_')

    if args.output:
        output_path = args.output
    else:
        output_dir = Path(__file__).resolve().parent.parent.parent / "output" / "plots"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f'{symbol_clean}_perpetual_analysis.png')

    plot_perpetual(data, output_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())

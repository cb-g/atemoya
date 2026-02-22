#!/usr/bin/env python3
"""
Plot Pareto frontier (cost vs protection trade-off)
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

setup_dark_mode()
sns.set_palette([COLORS['blue'], COLORS['green'], COLORS['red'], COLORS['magenta']])


def plot_pareto_frontier(df_frontier, output_file, ticker=''):
    """
    Plot Pareto frontier showing cost vs protection trade-off
    """
    costs = df_frontier['cost'].values
    protections = df_frontier['protection_level'].values
    strategies = df_frontier['strategy'].values

    # Create figure
    fig, ax = plt.subplots(figsize=(14, 9))
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['bg'])

    # Style by strategy type: distinct colors AND markers
    style_by_type = {
        'ProtectivePut': {'color': COLORS['cyan'], 'marker': 's', 'label': 'Protective Put'},
        'Collar':        {'color': COLORS['orange'], 'marker': 'D', 'label': 'Collar'},
        'VerticalSpread':{'color': COLORS['magenta'], 'marker': '^', 'label': 'Vertical Spread'},
        'CoveredCall':   {'color': COLORS['yellow'], 'marker': 'o', 'label': 'Covered Call'},
    }

    strategy_types = [s.split('(')[0] for s in strategies]
    unique_types = sorted(set(strategy_types))

    # Plot each strategy type separately for proper legend
    for st in unique_types:
        style = style_by_type.get(st, {'color': COLORS['gray'], 'marker': 'o', 'label': st})
        mask = [t == st for t in strategy_types]
        ax.scatter(costs[mask], protections[mask], s=160, alpha=0.85,
                   c=style['color'], marker=style['marker'],
                   edgecolors=COLORS['fg'], linewidth=1.5,
                   label=style['label'], zorder=3)

    # Plot frontier line
    sorted_idx = np.argsort(costs)
    ax.plot(costs[sorted_idx], protections[sorted_idx], '--',
            color=COLORS['cyan'], alpha=0.5, linewidth=1.5, zorder=1)

    # Find and highlight recommended strategy (middle of frontier)
    rec_idx = len(df_frontier) // 2
    ax.scatter(costs[rec_idx], protections[rec_idx],
              s=400, marker='*', color=COLORS['red'],
              edgecolor=COLORS['fg'], linewidth=2,
              label='Recommended', zorder=5)

    # Annotate key points
    # Min cost
    min_cost_idx = np.argmin(costs)
    ax.annotate(f"Min Cost\n${costs[min_cost_idx]:.0f}",
               (costs[min_cost_idx], protections[min_cost_idx]),
               xytext=(15, 15), textcoords='offset points',
               fontsize=9, alpha=0.9,
               bbox=dict(boxstyle='round', facecolor=COLORS['bg'], alpha=0.8, edgecolor=COLORS['gray']),
               arrowprops=dict(arrowstyle='->', color=COLORS['gray'], lw=1.5))

    # Max protection
    max_prot_idx = np.argmax(protections)
    ax.annotate(f"Max Protection\n${protections[max_prot_idx]:.0f}",
               (costs[max_prot_idx], protections[max_prot_idx]),
               xytext=(15, -25), textcoords='offset points',
               fontsize=9, alpha=0.9,
               bbox=dict(boxstyle='round', facecolor=COLORS['bg'], alpha=0.8, edgecolor=COLORS['gray']),
               arrowprops=dict(arrowstyle='->', color=COLORS['gray'], lw=1.5))

    # Recommended
    ax.annotate(f"Recommended\nCost: ${costs[rec_idx]:.0f}\nProtection: ${protections[rec_idx]:.0f}",
               (costs[rec_idx], protections[rec_idx]),
               xytext=(-80, 30), textcoords='offset points',
               fontsize=10, alpha=0.9, fontweight='bold',
               bbox=dict(boxstyle='round', facecolor=COLORS['bg'], alpha=0.9, edgecolor=COLORS['red']),
               arrowprops=dict(arrowstyle='->', color=COLORS['red'], lw=2))

    ax.set_xlabel('Hedge Cost ($)', fontsize=13)
    ax.set_ylabel('Protection Level ($ Portfolio Value)', fontsize=13)
    title_prefix = f'{ticker} — ' if ticker else ''
    ax.set_title(f'{title_prefix}Pareto Frontier: Cost vs Protection Trade-off', fontsize=15, fontweight='bold', pad=20)
    ax.grid(True, alpha=0.2)

    ax.legend(loc='lower right', fontsize=10)

    # Add info box
    info_text = (
        f"Pareto Efficient Points: {len(df_frontier)}\n"
        f"Cost Range: ${costs.min():.0f} - ${costs.max():.0f}\n"
        f"Protection Range: ${protections.min():.0f} - ${protections.max():.0f}"
    )
    ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
            fontsize=10, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor=COLORS['bg'], alpha=0.8, edgecolor=COLORS['gray']))

    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    print(f"Saved Pareto frontier to {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Plot Pareto frontier')
    parser.add_argument('--ticker', default='', help='Ticker symbol for plot title')
    parser.add_argument('--frontier-file', default='pricing/options_hedging/output/pareto_frontier.csv',
                       help='Pareto frontier CSV file')
    parser.add_argument('--output-dir', default='pricing/options_hedging/output/plots',
                       help='Output directory')

    args = parser.parse_args()

    try:
        # Load frontier
        frontier_file = Path(args.frontier_file)
        if not frontier_file.exists():
            raise FileNotFoundError(f"Frontier file not found: {frontier_file}")

        df_frontier = pd.read_csv(frontier_file)

        if df_frontier.empty:
            raise ValueError("Frontier file is empty")

        # Create output directory
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Plot
        output_file = output_dir / 'pareto_frontier.png'
        plot_pareto_frontier(df_frontier, output_file, ticker=args.ticker)

        print(f"\n✓ Successfully generated Pareto frontier plot")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

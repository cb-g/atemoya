#!/usr/bin/env python3
"""
Plot Greeks summary from hedge strategies
"""

import argparse
import sys
import traceback
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

setup_dark_mode()


def plot_greeks_summary(df_frontier, output_file, ticker=''):
    """Plot Greeks for all strategies in frontier"""
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    fig.patch.set_facecolor(COLORS['bg'])
    if ticker:
        fig.suptitle(f'{ticker} — Greeks Summary', fontsize=14, fontweight='bold', y=1.02)

    greeks = ['delta', 'gamma', 'vega', 'theta', 'rho']
    costs = df_frontier['cost'].values

    for idx, greek in enumerate(greeks):
        row = idx // 3
        col = idx % 3
        ax = axes[row, col]
        ax.set_facecolor(COLORS['bg'])

        values = df_frontier[greek].values

        # Scatter plot
        ax.scatter(costs, values, s=100, alpha=0.6, color=COLORS['blue'])
        ax.plot(costs, values, '--', alpha=0.3, color=COLORS['cyan'])

        ax.set_xlabel('Cost ($)', fontsize=10)
        ax.set_ylabel(greek.capitalize(), fontsize=10)
        ax.set_title(f'{greek.upper()} vs Cost', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.2)

    # Remove empty subplot
    axes[1, 2].remove()

    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    print(f"Saved Greeks plot to {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Plot Greeks summary')
    parser.add_argument('--ticker', default='', help='Ticker symbol for plot title')
    parser.add_argument('--frontier-file', default='pricing/options_hedging/output/pareto_frontier.csv')
    parser.add_argument('--output-dir', default='pricing/options_hedging/output/plots')

    args = parser.parse_args()

    try:
        df = pd.read_csv(args.frontier_file)
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / 'greeks_summary.png'
        plot_greeks_summary(df, output_file, ticker=args.ticker)

        print("\n✓ Successfully generated Greeks plot")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

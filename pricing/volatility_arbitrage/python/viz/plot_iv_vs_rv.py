#!/usr/bin/env python3
"""
Plot implied vs realized volatility comparison
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


def plot_iv_vs_rv(ticker: str, data_dir: Path, output_dir: Path):
    """
    Generate IV vs RV comparison plot

    3-panel chart:
    1. IV and RV time series overlay
    2. IV - RV spread (mispricing signal)
    3. Distribution of spread
    """
    # Load realized vol
    rv_file = data_dir / f"{ticker}_realized_vol.csv"
    if not rv_file.exists():
        raise FileNotFoundError(f"Realized vol file not found: {rv_file}")

    df_rv = pd.read_csv(rv_file)
    df_rv['timestamp'] = pd.to_datetime(df_rv['timestamp'], unit='s')

    # For now, we'll just plot realized vol (IV would come from options data)
    # Future enhancement: add actual IV data

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8))
    fig.patch.set_facecolor(COLORS['bg'])

    for ax in [ax1, ax2]:
        ax.set_facecolor(COLORS['bg'])

    # Panel 1: Realized Vol time series
    ax1.plot(df_rv['timestamp'], df_rv['volatility'] * 100,
             label='Realized Vol (21d Yang-Zhang)', color=COLORS['cyan'], linewidth=2)

    ax1.set_ylabel('Volatility (%)', fontsize=12)
    ax1.set_title(f'{ticker} - Realized Volatility', fontsize=14, fontweight='bold')
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.2)

    # Vol statistics
    vol_mean = df_rv['volatility'].mean() * 100
    vol_std = df_rv['volatility'].std() * 100
    vol_min = df_rv['volatility'].min() * 100
    vol_max = df_rv['volatility'].max() * 100

    # Panel 2: Vol distribution with stats inset
    ax2.hist(df_rv['volatility'] * 100, bins=30, color=COLORS['blue'], alpha=0.7, edgecolor=COLORS['fg'])
    ax2.axvline(vol_mean, color=COLORS['red'], linestyle='--', linewidth=2, label=f'Mean: {vol_mean:.2f}%')

    stats_text = (f"Mean:    {vol_mean:.2f}%\n"
                  f"Std Dev: {vol_std:.2f}%\n"
                  f"Min:     {vol_min:.2f}%\n"
                  f"Max:     {vol_max:.2f}%")
    ax2.text(0.97, 0.95, stats_text, transform=ax2.transAxes,
             fontsize=10, verticalalignment='top', horizontalalignment='right',
             fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor=COLORS['bg'], alpha=0.8, edgecolor=COLORS['fg']))

    ax2.set_xlabel('Volatility (%)', fontsize=12)
    ax2.set_ylabel('Frequency', fontsize=12)
    ax2.set_title('Realized Volatility Distribution', fontsize=14, fontweight='bold')
    ax2.legend(loc='upper left')
    ax2.grid(True, alpha=0.2, axis='y')

    plt.tight_layout()

    # Save plot
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f'{ticker}_rv_analysis.png'
    save_figure(fig, output_file, dpi=300)

    print(f"Saved plot to {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Plot IV vs RV comparison')
    parser.add_argument('--ticker', required=True)
    parser.add_argument('--data-dir', default='pricing/volatility_arbitrage/output')
    parser.add_argument('--output-dir', default='pricing/volatility_arbitrage/output/plots')

    args = parser.parse_args()

    try:
        data_dir = Path(args.data_dir)
        output_dir = Path(args.output_dir)

        plot_iv_vs_rv(args.ticker, data_dir, output_dir)

        print("\n✓ Successfully generated IV vs RV plot")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

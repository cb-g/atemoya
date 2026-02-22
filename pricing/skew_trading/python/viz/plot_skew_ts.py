#!/usr/bin/env python3
"""
Plot skew time series (RR25, BF25, ATM vol).

Visualizes:
- RR25 (risk reversal) over time
- BF25 (butterfly) over time
- Mean reversion bands
- Trading signals
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure


def setup_dark_style():
    """Configure matplotlib for dark mode."""
    setup_dark_mode()


def plot_skew_timeseries(skew_df: pd.DataFrame, output_file: Path, z_threshold: float = 2.0, ticker: str = ''):
    """
    Plot skew metrics over time.

    Args:
        skew_df: DataFrame with skew observations
        output_file: Output file path
        z_threshold: Z-score threshold for mean reversion bands
    """
    setup_dark_style()

    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 10))

    # Convert timestamps to datetime
    dates = pd.to_datetime(skew_df['timestamp'], unit='s')

    # Plot 1: RR25 (Risk Reversal)
    rr25_pct = skew_df['rr25'] * 100
    mean_rr25 = rr25_pct.mean()
    std_rr25 = rr25_pct.std()

    ax1.plot(dates, rr25_pct, color=COLORS['blue'], linewidth=1.5, label='RR25')
    ax1.axhline(mean_rr25, color=COLORS['fg'], linestyle='--', alpha=0.5, label=f'Mean: {mean_rr25:.2f}%')
    ax1.axhline(mean_rr25 + z_threshold * std_rr25, color=COLORS['red'], linestyle=':', alpha=0.7, label=f'+{z_threshold}σ')
    ax1.axhline(mean_rr25 - z_threshold * std_rr25, color=COLORS['green'], linestyle=':', alpha=0.7, label=f'-{z_threshold}σ')
    ax1.fill_between(dates,
                      mean_rr25 - z_threshold * std_rr25,
                      mean_rr25 + z_threshold * std_rr25,
                      alpha=0.1, color=COLORS['fg'])

    ax1.set_ylabel('RR25 (%)')
    ax1.set_title('25-Delta Risk Reversal (Call IV - Put IV)')
    ax1.legend(loc='best', fontsize=8)
    ax1.grid(True, alpha=0.2)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    # Plot 2: BF25 (Butterfly)
    bf25_pct = skew_df['bf25'] * 100
    mean_bf25 = bf25_pct.mean()
    std_bf25 = bf25_pct.std()

    ax2.plot(dates, bf25_pct, color=COLORS['cyan'], linewidth=1.5, label='BF25')
    ax2.axhline(mean_bf25, color=COLORS['fg'], linestyle='--', alpha=0.5, label=f'Mean: {mean_bf25:.2f}%')
    ax2.axhline(mean_bf25 + z_threshold * std_bf25, color=COLORS['red'], linestyle=':', alpha=0.7)
    ax2.axhline(mean_bf25 - z_threshold * std_bf25, color=COLORS['green'], linestyle=':', alpha=0.7)
    ax2.fill_between(dates,
                      mean_bf25 - z_threshold * std_bf25,
                      mean_bf25 + z_threshold * std_bf25,
                      alpha=0.1, color=COLORS['fg'])

    ax2.set_ylabel('BF25 (%)')
    ax2.set_title('25-Delta Butterfly (Wing Avg - ATM)')
    ax2.legend(loc='best', fontsize=8)
    ax2.grid(True, alpha=0.2)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    # Plot 3: ATM Volatility
    atm_vol_pct = skew_df['atm_vol'] * 100

    ax3.plot(dates, atm_vol_pct, color=COLORS['green'], linewidth=1.5, label='ATM Vol')
    ax3.axhline(atm_vol_pct.mean(), color=COLORS['fg'], linestyle='--', alpha=0.5,
                label=f'Mean: {atm_vol_pct.mean():.2f}%')

    ax3.set_ylabel('ATM Implied Vol (%)')
    ax3.set_title('At-The-Money Volatility')
    ax3.legend(loc='best', fontsize=8)
    ax3.grid(True, alpha=0.2)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    # Plot 4: RR25 Z-Score (for signal generation)
    z_scores = (rr25_pct - mean_rr25) / std_rr25

    ax4.plot(dates, z_scores, color=COLORS['magenta'], linewidth=1.5, label='RR25 Z-Score')
    ax4.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.3)
    ax4.axhline(z_threshold, color=COLORS['red'], linestyle='--', alpha=0.7, label=f'Long Threshold (+{z_threshold})')
    ax4.axhline(-z_threshold, color=COLORS['green'], linestyle='--', alpha=0.7, label=f'Short Threshold (-{z_threshold})')
    ax4.fill_between(dates, -z_threshold, z_threshold, alpha=0.1, color=COLORS['fg'], label='Neutral Zone')

    ax4.set_ylabel('Z-Score')
    ax4.set_title('RR25 Z-Score (Mean Reversion Signal)')
    ax4.legend(loc='best', fontsize=8)
    ax4.grid(True, alpha=0.2)
    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    if ticker:
        fig.suptitle(f'{ticker} — Skew Time Series', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    plt.close()

    print(f"✓ Saved skew timeseries plot: {output_file}")


def load_skew_timeseries(ticker: str, data_dir: Path) -> pd.DataFrame:
    """Load skew timeseries from CSV."""
    skew_file = data_dir / f"{ticker}_skew_timeseries.csv"

    if not skew_file.exists():
        raise FileNotFoundError(f"Skew timeseries file not found: {skew_file}")

    df = pd.read_csv(skew_file)
    print(f"Loaded {len(df)} skew observations")

    return df


def main():
    parser = argparse.ArgumentParser(description='Plot skew time series')
    parser.add_argument('--ticker', type=str, required=True,
                        help='Stock ticker symbol')
    parser.add_argument('--data-dir', type=str, default='pricing/skew_trading/data',
                        help='Data directory')
    parser.add_argument('--output-dir', type=str, default='pricing/skew_trading/output',
                        help='Output directory for plots')
    parser.add_argument('--z-threshold', type=float, default=2.0,
                        help='Z-score threshold for mean reversion bands (default: 2.0)')

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    skew_df = load_skew_timeseries(args.ticker, data_dir)

    # Plot
    output_file = output_dir / f"{args.ticker}_skew_timeseries.png"
    plot_skew_timeseries(skew_df, output_file, args.z_threshold, ticker=args.ticker)

    return 0


if __name__ == '__main__':
    exit(main())

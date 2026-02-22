#!/usr/bin/env python3
"""
Plot backtest P&L from skew trading strategy.

Visualizes:
- Cumulative P&L over time
- Rolling Sharpe ratio
- Drawdown analysis
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


def compute_drawdown(cumulative_pnl: pd.Series) -> pd.Series:
    """Compute drawdown from cumulative P&L."""
    running_max = cumulative_pnl.expanding().max()
    drawdown = cumulative_pnl - running_max
    return drawdown


def plot_backtest_pnl(pnl_df: pd.DataFrame, ticker: str, output_file: Path):
    """
    Plot backtest results.

    Args:
        pnl_df: DataFrame with backtest P&L
        ticker: Stock ticker
        output_file: Output file path
    """
    setup_dark_style()

    fig, axes = plt.subplots(3, 2, figsize=(16, 14))
    ((ax1, ax2), (ax3, ax4), (ax5, ax6)) = axes

    # Convert timestamps to datetime
    dates = pd.to_datetime(pnl_df['timestamp'], unit='s')

    # Plot 1: Cumulative P&L
    cumulative_pnl = pnl_df['cumulative_pnl']

    ax1.plot(dates, cumulative_pnl, color=COLORS['blue'], linewidth=2, label='Cumulative P&L')
    ax1.axhline(0, color=COLORS['fg'], linestyle='--', alpha=0.5)
    ax1.fill_between(dates, 0, cumulative_pnl,
                      where=(cumulative_pnl >= 0),
                      alpha=0.3, color=COLORS['green'], label='Profit')
    ax1.fill_between(dates, 0, cumulative_pnl,
                      where=(cumulative_pnl < 0),
                      alpha=0.3, color=COLORS['red'], label='Loss')

    final_pnl = cumulative_pnl.iloc[-1]
    ax1.set_ylabel('Cumulative P&L ($)')
    ax1.set_title(f'Backtest P&L - {ticker} (Final: ${final_pnl:,.2f})')
    ax1.legend(loc='best', fontsize=8)
    ax1.grid(True, alpha=0.2)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    # Plot 2: Rolling Sharpe Ratio
    sharpe_ratios = pnl_df['sharpe_ratio'].dropna()
    sharpe_dates = dates[pnl_df['sharpe_ratio'].notna()]

    if len(sharpe_ratios) > 0:
        ax2.plot(sharpe_dates, sharpe_ratios, color=COLORS['cyan'], linewidth=2, label='60-Day Sharpe')
        ax2.axhline(0, color=COLORS['fg'], linestyle='--', alpha=0.5)
        ax2.axhline(1.0, color=COLORS['green'], linestyle=':', alpha=0.7, label='Sharpe = 1.0')
        ax2.fill_between(sharpe_dates, 0, sharpe_ratios,
                          where=(sharpe_ratios >= 0),
                          alpha=0.2, color=COLORS['green'])

        final_sharpe = sharpe_ratios.iloc[-1]
        ax2.set_ylabel('Sharpe Ratio')
        ax2.set_title(f'Rolling 60-Day Sharpe Ratio (Final: {final_sharpe:.2f})')
        ax2.legend(loc='best', fontsize=8)
    else:
        ax2.text(0.5, 0.5, 'Insufficient data for Sharpe calculation',
                 ha='center', va='center', transform=ax2.transAxes,
                 fontsize=10, color=COLORS['fg'])
        ax2.set_title('Rolling Sharpe Ratio')

    ax2.grid(True, alpha=0.2)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    # Plot 3: Drawdown
    drawdown = compute_drawdown(cumulative_pnl)
    max_drawdown = drawdown.min()

    ax3.fill_between(dates, 0, drawdown, alpha=0.5, color=COLORS['red'], label='Drawdown')
    ax3.plot(dates, drawdown, color=COLORS['red'], linewidth=1.5)
    ax3.axhline(max_drawdown, color=COLORS['fg'], linestyle='--', alpha=0.7,
                label=f'Max DD: ${max_drawdown:,.2f}')

    ax3.set_ylabel('Drawdown ($)')
    ax3.set_title(f'Drawdown Analysis (Max: ${max_drawdown:,.2f})')
    ax3.legend(loc='best', fontsize=8)
    ax3.grid(True, alpha=0.2)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    # Plot 4: Rolling Sortino Ratio
    sortino_ratios = pnl_df['sortino_ratio'].dropna()
    sortino_dates = dates[pnl_df['sortino_ratio'].notna()]

    if len(sortino_ratios) > 0:
        ax4.plot(sortino_dates, sortino_ratios, color=COLORS['magenta'], linewidth=2, label='60-Day Sortino')
        ax4.axhline(0, color=COLORS['fg'], linestyle='--', alpha=0.5)
        ax4.axhline(1.0, color=COLORS['green'], linestyle=':', alpha=0.7, label='Sortino = 1.0')
        ax4.fill_between(sortino_dates, 0, sortino_ratios,
                          where=(sortino_ratios >= 0),
                          alpha=0.2, color=COLORS['magenta'])

        final_sortino = sortino_ratios.iloc[-1]
        ax4.set_ylabel('Sortino Ratio')
        ax4.set_title(f'Rolling 60-Day Sortino Ratio (Final: {final_sortino:.2f})')
        ax4.legend(loc='best', fontsize=8)
    else:
        ax4.text(0.5, 0.5, 'Insufficient data for Sortino calculation',
                 ha='center', va='center', transform=ax4.transAxes,
                 fontsize=10, color=COLORS['fg'])
        ax4.set_title('Rolling Sortino Ratio')

    ax4.grid(True, alpha=0.2)
    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    # Plot 5: Rolling Return Skewness
    skewness = pnl_df['return_skewness'].dropna()
    skewness_dates = dates[pnl_df['return_skewness'].notna()]

    if len(skewness) > 0:
        ax5.plot(skewness_dates, skewness, color=COLORS['orange'], linewidth=2, label='60-Day Skewness')
        ax5.axhline(0, color=COLORS['fg'], linestyle='--', alpha=0.5)
        ax5.fill_between(skewness_dates, 0, skewness,
                          where=(skewness >= 0),
                          alpha=0.2, color=COLORS['green'])
        ax5.fill_between(skewness_dates, 0, skewness,
                          where=(skewness < 0),
                          alpha=0.2, color=COLORS['red'])

        final_skewness = skewness.iloc[-1]
        ax5.set_ylabel('Skewness')
        ax5.set_title(f'Rolling 60-Day Return Skewness (Final: {final_skewness:.2f})')
        ax5.legend(loc='best', fontsize=8)
    else:
        ax5.text(0.5, 0.5, 'Insufficient data for skewness calculation',
                 ha='center', va='center', transform=ax5.transAxes,
                 fontsize=10, color=COLORS['fg'])
        ax5.set_title('Rolling Return Skewness')

    ax5.grid(True, alpha=0.2)
    ax5.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    # Plot 6: Daily P&L (mark-to-market)
    daily_pnl = pnl_df['mark_to_market']

    colors_pnl = [COLORS['green'] if p >= 0 else COLORS['red'] for p in daily_pnl]
    ax6.bar(dates, daily_pnl, color=colors_pnl, alpha=0.7, width=1.0)
    ax6.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.5)

    ax6.set_ylabel('Daily P&L ($)')
    ax6.set_title('Daily Mark-to-Market P&L')
    ax6.grid(True, alpha=0.2)
    ax6.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    plt.close()

    print(f"✓ Saved backtest P&L plot: {output_file}")

    # Print summary statistics
    print("\n=== Backtest Summary ===")
    print(f"Final P&L: ${final_pnl:,.2f}")
    print(f"Max Drawdown: ${max_drawdown:,.2f}")

    if len(sharpe_ratios) > 0:
        print(f"Final Sharpe: {final_sharpe:.2f}")

    if len(sortino_ratios) > 0:
        print(f"Final Sortino: {final_sortino:.2f}")

    if len(skewness) > 0:
        print(f"Final Return Skewness: {final_skewness:.2f}")

    win_days = (daily_pnl > 0).sum()
    total_days = len(daily_pnl[daily_pnl != 0])
    if total_days > 0:
        win_rate = win_days / total_days * 100
        print(f"Win Rate: {win_rate:.1f}% ({win_days}/{total_days} days)")


def load_pnl_data(ticker: str, data_dir: Path) -> pd.DataFrame:
    """Load backtest P&L from CSV."""
    pnl_file = data_dir / f"{ticker}_backtest.csv"

    if not pnl_file.exists():
        raise FileNotFoundError(f"Backtest P&L file not found: {pnl_file}")

    df = pd.read_csv(pnl_file)
    print(f"Loaded {len(df)} P&L observations")

    # Handle empty optional metric strings
    for col in ['sharpe_ratio', 'max_drawdown', 'sortino_ratio', 'return_skewness']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def main():
    parser = argparse.ArgumentParser(description='Plot backtest P&L')
    parser.add_argument('--ticker', type=str, required=True,
                        help='Stock ticker symbol')
    parser.add_argument('--data-dir', type=str, default='pricing/skew_trading/output',
                        help='Data directory (default: pricing/skew_trading/output)')
    parser.add_argument('--output-dir', type=str, default='pricing/skew_trading/output',
                        help='Output directory for plots')

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    pnl_df = load_pnl_data(args.ticker, data_dir)

    # Plot
    output_file = output_dir / f"{args.ticker}_backtest_pnl.png"
    plot_backtest_pnl(pnl_df, args.ticker, output_file)

    return 0


if __name__ == '__main__':
    exit(main())

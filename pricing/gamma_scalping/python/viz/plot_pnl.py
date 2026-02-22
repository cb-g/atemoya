#!/usr/bin/env python3
"""
Visualize gamma scalping P&L attribution and results.

This script creates comprehensive visualization of:
1. Cumulative P&L over time
2. P&L attribution breakdown (gamma, theta, vega)
3. Spot price evolution with hedge markers
4. Greeks evolution over time

Usage:
    uv run pricing/gamma_scalping/python/viz/plot_pnl.py --ticker SPY
    uv run pricing/gamma_scalping/python/viz/plot_pnl.py --ticker SPY --output-dir pricing/gamma_scalping/output/plots
"""

import argparse
import sys
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

# Apply dark theme
setup_dark_mode()

def load_simulation_data(ticker: str, data_dir: str = "pricing/gamma_scalping/output"):
    """
    Load simulation results from CSV files.

    Args:
        ticker: Stock ticker symbol
        data_dir: Directory containing simulation output

    Returns:
        Tuple of (summary_df, pnl_df, hedge_df)
    """
    summary_file = f"{data_dir}/{ticker}_simulation.csv"
    pnl_file = f"{data_dir}/{ticker}_pnl_attribution.csv"
    hedge_file = f"{data_dir}/{ticker}_hedge_log.csv"

    # Load files
    summary = pd.read_csv(summary_file)
    pnl = pd.read_csv(pnl_file)
    hedge = pd.read_csv(hedge_file)

    print(f"Loaded simulation data for {ticker}:")
    print(f"  P&L timeseries: {len(pnl)} observations")
    print(f"  Hedge events: {len(hedge)} hedges")

    return summary, pnl, hedge

def plot_pnl_attribution(ticker: str, summary: pd.DataFrame, pnl: pd.DataFrame, hedge: pd.DataFrame,
                         output_dir: str = "pricing/gamma_scalping/output/plots"):
    """
    Create comprehensive P&L attribution visualization.

    4-panel plot:
    1. Cumulative P&L and components
    2. P&L attribution breakdown (stacked area)
    3. Spot price with hedge markers
    4. Transaction costs accumulation
    """
    # Create figure with 4 subplots
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.patch.set_facecolor(COLORS['bg'])
    for ax in axes.flat:
        ax.set_facecolor(COLORS['bg'])
    fig.suptitle(f"Gamma Scalping Analysis: {ticker}", fontsize=16, fontweight='bold', color=COLORS['fg'])

    # Convert timestamp to hours for x-axis
    pnl['time_hours'] = pnl['timestamp'] * 24

    # Panel 1: Cumulative P&L
    ax1 = axes[0, 0]
    ax1.plot(pnl['time_hours'], pnl['cumulative_pnl'], linewidth=2.5, color=COLORS['blue'], label='Total P&L')
    ax1.axhline(y=0, color=COLORS['gray'], linestyle='--', alpha=0.5)
    ax1.fill_between(pnl['time_hours'], 0, pnl['cumulative_pnl'],
                      where=pnl['cumulative_pnl'] >= 0, alpha=0.3, color=COLORS['green'], label='Profit')
    ax1.fill_between(pnl['time_hours'], 0, pnl['cumulative_pnl'],
                      where=pnl['cumulative_pnl'] < 0, alpha=0.3, color=COLORS['red'], label='Loss')
    ax1.set_xlabel('Time (hours)', fontsize=11, color=COLORS['fg'])
    ax1.set_ylabel('Cumulative P&L ($)', fontsize=11, color=COLORS['fg'])
    ax1.set_title('Cumulative P&L Over Time', fontsize=12, fontweight='bold', color=COLORS['fg'])
    ax1.legend(loc='best')
    ax1.grid(True, alpha=0.2, color=COLORS['gray'])
    ax1.tick_params(colors=COLORS['fg'])

    # Panel 2: P&L Attribution Breakdown (Stacked Area)
    ax2 = axes[0, 1]

    # Stack positive and negative components separately
    gamma_pnl = pnl['gamma_pnl'].values
    theta_pnl = pnl['theta_pnl'].values
    vega_pnl = pnl['vega_pnl'].values

    # Create stacked area chart
    ax2.fill_between(pnl['time_hours'], 0, gamma_pnl, alpha=0.7, color=COLORS['green'], label='Gamma P&L')
    ax2.fill_between(pnl['time_hours'], gamma_pnl, gamma_pnl + theta_pnl,
                      alpha=0.7, color=COLORS['red'], label='Theta P&L')
    ax2.fill_between(pnl['time_hours'], gamma_pnl + theta_pnl, gamma_pnl + theta_pnl + vega_pnl,
                      alpha=0.7, color=COLORS['yellow'], label='Vega P&L')

    # Plot net P&L line
    ax2.plot(pnl['time_hours'], pnl['total_pnl'], linewidth=2.5, color=COLORS['fg'], label='Net P&L', alpha=0.9)
    ax2.axhline(y=0, color=COLORS['gray'], linestyle='--', alpha=0.5)

    ax2.set_xlabel('Time (hours)', fontsize=11, color=COLORS['fg'])
    ax2.set_ylabel('P&L ($)', fontsize=11, color=COLORS['fg'])
    ax2.set_title('P&L Attribution Breakdown', fontsize=12, fontweight='bold', color=COLORS['fg'])
    ax2.legend(loc='best', fontsize=9)
    ax2.grid(True, alpha=0.2, color=COLORS['gray'])
    ax2.tick_params(colors=COLORS['fg'])

    # Panel 3: Spot Price with Hedge Markers
    ax3 = axes[1, 0]
    ax3.plot(pnl['time_hours'], pnl['spot_price'], linewidth=2, color=COLORS['cyan'], label='Spot Price')

    # Add hedge markers
    if len(hedge) > 0:
        hedge['time_hours'] = hedge['timestamp'] * 24
        ax3.scatter(hedge['time_hours'], hedge['spot_price'], color=COLORS['orange'], s=50, alpha=0.8,
                    marker='v', label=f'Hedge Events (n={len(hedge)})', zorder=5, edgecolors=COLORS['fg'])

    ax3.set_xlabel('Time (hours)', fontsize=11, color=COLORS['fg'])
    ax3.set_ylabel('Spot Price ($)', fontsize=11, color=COLORS['fg'])
    ax3.set_title('Spot Price Evolution & Hedge Timing', fontsize=12, fontweight='bold', color=COLORS['fg'])
    ax3.legend(loc='best')
    ax3.grid(True, alpha=0.2, color=COLORS['gray'])
    ax3.tick_params(colors=COLORS['fg'])

    # Panel 4: Transaction Costs Accumulation
    ax4 = axes[1, 1]
    ax4.plot(pnl['time_hours'], pnl['transaction_costs'], linewidth=2, color=COLORS['red'], label='Transaction Costs')
    ax4.fill_between(pnl['time_hours'], 0, pnl['transaction_costs'], alpha=0.3, color=COLORS['red'])

    # Add hedge markers
    if len(hedge) > 0:
        ax4.scatter(hedge['time_hours'], hedge['hedge_cost'].cumsum(), color=COLORS['orange'], s=30,
                    alpha=0.8, marker='o', label='Hedge Events', zorder=5, edgecolors=COLORS['fg'])

    ax4.set_xlabel('Time (hours)', fontsize=11, color=COLORS['fg'])
    ax4.set_ylabel('Cumulative Costs ($)', fontsize=11, color=COLORS['fg'])
    ax4.set_title('Transaction Costs Accumulation', fontsize=12, fontweight='bold', color=COLORS['fg'])
    ax4.legend(loc='best')
    ax4.grid(True, alpha=0.2, color=COLORS['gray'])
    ax4.tick_params(colors=COLORS['fg'])

    plt.tight_layout()

    # Save plot
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_dir}/{ticker}_pnl_attribution.png"
    save_figure(fig, output_file, dpi=300)
    print(f"  Saved: {output_file}")

    svg_file = f"{output_dir}/{ticker}_pnl_attribution.svg"
    save_figure(fig, svg_file)
    print(f"  Saved: {svg_file}")

    plt.close()

def plot_summary_metrics(ticker: str, summary: pd.DataFrame, pnl: pd.DataFrame,
                         output_dir: str = "pricing/gamma_scalping/output/plots"):
    """
    Create summary metrics visualization.
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor(COLORS['bg'])
    for ax in axes:
        ax.set_facecolor(COLORS['bg'])
    fig.suptitle(f"Performance Metrics: {ticker}", fontsize=14, fontweight='bold', color=COLORS['fg'])

    # Parse summary metrics
    metrics = dict(zip(summary['metric'], summary['value']))

    # Panel 1: P&L Breakdown (Bar Chart)
    ax1 = axes[0]
    components = ['gamma_pnl_total', 'theta_pnl_total', 'vega_pnl_total', 'total_transaction_costs']
    labels = ['Gamma P&L', 'Theta P&L', 'Vega P&L', 'Transaction Costs']
    values = [float(metrics.get(c, 0)) for c in components]
    bar_colors = [COLORS['green'], COLORS['red'], COLORS['yellow'], COLORS['orange']]

    bars = ax1.bar(labels, values, color=bar_colors, alpha=0.8, edgecolor=COLORS['fg'], linewidth=1.5)

    # Add value labels on bars
    for bar, val in zip(bars, values):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'${val:.2f}', ha='center', va='bottom' if val >= 0 else 'top',
                fontsize=10, color=COLORS['fg'], fontweight='bold')

    ax1.axhline(y=0, color=COLORS['gray'], linestyle='-', linewidth=1)
    ax1.set_ylabel('P&L ($)', fontsize=11, color=COLORS['fg'])
    ax1.set_title('P&L Component Breakdown', fontsize=12, fontweight='bold', color=COLORS['fg'])
    ax1.tick_params(axis='x', rotation=15, colors=COLORS['fg'])
    ax1.tick_params(axis='y', colors=COLORS['fg'])
    ax1.grid(True, alpha=0.2, axis='y', color=COLORS['gray'])

    # Panel 2: Key Metrics Table
    ax2 = axes[1]
    ax2.axis('off')

    # Extract key metrics
    final_pnl = float(metrics.get('final_pnl', 0))
    sharpe = metrics.get('sharpe_ratio', 'N/A')
    max_dd = float(metrics.get('max_drawdown', 0)) * 100
    win_rate = float(metrics.get('win_rate', 0)) * 100
    num_hedges = int(float(metrics.get('num_hedges', 0)))
    avg_interval = float(metrics.get('avg_hedge_interval_minutes', 0))
    entry_premium = float(metrics.get('entry_premium', 0))

    # Create table
    table_data = [
        ['Final P&L', f'${final_pnl:.2f}'],
        ['Entry Premium', f'${entry_premium:.2f}'],
        ['Return', f'{(final_pnl / entry_premium * 100):.2f}%' if entry_premium > 0 else 'N/A'],
        ['Sharpe Ratio', f'{sharpe}' if sharpe != 'N/A' else 'N/A'],
        ['Max Drawdown', f'{max_dd:.2f}%'],
        ['Win Rate', f'{win_rate:.2f}%'],
        ['Num Hedges', f'{num_hedges}'],
        ['Avg Hedge Interval', f'{avg_interval:.1f} min'],
    ]

    table = ax2.table(cellText=table_data, cellLoc='left',
                      colWidths=[0.5, 0.5], loc='center',
                      bbox=[0.1, 0.1, 0.8, 0.8])

    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 2)

    # Style table with Kanagawa colors
    for i in range(len(table_data)):
        table[(i, 0)].set_facecolor(COLORS['gray'])
        table[(i, 1)].set_facecolor(COLORS['bg'])
        table[(i, 0)].set_text_props(weight='bold', color=COLORS['fg'])
        table[(i, 1)].set_text_props(color=COLORS['fg'])
        table[(i, 0)].set_edgecolor(COLORS['fg'])
        table[(i, 1)].set_edgecolor(COLORS['fg'])

    ax2.set_title('Summary Statistics', fontsize=12, fontweight='bold', pad=20, color=COLORS['fg'])

    plt.tight_layout()

    # Save plot
    output_file = f"{output_dir}/{ticker}_summary_metrics.png"
    save_figure(fig, output_file, dpi=300)
    print(f"  Saved: {output_file}")

    svg_file = f"{output_dir}/{ticker}_summary_metrics.svg"
    save_figure(fig, svg_file)
    print(f"  Saved: {svg_file}")

    plt.close()

def main():
    parser = argparse.ArgumentParser(
        description="Visualize gamma scalping P&L attribution and results"
    )

    parser.add_argument("--ticker", type=str, required=True, help="Stock ticker symbol (e.g., SPY)")
    parser.add_argument("--data-dir", type=str, default="pricing/gamma_scalping/output",
                       help="Input directory with simulation results (default: pricing/gamma_scalping/output)")
    parser.add_argument("--output-dir", type=str, default="pricing/gamma_scalping/output/plots",
                       help="Output directory for plots (default: pricing/gamma_scalping/output/plots)")

    args = parser.parse_args()

    try:
        print(f"Creating visualizations for {args.ticker}...")

        # Load data
        summary, pnl, hedge = load_simulation_data(args.ticker, args.data_dir)

        # Create plots
        plot_pnl_attribution(args.ticker, summary, pnl, hedge, args.output_dir)
        plot_summary_metrics(args.ticker, summary, pnl, args.output_dir)

        print(f"\n✓ Visualizations created successfully")
        print(f"  Output directory: {args.output_dir}")

    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

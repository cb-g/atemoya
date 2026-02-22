#!/usr/bin/env python3
"""
Visualize backtest results and compare to claimed performance.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

# Set style
setup_dark_mode()
plt.rcParams['figure.figsize'] = (14, 10)

def plot_backtest_results(results_file: Path, output_dir: Path, structure: str):
    """Generate comprehensive backtest visualization."""

    # Load results
    df = pd.read_csv(results_file)

    # Filter to trades that passed filters
    trades = df[df['passed_filters'] == True].copy()

    if len(trades) == 0:
        print("⚠ No trades passed filters!")
        return

    print(f"\nAnalyzing {len(trades)} trades that passed filters...")

    # Calculate statistics
    win_rate = (trades['return_pct'] > 0).mean()
    mean_return = trades['return_pct'].mean()
    std_dev = trades['return_pct'].std()
    sharpe = (mean_return * np.sqrt(10)) / std_dev if std_dev > 0 else 0  # Assume ~10 trades/year

    # Equity curve
    trades = trades.sort_values('earnings_date')
    trades['equity'] = (1 + trades['return_pct']).cumprod()
    trades['drawdown'] = trades['equity'] / trades['equity'].cummax() - 1

    max_dd = trades['drawdown'].min()

    # Claimed performance (from video)
    if structure.lower() == 'calendar':
        claimed_win_rate = 0.66
        claimed_mean_return = 0.073
        claimed_std = 0.28
        claimed_sharpe = 3.5
        claimed_max_dd = -0.20
    else:  # straddle
        claimed_win_rate = 0.66
        claimed_mean_return = 0.09
        claimed_std = 0.48
        claimed_sharpe = 3.5  # Not specified, using same
        claimed_max_dd = -0.30  # Estimate

    # Create figure
    fig = plt.figure(figsize=(16, 12))

    # 1. Equity curve
    ax1 = plt.subplot(3, 2, 1)
    ax1.plot(range(len(trades)), trades['equity'].values, linewidth=2, color='#2E86AB')
    ax1.axhline(y=1, color='gray', linestyle='--', alpha=0.5)
    ax1.set_title('Cumulative Equity Curve', fontsize=14, fontweight='bold')
    ax1.set_xlabel('Trade Number')
    ax1.set_ylabel('Equity Multiple')
    ax1.grid(True, alpha=0.3)

    # Final equity
    final_equity = trades['equity'].iloc[-1]
    ax1.text(0.02, 0.98, f'Final Equity: {final_equity:.2f}x',
             transform=ax1.transAxes, fontsize=11,
             verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    # 2. Drawdown
    ax2 = plt.subplot(3, 2, 2)
    ax2.fill_between(range(len(trades)), trades['drawdown'].values * 100, 0,
                      color='#A23B72', alpha=0.6)
    ax2.set_title('Drawdown', fontsize=14, fontweight='bold')
    ax2.set_xlabel('Trade Number')
    ax2.set_ylabel('Drawdown (%)')
    ax2.grid(True, alpha=0.3)
    ax2.text(0.02, 0.02, f'Max DD: {max_dd*100:.1f}%',
             transform=ax2.transAxes, fontsize=11,
             verticalalignment='bottom',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    # 3. Return distribution
    ax3 = plt.subplot(3, 2, 3)
    ax3.hist(trades['return_pct'] * 100, bins=30, color='#18A558', alpha=0.7, edgecolor='black')
    ax3.axvline(x=0, color='red', linestyle='--', linewidth=2)
    ax3.axvline(x=mean_return * 100, color='blue', linestyle='--', linewidth=2, label=f'Mean: {mean_return*100:.1f}%')
    ax3.set_title('Return Distribution', fontsize=14, fontweight='bold')
    ax3.set_xlabel('Return (%)')
    ax3.set_ylabel('Frequency')
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # 4. Win/Loss analysis
    ax4 = plt.subplot(3, 2, 4)
    win_loss_data = [
        len(trades[trades['return_pct'] > 0]),
        len(trades[trades['return_pct'] <= 0])
    ]
    colors = ['#18A558', '#A23B72']
    ax4.bar(['Wins', 'Losses'], win_loss_data, color=colors, alpha=0.7, edgecolor='black')
    ax4.set_title('Win/Loss Count', fontsize=14, fontweight='bold')
    ax4.set_ylabel('Number of Trades')
    ax4.grid(True, alpha=0.3, axis='y')

    # Add percentages on bars
    for i, v in enumerate(win_loss_data):
        pct = v / len(trades) * 100
        ax4.text(i, v, f'{v}\n({pct:.1f}%)', ha='center', va='bottom', fontweight='bold')

    # 5. Actual vs Claimed Performance
    ax5 = plt.subplot(3, 2, 5)
    metrics = ['Win Rate', 'Mean Return', 'Std Dev', 'Sharpe', 'Max DD']
    actual_values = [
        win_rate * 100,
        mean_return * 100,
        std_dev * 100,
        sharpe,
        abs(max_dd) * 100
    ]
    claimed_values = [
        claimed_win_rate * 100,
        claimed_mean_return * 100,
        claimed_std * 100,
        claimed_sharpe,
        abs(claimed_max_dd) * 100
    ]

    x = np.arange(len(metrics))
    width = 0.35

    ax5.bar(x - width/2, actual_values, width, label='Our Backtest', color='#2E86AB', alpha=0.8)
    ax5.bar(x + width/2, claimed_values, width, label='Claimed (Video)', color='#F18F01', alpha=0.8)

    ax5.set_title('Performance: Actual vs Claimed', fontsize=14, fontweight='bold')
    ax5.set_xticks(x)
    ax5.set_xticklabels(metrics, rotation=45, ha='right')
    ax5.legend()
    ax5.grid(True, alpha=0.3, axis='y')

    # 6. Statistics summary
    ax6 = plt.subplot(3, 2, 6)
    ax6.axis('off')

    stats_text = f"""
    === BACKTEST RESULTS ===

    Structure: {structure.upper()}
    Total Trades: {len(trades)}

    Win Rate: {win_rate*100:.1f}% (claimed: {claimed_win_rate*100:.1f}%)
    Mean Return: {mean_return*100:.2f}% (claimed: {claimed_mean_return*100:.1f}%)
    Std Dev: {std_dev*100:.2f}% (claimed: {claimed_std*100:.1f}%)
    Sharpe Ratio: {sharpe:.2f} (claimed: {claimed_sharpe:.1f})
    Max Drawdown: {max_dd*100:.1f}% (claimed: {claimed_max_dd*100:.1f}%)

    Final Equity: {final_equity:.2f}x
    Total Return: {(final_equity-1)*100:.1f}%

    === VERDICT ===
    {'✓ MATCHES' if abs(win_rate - claimed_win_rate) < 0.1 else '✗ DIFFERS'}
    """

    ax6.text(0.1, 0.9, stats_text, transform=ax6.transAxes,
             fontsize=11, verticalalignment='top',
             fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))

    plt.suptitle(f'Earnings Volatility Backtest Analysis - {structure.upper()}',
                 fontsize=16, fontweight='bold', y=0.995)

    plt.tight_layout()

    # Save
    output_file = output_dir / f'backtest_analysis_{structure}.png'
    save_figure(fig, output_file, dpi=300)
    print(f"✓ Saved: {output_file}")

    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Visualize backtest results')
    parser.add_argument('--results', type=str,
                       default='pricing/earnings_vol/data/backtest/backtest_results.csv',
                       help='Backtest results CSV')
    parser.add_argument('--output-dir', type=str,
                       default='pricing/earnings_vol/output',
                       help='Output directory for plots')
    parser.add_argument('--structure', type=str, default='calendar',
                       help='Structure type (calendar or straddle)')

    args = parser.parse_args()

    results_file = Path(args.results)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not results_file.exists():
        print(f"✗ Results file not found: {results_file}")
        return

    plot_backtest_results(results_file, output_dir, args.structure)

    print(f"\n✅ Backtest visualization complete")

if __name__ == "__main__":
    main()

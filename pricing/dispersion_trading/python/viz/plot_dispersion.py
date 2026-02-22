#!/usr/bin/env python3
"""
Visualize dispersion trading metrics.
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

setup_dark_mode()

def plot_dispersion_metrics():
    """Plot dispersion and correlation metrics."""

    # Load data
    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    index_df = pd.read_csv(data_dir / "index_data.csv")
    constituents_df = pd.read_csv(data_dir / "constituents_data.csv")

    # Calculate metrics
    index_iv = index_df['implied_vol'].values[0]
    weighted_avg_iv = (constituents_df['implied_vol'] * constituents_df['weight']).sum()
    dispersion = weighted_avg_iv - index_iv

    # Create figure
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.patch.set_facecolor(COLORS['bg'])

    # 1. IV Comparison
    ax1 = axes[0, 0]
    ax1.set_facecolor(COLORS['bg'])

    tickers = ['Index'] + constituents_df['ticker'].tolist()
    ivs = [index_iv] + constituents_df['implied_vol'].tolist()
    colors_list = [COLORS['red']] + [COLORS['blue']] * len(constituents_df)

    ax1.bar(tickers, np.array(ivs) * 100, color=colors_list, alpha=0.8)
    ax1.axhline(y=weighted_avg_iv * 100, color=COLORS['yellow'],
                linestyle='--', linewidth=2, label='Weighted Avg')
    ax1.set_ylabel('Implied Volatility (%)', color=COLORS['fg'])
    ax1.set_title('Implied Volatility Comparison', fontweight='bold', color=COLORS['fg'])
    ax1.legend(facecolor=COLORS['bg'], edgecolor=COLORS['gray'])
    ax1.tick_params(colors=COLORS['fg'])
    ax1.grid(True, alpha=0.2, color=COLORS['gray'])

    # 2. Dispersion Level
    ax2 = axes[0, 1]
    ax2.set_facecolor(COLORS['bg'])

    metrics = ['Index IV', 'Weighted\nAvg IV', 'Dispersion']
    values = [index_iv * 100, weighted_avg_iv * 100, dispersion * 100]
    bar_colors = [COLORS['red'], COLORS['blue'], COLORS['green'] if dispersion > 0 else COLORS['orange']]

    ax2.bar(metrics, values, color=bar_colors, alpha=0.8)
    ax2.set_ylabel('Volatility (%)', color=COLORS['fg'])
    ax2.set_title('Dispersion Metrics', fontweight='bold', color=COLORS['fg'])
    ax2.tick_params(colors=COLORS['fg'])
    ax2.grid(True, alpha=0.2, color=COLORS['gray'], axis='y')

    # 3. Per-Constituent IV Contribution
    ax3 = axes[1, 0]
    ax3.set_facecolor(COLORS['bg'])

    iv_contrib = (constituents_df['weight'] * constituents_df['implied_vol'] * 100).values
    contrib_tickers = constituents_df['ticker'].values
    sort_idx = np.argsort(iv_contrib)[::-1]
    iv_contrib = iv_contrib[sort_idx]
    contrib_tickers = contrib_tickers[sort_idx]

    ax3.barh(contrib_tickers[::-1], iv_contrib[::-1], color=COLORS['blue'], alpha=0.8)
    ax3.axvline(x=weighted_avg_iv * 100 / len(constituents_df), color=COLORS['yellow'],
                linestyle='--', linewidth=1.5, label='Equal share')
    ax3.set_xlabel('IV Contribution (w × σ, %)', color=COLORS['fg'])
    ax3.set_title('IV Contribution by Constituent', fontweight='bold', color=COLORS['fg'])
    ax3.legend(facecolor=COLORS['bg'], edgecolor=COLORS['gray'])
    ax3.tick_params(colors=COLORS['fg'])
    ax3.grid(True, alpha=0.2, color=COLORS['gray'], axis='x')

    # 4. Trading Signal & Analysis
    ax4 = axes[1, 1]
    ax4.set_facecolor(COLORS['bg'])
    ax4.axis('off')

    # Calculate implied correlation (simplified)
    # ρ ≈ (σ_index / σ_avg)² when weights are equal
    implied_corr = (index_iv / weighted_avg_iv) ** 2 if weighted_avg_iv > 0 else 0

    # Determine signal and build reasoning
    if dispersion > 0.05:
        signal = "LONG DISPERSION"
        signal_color = COLORS['green']
        action = "Buy single-stock straddles, Sell index straddle"
        reasoning = (
            f"Dispersion is wide ({dispersion*100:.1f}%).\n"
            f"Implied correlation is low ({implied_corr*100:.0f}%).\n"
            f"Bet: Stocks will move independently.\n"
            f"Profit if realized corr < implied corr."
        )
        risk = "Risk: Correlated sell-off (risk-on to risk-off)"
    elif dispersion < -0.02:
        signal = "SHORT DISPERSION"
        signal_color = COLORS['red']
        action = "Sell single-stock straddles, Buy index straddle"
        reasoning = (
            f"Dispersion is narrow ({dispersion*100:.1f}%).\n"
            f"Implied correlation is high ({implied_corr*100:.0f}%).\n"
            f"Bet: Stocks will move together.\n"
            f"Profit if realized corr > implied corr."
        )
        risk = "Risk: Stock-specific event (earnings, news)"
    else:
        signal = "NEUTRAL"
        signal_color = COLORS['gray']
        action = "No trade"
        reasoning = (
            f"Dispersion is fair ({dispersion*100:.1f}%).\n"
            f"Implied correlation: {implied_corr*100:.0f}%.\n"
            f"No clear edge detected.\n"
            f"Wait for extreme readings."
        )
        risk = ""

    # Signal header
    ax4.text(0.5, 0.92, signal, ha='center', va='top',
             fontsize=20, fontweight='bold', color=signal_color,
             transform=ax4.transAxes)

    # Action
    ax4.text(0.5, 0.80, action, ha='center', va='top',
             fontsize=11, fontstyle='italic', color=COLORS['fg'],
             transform=ax4.transAxes)

    # Metrics box
    metrics_text = (
        f"Index IV: {index_iv*100:.1f}%\n"
        f"Avg Constituent IV: {weighted_avg_iv*100:.1f}%\n"
        f"Dispersion: {dispersion*100:.1f}%\n"
        f"Implied Correlation: {implied_corr*100:.0f}%"
    )
    ax4.text(0.5, 0.65, metrics_text, ha='center', va='top',
             fontsize=10, family='monospace', color=COLORS['fg'],
             transform=ax4.transAxes,
             bbox=dict(boxstyle='round', facecolor=COLORS['bg_light'],
                      edgecolor=COLORS['gray'], alpha=0.8))

    # Reasoning
    ax4.text(0.5, 0.35, reasoning, ha='center', va='top',
             fontsize=10, color=COLORS['fg'],
             transform=ax4.transAxes)

    # Risk warning
    if risk:
        ax4.text(0.5, 0.08, risk, ha='center', va='top',
                 fontsize=9, color=COLORS['yellow'], fontstyle='italic',
                 transform=ax4.transAxes)

    plt.suptitle('Dispersion Trading Analysis',
                 fontsize=16, fontweight='bold',
                 color=COLORS['fg'], y=0.98)

    plt.tight_layout()

    # Save
    output_dir = Path(__file__).resolve().parent.parent.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "dispersion_analysis.png"

    save_figure(fig, output_file, dpi=300)
    print(f"✓ Saved: {output_file}")

    plt.show()

if __name__ == "__main__":
    plot_dispersion_metrics()

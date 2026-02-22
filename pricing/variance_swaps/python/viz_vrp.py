#!/usr/bin/env python3
"""
Visualize Variance Risk Premium (VRP) analysis
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import sys
from pathlib import Path
import argparse
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

setup_dark_mode()


ESTIMATOR_LABELS = {
    'cc': 'Close-to-Close', 'parkinson': 'Parkinson', 'gk': 'Garman-Klass',
    'rs': 'Rogers-Satchell', 'yz': 'Yang-Zhang',
}
FORECAST_LABELS = {
    'historical': 'Historical RV', 'ewma': 'EWMA', 'garch': 'GARCH(1,1)',
}


def plot_vrp_time_series(vrp_file: Path, output_file: Path, estimator: str = '', forecast: str = ''):
    """Plot VRP time series with implied vs realized variance"""
    print(f"Plotting VRP time series from {vrp_file}...")

    df = pd.read_csv(vrp_file)

    if len(df) == 0:
        print("  ⚠ No VRP data to plot")
        return

    # Trim warm-up artifacts: GARCH/EWMA need ~30 observations to stabilize
    warmup = min(30, len(df) // 4)
    if len(df) > warmup + 10:
        df = df.iloc[warmup:].reset_index(drop=True)

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    # Panel 1: Implied vs Realized Variance
    ax1 = axes[0]
    ax1.plot(df.index, df['implied_var'], color=COLORS['orange'], label='Implied Variance', linewidth=2)
    ax1.plot(df.index, df['forecast_realized_var'], color=COLORS['cyan'], label='Forecast Realized Var', linewidth=2)
    ax1.set_ylabel('Variance', fontsize=12)
    ax1.legend(loc='upper left', fontsize=10)
    ax1.grid(True, alpha=0.3)
    est_label = ESTIMATOR_LABELS.get(estimator, estimator)
    fc_label = FORECAST_LABELS.get(forecast, forecast)
    combo_str = f' ({est_label} + {fc_label})' if est_label and fc_label else ''
    ax1.set_title(f'{df["ticker"].iloc[0]} - Variance Risk Premium Analysis{combo_str}', fontsize=14, pad=15)

    # Panel 2: VRP (absolute)
    ax2 = axes[1]
    vrp_positive = df[df['vrp'] >= 0]
    vrp_negative = df[df['vrp'] < 0]

    ax2.bar(vrp_positive.index, vrp_positive['vrp'], color=COLORS['green'], alpha=0.7, label='Positive VRP')
    ax2.bar(vrp_negative.index, vrp_negative['vrp'], color=COLORS['red'], alpha=0.7, label='Negative VRP')
    ax2.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.5, linewidth=0.8)
    ax2.set_ylabel('VRP (Variance)', fontsize=12)
    ax2.legend(loc='upper left', fontsize=10)
    ax2.grid(True, alpha=0.3)

    # Panel 3: VRP (percentage)
    ax3 = axes[2]
    ax3.plot(df.index, df['vrp_percent'], color=COLORS['purple'], linewidth=2)
    ax3.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.5, linewidth=0.8)
    ax3.axhline(2.0, color=COLORS['green'], linestyle='--', alpha=0.5, label='Short Threshold (+2%)')
    ax3.axhline(-1.0, color=COLORS['red'], linestyle='--', alpha=0.5, label='Long Threshold (-1%)')
    ax3.set_xlabel('Observation', fontsize=12)
    ax3.set_ylabel('VRP (%)', fontsize=12)
    ax3.legend(loc='upper left', fontsize=10)
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    print(f"  ✓ Saved VRP plot to {output_file}")
    plt.close()


def plot_signals(signals_file: Path, output_file: Path, vrp_file: Path = None, swap_file: Path = None,
                 estimator: str = '', forecast: str = ''):
    """Plot trading signals with trade suggestion summary"""
    print(f"Plotting trading signals from {signals_file}...")

    df = pd.read_csv(signals_file)

    if len(df) == 0:
        print("  ⚠ No signals to plot")
        return

    # Load supplementary data for the summary box
    swap_data = None
    if swap_file and swap_file.exists():
        try:
            swap_data = pd.read_csv(swap_file)
        except Exception:
            pass

    vrp_data = None
    if vrp_file and vrp_file.exists():
        try:
            vrp_data = pd.read_csv(vrp_file)
        except Exception:
            pass

    fig, ax = plt.subplots(1, 1, figsize=(14, 7))

    # Build the trade suggestion summary
    row = df.iloc[-1]
    ticker = row['ticker']
    signal_type = row['signal_type']
    confidence = row['confidence']
    position_size = row['position_size']
    reason = row.get('reason', '')
    expected_sharpe = row.get('expected_sharpe', '')

    # Signal color
    if signal_type == 'SHORT':
        sig_color = COLORS['red']
        sig_label = 'SHORT VARIANCE'
        sig_desc = 'Implied vol is rich — sell variance to harvest premium'
    elif signal_type == 'LONG':
        sig_color = COLORS['green']
        sig_label = 'LONG VARIANCE'
        sig_desc = 'Implied vol is cheap — buy variance for mean reversion'
    else:
        sig_color = COLORS['gray']
        sig_label = 'NEUTRAL'
        sig_desc = 'VRP within thresholds — no position warranted'

    # Build summary text
    lines = []
    lines.append(f'SIGNAL:  {sig_label}')
    lines.append(f'')
    lines.append(f'Confidence:     {confidence:.0%}')
    lines.append(f'Position Size:  ${position_size:,.0f} vega notional')
    if expected_sharpe and str(expected_sharpe).strip():
        try:
            lines.append(f'Expected Sharpe: {float(expected_sharpe):.1f}')
        except (ValueError, TypeError):
            pass
    lines.append(f'')

    # Add variance swap details if available
    if swap_data is not None and len(swap_data) > 0:
        sr = swap_data.iloc[0]
        vol_strike = sr.get('strike_vol', 0)
        vega_not = sr.get('vega_notional', 0)
        lines.append(f'Vol Strike:     {vol_strike:.2%}')
        lines.append(f'Vega Notional:  ${vega_not:,.0f}')
        lines.append(f'')

    # Add VRP details if available
    if vrp_data is not None and len(vrp_data) > 0:
        vr = vrp_data.iloc[-1]
        iv = vr.get('implied_var', 0)
        rv = vr.get('forecast_realized_var', 0)
        vrp_val = vr.get('vrp', 0)
        vrp_pct = vr.get('vrp_percent', 0)
        lines.append(f'Implied Vol:    {np.sqrt(iv)*100:.1f}%')
        lines.append(f'Forecast RV:    {np.sqrt(rv)*100:.1f}%')
        lines.append(f'VRP:            {vrp_val:.4f} ({vrp_pct:+.1f}%)')
        lines.append(f'')

        # Significance tests on VRP series
        vrp_values = vrp_data['vrp'].dropna().values
        if len(vrp_values) >= 10:
            # T-test: H0: mean VRP = 0
            t_stat, t_pval = stats.ttest_1samp(vrp_values, 0.0)
            t_sig = 'YES' if t_pval < 0.05 else 'NO'

            # Wilcoxon signed-rank: H0: median VRP = 0
            w_stat, w_pval = stats.wilcoxon(vrp_values)
            w_sig = 'YES' if w_pval < 0.05 else 'NO'

            lines.append(f'T-test (95%):      {t_sig}  (t={t_stat:.2f}, p={t_pval:.4f})')
            lines.append(f'Wilcoxon (95%):    {w_sig}  (p={w_pval:.4f})')
            lines.append(f'')

    if reason:
        lines.append(f'Reason: {reason}')

    lines.append(f'')
    lines.append(sig_desc)

    summary_text = '\n'.join(lines)

    # Draw the summary as a centered text box
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    # Title
    est_label = ESTIMATOR_LABELS.get(estimator, estimator)
    fc_label = FORECAST_LABELS.get(forecast, forecast)
    combo_str = f'  ({est_label} + {fc_label})' if est_label and fc_label else ''
    ax.text(0.5, 0.97, f'{ticker} — Trade Suggestion{combo_str}',
            fontsize=18, fontweight='bold', color=sig_color,
            ha='center', va='top', transform=ax.transAxes)

    # Divider line
    ax.axhline(y=0.92, xmin=0.15, xmax=0.85, color=sig_color, linewidth=2, alpha=0.6)

    # Summary text
    ax.text(0.5, 0.85, summary_text,
            fontsize=13, color=COLORS['fg'],
            ha='center', va='top', transform=ax.transAxes,
            family='monospace', linespacing=1.6,
            bbox=dict(boxstyle='round,pad=0.8', facecolor=COLORS['bg_light'],
                      edgecolor=sig_color, alpha=0.8, linewidth=1.5))

    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    print(f"  ✓ Saved signal summary to {output_file}")
    plt.close()


def plot_pnl(pnl_file: Path, output_file: Path):
    """Plot strategy P&L"""
    print(f"Plotting P&L from {pnl_file}...")

    df = pd.read_csv(pnl_file)

    if len(df) == 0:
        print("  ⚠ No P&L data to plot")
        return

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    # Panel 1: MTM P&L
    ax1 = axes[0]
    positive_pnl = df[df['mtm_pnl'] >= 0]
    negative_pnl = df[df['mtm_pnl'] < 0]

    ax1.bar(positive_pnl.index, positive_pnl['mtm_pnl'], color=COLORS['green'], alpha=0.7, label='Profit')
    ax1.bar(negative_pnl.index, negative_pnl['mtm_pnl'], color=COLORS['red'], alpha=0.7, label='Loss')
    ax1.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.5, linewidth=0.8)
    ax1.set_ylabel('MTM P&L ($)', fontsize=12)
    ax1.legend(loc='upper left', fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.set_title('Variance Swap Strategy - P&L Analysis', fontsize=14, pad=15)

    # Panel 2: Cumulative P&L
    ax2 = axes[1]
    ax2.plot(df.index, df['cumulative_pnl'], color=COLORS['cyan'], linewidth=2.5)
    ax2.fill_between(df.index, df['cumulative_pnl'], 0, alpha=0.3, color=COLORS['cyan'])
    ax2.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.5, linewidth=0.8)
    ax2.set_ylabel('Cumulative P&L ($)', fontsize=12)
    ax2.grid(True, alpha=0.3)

    # Panel 3: Sharpe Ratio (rolling)
    ax3 = axes[2]
    df_with_sharpe = df[df['sharpe_ratio'].notna()]
    if len(df_with_sharpe) > 0:
        ax3.plot(df_with_sharpe.index, df_with_sharpe['sharpe_ratio'],
                 color=COLORS['purple'], linewidth=2)
        ax3.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.5, linewidth=0.8)
        ax3.axhline(1.0, color=COLORS['yellow'], linestyle='--', alpha=0.5, label='Sharpe = 1.0')
        ax3.set_ylabel('Sharpe Ratio', fontsize=12)
        ax3.legend(loc='lower right', fontsize=10)
    ax3.set_xlabel('Time Index', fontsize=12)
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    print(f"  ✓ Saved P&L plot to {output_file}")
    plt.close()

    # Print summary stats
    print(f"\n  Summary Statistics:")
    print(f"    Total P&L: ${df['cumulative_pnl'].iloc[-1]:,.2f}")
    print(f"    Max Drawdown: ${df['cumulative_pnl'].min():,.2f}")
    if len(df_with_sharpe) > 0:
        print(f"    Final Sharpe: {df_with_sharpe['sharpe_ratio'].iloc[-1]:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Visualize VRP analysis")
    parser.add_argument('--vrp', type=str, help='VRP observations CSV file')
    parser.add_argument('--signals', type=str, help='Trading signals CSV file')
    parser.add_argument('--pnl', type=str, help='Strategy P&L CSV file')
    parser.add_argument('--output-dir', type=str, default='pricing/variance_swaps/output',
                        help='Output directory for plots')
    parser.add_argument('--estimator', type=str, default='', help='RV estimator used (for plot labels)')
    parser.add_argument('--forecast', type=str, default='', help='Forecast model used (for plot labels)')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build filename suffix from estimator/forecast combo
    suffix = f'_{args.estimator}_{args.forecast}' if args.estimator and args.forecast else ''

    try:
        if args.vrp:
            vrp_file = Path(args.vrp)
            ticker_stem = vrp_file.stem.replace(f'_vrp{suffix}', '').replace('_vrp', '')
            output_file = output_dir / f"{ticker_stem}_vrp{suffix}_plot.png"
            plot_vrp_time_series(vrp_file, output_file, estimator=args.estimator, forecast=args.forecast)

        if args.signals:
            signals_file = Path(args.signals)
            ticker_from_file = signals_file.stem.replace(f'_signal{suffix}', '').replace('_signal', '')
            output_file = output_dir / f"{ticker_from_file}_signal{suffix}_plot.png"
            vrp_path = signals_file.parent / f"{ticker_from_file}_vrp{suffix}.csv"
            swap_path = signals_file.parent / f"{ticker_from_file}_variance_swap.csv"
            plot_signals(signals_file, output_file,
                         vrp_file=vrp_path if vrp_path.exists() else None,
                         swap_file=swap_path if swap_path.exists() else None,
                         estimator=args.estimator, forecast=args.forecast)

        if args.pnl:
            pnl_file = Path(args.pnl)
            output_file = output_dir / f"{pnl_file.stem}_plot.png"
            plot_pnl(pnl_file, output_file)

        print("\n✅ Visualization complete")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1

    return 0


if __name__ == '__main__':
    exit(main())

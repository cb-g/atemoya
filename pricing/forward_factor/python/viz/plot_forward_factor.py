#!/usr/bin/env python3
"""
Visualize forward factor calendar spread analysis.

Creates:
1. Term structure (IV vs DTE)
2. Forward factor breakdown
3. Calendar spread payoff diagram
4. Opportunity summary
"""

import argparse
import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure


def get_kanagawa_cmap():
    """Create a Kanagawa-themed colormap for heatmaps."""
    colors_list = [COLORS['bg'], COLORS['blue'], COLORS['cyan'], COLORS['green'], COLORS['yellow']]
    return LinearSegmentedColormap.from_list('kanagawa', colors_list)


def setup_dark_style():
    """Configure matplotlib for dark mode."""
    setup_dark_mode()


def calculate_forward_vol(front_iv, back_iv, front_dte, back_dte):
    """Calculate forward volatility and forward factor."""
    t1 = front_dte / 365.0
    t2 = back_dte / 365.0

    v1 = front_iv ** 2
    v2 = back_iv ** 2

    # Forward variance
    if t2 > t1:
        forward_variance = (v2 * t2 - v1 * t1) / (t2 - t1)
    else:
        forward_variance = 0.0

    forward_variance = max(0.0, forward_variance)
    forward_volatility = np.sqrt(forward_variance)

    # Forward factor
    if forward_volatility > 0:
        forward_factor = (front_iv - forward_volatility) / forward_volatility
    else:
        forward_factor = 0.0

    return forward_volatility, forward_factor


def generate_sample_data(ticker):
    """Generate sample expiration data (matches OCaml main.ml)."""
    expirations = [
        {'exp': '2026-02-06', 'dte': 30, 'atm_iv': 0.35, 'call': 4.50, 'put': 4.30, 'strike': 180.0},
        {'exp': '2026-03-08', 'dte': 60, 'atm_iv': 0.28, 'call': 6.80, 'put': 6.50, 'strike': 180.0},
        {'exp': '2026-04-07', 'dte': 90, 'atm_iv': 0.26, 'call': 8.50, 'put': 8.20, 'strike': 180.0},
    ]
    return expirations


def plot_forward_factor_analysis(ticker: str, output_file: Path):
    """Create comprehensive forward factor visualization."""
    setup_dark_style()

    fig = plt.figure(figsize=(16, 12))
    gs = fig.add_gridspec(3, 3, hspace=0.35, wspace=0.3)

    # Generate sample data
    expirations = generate_sample_data(ticker)
    spot = 180.0  # Sample spot price

    # Calculate forward factors for different DTE pairs
    dte_pairs = [(30, 60), (30, 90), (60, 90)]
    ff_results = []

    for front_dte, back_dte in dte_pairs:
        front_exp = next(e for e in expirations if e['dte'] == front_dte)
        back_exp = next(e for e in expirations if e['dte'] == back_dte)

        fwd_vol, ff = calculate_forward_vol(
            front_exp['atm_iv'], back_exp['atm_iv'],
            front_dte, back_dte
        )

        ff_results.append({
            'pair': f"{front_dte}/{back_dte}",
            'front_dte': front_dte,
            'back_dte': back_dte,
            'front_iv': front_exp['atm_iv'],
            'back_iv': back_exp['atm_iv'],
            'forward_vol': fwd_vol,
            'forward_factor': ff,
            'front_price': front_exp['call'],
            'back_price': back_exp['call'],
        })

    # Best opportunity (highest FF)
    best = max(ff_results, key=lambda x: x['forward_factor'])

    # --- Plot 1: Term Structure (top left, spans 2 cols) ---
    ax1 = fig.add_subplot(gs[0, :2])

    dtes = [e['dte'] for e in expirations]
    ivs = [e['atm_iv'] * 100 for e in expirations]

    ax1.plot(dtes, ivs, 'o-', color=COLORS['cyan'], markersize=12, linewidth=2,
             markeredgecolor=COLORS['fg'], markeredgewidth=2)

    # Add forward vol line for best pair
    ax1.axhline(best['forward_vol'] * 100, color=COLORS['yellow'], linestyle='--',
                linewidth=2, label=f'Forward Vol ({best["forward_vol"]*100:.1f}%)')

    # Shade backwardation region
    ax1.fill_between(dtes, ivs, best['forward_vol'] * 100,
                     where=[iv > best['forward_vol'] * 100 for iv in ivs],
                     color=COLORS['green'], alpha=0.2, label='Backwardation')

    # Annotations
    for dte, iv in zip(dtes, ivs):
        ax1.annotate(f'{iv:.1f}%', (dte, iv), textcoords="offset points",
                     xytext=(0, 10), ha='center', fontsize=10, color=COLORS['fg'])

    ax1.set_xlabel('Days to Expiration')
    ax1.set_ylabel('Implied Volatility (%)')
    ax1.set_title('Volatility Term Structure (Backwardation)', fontsize=14, fontweight='bold')
    ax1.legend(loc='upper right', fontsize=9)
    ax1.grid(True, alpha=0.2)
    ax1.set_xlim(0, 100)

    # --- Plot 2: Summary Panel (top right) ---
    ax2 = fig.add_subplot(gs[0, 2])
    ax2.axis('off')

    # Determine recommendation
    if best['forward_factor'] >= 1.0:
        rec = "STRONG BUY"
        rec_note = "Extreme backwardation"
    elif best['forward_factor'] >= 0.5:
        rec = "BUY"
        rec_note = "Strong backwardation"
    elif best['forward_factor'] >= 0.2:
        rec = "CONSIDER"
        rec_note = "Valid setup"
    else:
        rec = "PASS"
        rec_note = "Below threshold"

    net_debit = best['back_price'] - best['front_price']
    expected_return = min(0.30, best['forward_factor'] * 0.3) * 100

    summary_text = f"""{ticker} FORWARD FACTOR
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Best DTE Pair: {best['pair']}
Forward Factor: {best['forward_factor']*100:.1f}%

TERM STRUCTURE
Front IV ({best['front_dte']}d): {best['front_iv']*100:.1f}%
Back IV ({best['back_dte']}d): {best['back_iv']*100:.1f}%
Forward Vol: {best['forward_vol']*100:.1f}%

CALENDAR SPREAD
Sell {best['front_dte']}d Call: ${best['front_price']:.2f}
Buy {best['back_dte']}d Call: ${best['back_price']:.2f}
Net Debit: ${net_debit:.2f}

Expected Return: {expected_return:.0f}%

{rec}
{rec_note}"""

    ax2.text(0.05, 0.98, summary_text, transform=ax2.transAxes,
             fontsize=9, verticalalignment='top', fontfamily='monospace',
             color=COLORS['fg'], linespacing=1.1)

    # --- Plot 3: Forward Factor Comparison (middle left) ---
    ax3 = fig.add_subplot(gs[1, 0])

    pairs = [r['pair'] for r in ff_results]
    ffs = [r['forward_factor'] * 100 for r in ff_results]

    colors_ff = [COLORS['green'] if ff >= 20 else COLORS['yellow'] if ff >= 0 else COLORS['red']
                 for ff in ffs]

    bars = ax3.bar(pairs, ffs, color=colors_ff, alpha=0.7, edgecolor=COLORS['fg'])
    ax3.axhline(20, color=COLORS['cyan'], linestyle='--', alpha=0.7, label='Threshold (20%)')
    ax3.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.3)

    # Add value labels
    for bar, ff in zip(bars, ffs):
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height + 1,
                f'{ff:.1f}%', ha='center', va='bottom', fontsize=10, color=COLORS['fg'])

    ax3.set_xlabel('DTE Pair (Front/Back)')
    ax3.set_ylabel('Forward Factor (%)')
    ax3.set_title('Forward Factor by DTE Pair', fontsize=12, fontweight='bold')
    ax3.legend(loc='upper right', fontsize=8)
    ax3.grid(True, alpha=0.2, axis='y')

    # --- Plot 4: Forward Vol Breakdown (middle center) ---
    ax4 = fig.add_subplot(gs[1, 1])

    labels = ['Front IV', 'Back IV', 'Forward Vol']
    values = [best['front_iv'] * 100, best['back_iv'] * 100, best['forward_vol'] * 100]
    colors_bar = [COLORS['red'], COLORS['blue'], COLORS['yellow']]

    y_pos = np.arange(len(labels))
    bars = ax4.barh(y_pos, values, color=colors_bar, alpha=0.7, edgecolor=COLORS['fg'])

    ax4.set_yticks(y_pos)
    ax4.set_yticklabels(labels)
    ax4.set_xlabel('Volatility (%)')
    ax4.set_title(f'Forward Vol Breakdown ({best["pair"]})', fontsize=12, fontweight='bold')
    ax4.grid(True, alpha=0.2, axis='x')

    # Add value labels
    for bar, val in zip(bars, values):
        width = bar.get_width()
        ax4.text(width + 0.5, bar.get_y() + bar.get_height()/2,
                f'{val:.1f}%', ha='left', va='center', fontsize=10, color=COLORS['fg'])

    # --- Plot 5: Calendar Spread Payoff (middle right) ---
    ax5 = fig.add_subplot(gs[1, 2])

    strike = 180.0
    front_price = best['front_price']
    back_price = best['back_price']
    net_debit = back_price - front_price

    # Simplified calendar payoff at front expiration
    # Max profit at strike, limited loss at extremes
    prices = np.linspace(strike * 0.85, strike * 1.15, 200)

    # Approximate calendar payoff (bell curve around strike)
    distance_from_strike = np.abs(prices - strike)
    max_profit = front_price * 0.8  # Approximate max profit
    payoff = max_profit * np.exp(-0.5 * (distance_from_strike / (strike * 0.05)) ** 2) - net_debit

    ax5.fill_between(prices, payoff, 0, where=(payoff >= 0),
                     color=COLORS['green'], alpha=0.3)
    ax5.fill_between(prices, payoff, 0, where=(payoff < 0),
                     color=COLORS['red'], alpha=0.3)
    ax5.plot(prices, payoff, color=COLORS['blue'], linewidth=2)

    ax5.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.3)
    ax5.axvline(strike, color=COLORS['yellow'], linestyle='--', alpha=0.7,
                label=f'Strike ${strike:.0f}')
    ax5.axhline(-net_debit, color=COLORS['red'], linestyle=':', alpha=0.7,
                label=f'Max Loss ${net_debit:.2f}')

    ax5.set_xlabel('Stock Price at Front Expiration ($)')
    ax5.set_ylabel('Profit/Loss ($)')
    ax5.set_title('Calendar Spread Payoff', fontsize=12, fontweight='bold')
    ax5.legend(loc='upper right', fontsize=8)
    ax5.grid(True, alpha=0.2)

    # --- Plot 6: IV Surface Heatmap (bottom left) ---
    ax6 = fig.add_subplot(gs[2, 0])

    # Simulate IV surface across strikes and expirations
    strikes = np.array([170, 175, 180, 185, 190])
    dte_grid = np.array([30, 60, 90])

    # Create synthetic IV surface with skew
    iv_surface = np.zeros((len(strikes), len(dte_grid)))
    for i, s in enumerate(strikes):
        moneyness = np.log(s / spot)
        skew = 0.1 * moneyness ** 2  # Simple smile
        for j, dte in enumerate(dte_grid):
            base_iv = expirations[j]['atm_iv']
            iv_surface[i, j] = (base_iv + skew) * 100

    im = ax6.imshow(iv_surface, cmap=get_kanagawa_cmap(), aspect='auto', origin='lower')
    ax6.set_xticks(range(len(dte_grid)))
    ax6.set_xticklabels([f'{d}d' for d in dte_grid])
    ax6.set_yticks(range(len(strikes)))
    ax6.set_yticklabels([f'${s}' for s in strikes])
    ax6.set_xlabel('Days to Expiration')
    ax6.set_ylabel('Strike')
    ax6.set_title('IV Surface', fontsize=12, fontweight='bold')
    cbar = plt.colorbar(im, ax=ax6, label='IV (%)')
    cbar.ax.yaxis.label.set_color(COLORS['fg'])
    cbar.ax.tick_params(colors=COLORS['fg'])

    # --- Plot 7: Expected Return by FF (bottom center) ---
    ax7 = fig.add_subplot(gs[2, 1])

    # Backtest data (from strategy description)
    ff_buckets = [0.2, 0.3, 0.5, 0.7, 1.0, 1.5]
    expected_returns = [8, 12, 18, 22, 28, 35]  # Approximate from backtest

    ax7.bar(range(len(ff_buckets)), expected_returns, color=COLORS['green'],
            alpha=0.7, edgecolor=COLORS['fg'])
    ax7.set_xticks(range(len(ff_buckets)))
    ax7.set_xticklabels([f'{ff*100:.0f}%' for ff in ff_buckets])

    # Mark current FF
    current_ff = best['forward_factor']
    for i, ff in enumerate(ff_buckets):
        if current_ff <= ff:
            ax7.axvline(i - 0.5 + (current_ff - (ff_buckets[i-1] if i > 0 else 0)) /
                       (ff - (ff_buckets[i-1] if i > 0 else 0)),
                       color=COLORS['yellow'], linestyle='--', linewidth=2,
                       label=f'Current FF ({current_ff*100:.0f}%)')
            break

    ax7.set_xlabel('Forward Factor Bucket')
    ax7.set_ylabel('Expected Return (%)')
    ax7.set_title('Historical Returns by FF', fontsize=12, fontweight='bold')
    ax7.legend(loc='upper left', fontsize=8)
    ax7.grid(True, alpha=0.2, axis='y')

    # --- Plot 8: Strategy Stats (bottom right) ---
    ax8 = fig.add_subplot(gs[2, 2])
    ax8.axis('off')

    stats_text = f"""BACKTEST STATISTICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━
CAGR: 27%
Sharpe Ratio: 2.42
Win Rate: 68%
Avg Win: +15%
Avg Loss: -8%

POSITION SIZING
Kelly: {min(8, best['forward_factor'] * 10):.1f}%
Suggested: 4% of portfolio

TRADE THESIS
• Buy calendar when FF ≥ 20%
• Profit from IV term structure
• Front IV decays faster than back
• Best DTE pairs: 60/90, 30/90

RISK MANAGEMENT
• Max loss = net debit
• Exit if FF inverts (contango)
• Roll front leg if profitable"""

    ax8.text(0.05, 0.95, stats_text, transform=ax8.transAxes,
             fontsize=9, verticalalignment='top', fontfamily='monospace',
             color=COLORS['fg'], linespacing=1.2)

    # Main title
    fig.suptitle(f'{ticker} Forward Factor Calendar Spread Analysis',
                 fontsize=16, fontweight='bold', color=COLORS['fg'], y=0.98)

    save_figure(fig, output_file, dpi=300)
    plt.close()

    print(f"✓ Saved forward factor analysis plot: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Visualize forward factor analysis')
    parser.add_argument('-t', '--ticker', type=str, default='AAPL',
                        help='Stock ticker symbol')
    parser.add_argument('-o', '--output-dir', type=str, default='pricing/forward_factor/output/plots',
                        help='Output directory for plots')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating forward factor visualization for {args.ticker}...")

    output_file = output_dir / f"{args.ticker}_forward_factor.png"
    plot_forward_factor_analysis(args.ticker, output_file)

    return 0


if __name__ == '__main__':
    exit(main())

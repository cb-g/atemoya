#!/usr/bin/env python3
"""
Visualize pre-earnings straddle analysis.

Creates:
1. Historical implied vs realized moves comparison
2. Straddle payoff diagram
3. Signal analysis
4. Opportunity summary
"""

import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure


def setup_dark_style():
    """Configure matplotlib for dark mode."""
    setup_dark_mode()


def load_data(ticker: str, data_dir: Path) -> tuple:
    """Load all data files."""
    # Load earnings history
    history_file = data_dir / 'earnings_history.csv'
    history_df = pd.read_csv(history_file)
    history_df = history_df[history_df['ticker'] == ticker].copy()

    # Load current opportunity
    opp_file = data_dir / f'{ticker}_opportunity.csv'
    opp_df = pd.read_csv(opp_file)

    # Load model coefficients
    coef_file = data_dir / 'model_coefficients.csv'
    coef_df = pd.read_csv(coef_file)

    return history_df, opp_df, coef_df


def calculate_signals(history_df: pd.DataFrame, current_implied: float) -> dict:
    """Calculate the four predictive signals."""
    if len(history_df) == 0:
        return None

    last_implied = history_df['implied_move'].iloc[-1]
    last_realized = history_df['realized_move'].iloc[-1]
    avg_implied = history_df['implied_move'].mean()
    avg_realized = history_df['realized_move'].mean()

    return {
        'current_implied': current_implied,
        'last_implied': last_implied,
        'last_realized': last_realized,
        'avg_implied': avg_implied,
        'avg_realized': avg_realized,
        'implied_vs_last_implied': current_implied / last_implied if last_implied > 0 else 1.0,
        'implied_vs_last_realized': current_implied - last_realized,
        'implied_vs_avg_implied': current_implied / avg_implied if avg_implied > 0 else 1.0,
        'implied_vs_avg_realized': current_implied - avg_realized,
    }


def predict_return(signals: dict, coef_df: pd.DataFrame) -> float:
    """Calculate predicted return using model coefficients."""
    intercept = coef_df['intercept'].iloc[0]
    c1 = coef_df['coef_implied_vs_last_implied'].iloc[0]
    c2 = coef_df['coef_implied_vs_last_realized'].iloc[0]
    c3 = coef_df['coef_implied_vs_avg_implied'].iloc[0]
    c4 = coef_df['coef_implied_vs_avg_realized'].iloc[0]

    return (intercept +
            c1 * signals['implied_vs_last_implied'] +
            c2 * signals['implied_vs_last_realized'] +
            c3 * signals['implied_vs_avg_implied'] +
            c4 * signals['implied_vs_avg_realized'])


def plot_straddle_analysis(ticker: str, history_df: pd.DataFrame, opp_df: pd.DataFrame,
                           coef_df: pd.DataFrame, output_file: Path):
    """Create comprehensive straddle visualization."""
    setup_dark_style()

    fig = plt.figure(figsize=(16, 12))
    gs = fig.add_gridspec(3, 3, hspace=0.35, wspace=0.3)

    # Extract opportunity data
    opp = opp_df.iloc[0]
    spot = opp['spot_price']
    strike = opp['atm_strike']
    call_price = opp['atm_call_price']
    put_price = opp['atm_put_price']
    straddle_cost = opp['straddle_cost']
    current_implied = opp['current_implied_move']
    days_to_earnings = opp['days_to_earnings']
    earnings_date = opp['earnings_date']

    # Calculate signals and prediction
    signals = calculate_signals(history_df, current_implied)
    predicted_return = predict_return(signals, coef_df) if signals else 0.0

    # --- Plot 1: Historical Implied vs Realized (top left, spans 2 cols) ---
    ax1 = fig.add_subplot(gs[0, :2])

    if len(history_df) > 0:
        dates = history_df['date'].values
        implied = history_df['implied_move'].values * 100
        realized = history_df['realized_move'].values * 100

        x = np.arange(len(dates))
        width = 0.35

        bars1 = ax1.bar(x - width/2, implied, width, label='Implied Move',
                        color=COLORS['blue'], alpha=0.8, edgecolor=COLORS['fg'])
        bars2 = ax1.bar(x + width/2, realized, width, label='Realized Move',
                        color=COLORS['green'], alpha=0.8, edgecolor=COLORS['fg'])

        # Add current implied as a horizontal line
        ax1.axhline(current_implied * 100, color=COLORS['yellow'], linestyle='--',
                    linewidth=2, label=f'Current Implied ({current_implied*100:.1f}%)')

        ax1.set_xticks(x)
        ax1.set_xticklabels([d[:7] for d in dates], rotation=45, ha='right')
        ax1.set_ylabel('Move (%)')
        ax1.set_title('Historical Implied vs Realized Moves', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper right', fontsize=9)
        ax1.grid(True, alpha=0.2, axis='y')

    # --- Plot 2: Summary Panel (top right) ---
    ax2 = fig.add_subplot(gs[0, 2])
    ax2.axis('off')

    # Determine recommendation
    if predicted_return >= 0.05:
        rec = "STRONG BUY"
        rec_color = COLORS['green']
    elif predicted_return >= 0.02:
        rec = "BUY"
        rec_color = COLORS['cyan']
    else:
        rec = "PASS"
        rec_color = COLORS['yellow']

    summary_text = f"""{ticker} PRE-EARNINGS STRADDLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Earnings: {earnings_date}
Days to Earnings: {days_to_earnings}

STRADDLE DETAILS
Spot: ${spot:.2f}
ATM Strike: ${strike:.0f}
Call: ${call_price:.2f}
Put: ${put_price:.2f}
Total Cost: ${straddle_cost:.2f}

IMPLIED MOVE
Current: {current_implied*100:.2f}%
Avg Historical: {signals['avg_implied']*100:.2f}%
Ratio: {signals['implied_vs_avg_implied']:.2f}x

PREDICTION
Predicted Return: {predicted_return*100:.2f}%

{rec}"""

    ax2.text(0.05, 0.98, summary_text, transform=ax2.transAxes,
             fontsize=9, verticalalignment='top', fontfamily='monospace',
             color=COLORS['fg'], linespacing=1.1)

    # Timing warning
    timing_warn = ''
    if days_to_earnings < 5:
        timing_warn = f'\nTOO CLOSE ({days_to_earnings}d)\nlimited entry window'
    elif days_to_earnings > 45:
        timing_warn = f'\nTOO FAR ({days_to_earnings}d)\nvol crush uncertain'

    if timing_warn:
        ax2.text(0.95, 0.98, timing_warn, transform=ax2.transAxes,
                 fontsize=7, verticalalignment='top', ha='right',
                 fontfamily='monospace', color=COLORS['bg'],
                 bbox=dict(boxstyle='round,pad=0.4', facecolor=COLORS['orange'],
                           edgecolor=COLORS['orange'], alpha=0.9))

    # --- Plot 3: Straddle Payoff Diagram (middle left) ---
    ax3 = fig.add_subplot(gs[1, 0])

    # Price range
    price_range = strike * 0.3
    prices = np.linspace(strike - price_range, strike + price_range, 200)

    # Straddle payoff
    call_payoff = np.maximum(prices - strike, 0)
    put_payoff = np.maximum(strike - prices, 0)
    straddle_payoff = call_payoff + put_payoff - straddle_cost

    ax3.fill_between(prices, straddle_payoff, 0, where=(straddle_payoff >= 0),
                     color=COLORS['green'], alpha=0.3)
    ax3.fill_between(prices, straddle_payoff, 0, where=(straddle_payoff < 0),
                     color=COLORS['red'], alpha=0.3)
    ax3.plot(prices, straddle_payoff, color=COLORS['blue'], linewidth=2)

    ax3.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.3)
    ax3.axvline(strike, color=COLORS['yellow'], linestyle='--', alpha=0.7,
                label=f'Strike ${strike:.0f}')

    # Breakeven points
    upper_be = strike + straddle_cost
    lower_be = strike - straddle_cost
    ax3.axvline(upper_be, color=COLORS['cyan'], linestyle=':', alpha=0.7)
    ax3.axvline(lower_be, color=COLORS['cyan'], linestyle=':', alpha=0.7)

    ax3.set_xlabel('Stock Price at Expiration ($)')
    ax3.set_ylabel('Profit/Loss ($)')
    ax3.set_title('Straddle Payoff at Expiration', fontsize=12, fontweight='bold')
    ax3.legend(loc='upper right', fontsize=8)
    ax3.grid(True, alpha=0.2)

    # --- Plot 4: Signal Analysis (middle center) ---
    ax4 = fig.add_subplot(gs[1, 1])

    signal_names = ['Impl/Last Impl', 'Impl-Last Real', 'Impl/Avg Impl', 'Impl-Avg Real']
    signal_values = [
        signals['implied_vs_last_implied'],
        signals['implied_vs_last_realized'] * 100,  # Convert to %
        signals['implied_vs_avg_implied'],
        signals['implied_vs_avg_realized'] * 100,   # Convert to %
    ]

    # Neutral values (1.0 for ratios, 0 for differences)
    neutral = [1.0, 0, 1.0, 0]

    colors_sig = []
    for i, (val, neu) in enumerate(zip(signal_values, neutral)):
        if i in [0, 2]:  # Ratios: lower is better (cheaper implied)
            colors_sig.append(COLORS['green'] if val < neu else COLORS['red'])
        else:  # Differences: lower is better
            colors_sig.append(COLORS['green'] if val < neu else COLORS['red'])

    y_pos = np.arange(len(signal_names))
    bars = ax4.barh(y_pos, signal_values, color=colors_sig, alpha=0.7, edgecolor=COLORS['fg'])

    ax4.set_yticks(y_pos)
    ax4.set_yticklabels(signal_names)
    ax4.axvline(1.0, color=COLORS['fg'], linestyle='--', alpha=0.5)
    ax4.axvline(0, color=COLORS['fg'], linestyle='-', alpha=0.3)
    ax4.set_title('Signal Analysis', fontsize=12, fontweight='bold')
    ax4.grid(True, alpha=0.2, axis='x')

    # Add value labels
    for bar, val in zip(bars, signal_values):
        width = bar.get_width()
        ax4.text(width + 0.02, bar.get_y() + bar.get_height()/2,
                f'{val:.2f}', ha='left', va='center', fontsize=9, color=COLORS['fg'])

    # --- Plot 5: Implied Move Distribution (middle right) ---
    ax5 = fig.add_subplot(gs[1, 2])

    if len(history_df) > 0:
        implied_hist = history_df['implied_move'].values * 100
        realized_hist = history_df['realized_move'].values * 100

        bins = np.linspace(0, max(implied_hist.max(), realized_hist.max()) * 1.2, 15)

        ax5.hist(implied_hist, bins=bins, alpha=0.6, color=COLORS['blue'],
                 label='Implied', edgecolor=COLORS['fg'])
        ax5.hist(realized_hist, bins=bins, alpha=0.6, color=COLORS['green'],
                 label='Realized', edgecolor=COLORS['fg'])

        ax5.axvline(current_implied * 100, color=COLORS['yellow'], linestyle='--',
                    linewidth=2, label=f'Current ({current_implied*100:.1f}%)')

        ax5.set_xlabel('Move (%)')
        ax5.set_ylabel('Frequency')
        ax5.set_title('Move Distribution', fontsize=12, fontweight='bold')
        ax5.legend(loc='upper right', fontsize=8)
        ax5.grid(True, alpha=0.2)

    # --- Plot 6: Implied vs Realized Scatter (bottom left) ---
    ax6 = fig.add_subplot(gs[2, 0])

    if len(history_df) > 0:
        implied_hist = history_df['implied_move'].values * 100
        realized_hist = history_df['realized_move'].values * 100

        ax6.scatter(implied_hist, realized_hist, s=80, color=COLORS['cyan'],
                    alpha=0.7, edgecolor=COLORS['fg'], linewidth=1)

        # 45-degree line (implied = realized)
        max_val = max(implied_hist.max(), realized_hist.max())
        ax6.plot([0, max_val], [0, max_val], color=COLORS['yellow'], linestyle='--',
                 alpha=0.7, label='Implied = Realized')

        # Current implied as vertical line
        ax6.axvline(current_implied * 100, color=COLORS['magenta'], linestyle=':',
                    linewidth=2, label=f'Current Implied')

        ax6.set_xlabel('Implied Move (%)')
        ax6.set_ylabel('Realized Move (%)')
        ax6.set_title('Implied vs Realized', fontsize=12, fontweight='bold')
        ax6.legend(loc='upper left', fontsize=8)
        ax6.grid(True, alpha=0.2)

    # --- Plot 7: Historical Returns (bottom center) ---
    ax7 = fig.add_subplot(gs[2, 1])

    if len(history_df) > 0:
        # Simulate what returns would have been
        implied_hist = history_df['implied_move'].values
        realized_hist = history_df['realized_move'].values

        # Straddle return = realized/implied - 1 (simplified)
        returns = (realized_hist / implied_hist - 1) * 100

        colors_ret = [COLORS['green'] if r > 0 else COLORS['red'] for r in returns]

        x = np.arange(len(returns))
        bars = ax7.bar(x, returns, color=colors_ret, alpha=0.7, edgecolor=COLORS['fg'])

        ax7.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.3)
        ax7.axhline(np.mean(returns), color=COLORS['yellow'], linestyle='--',
                    alpha=0.7, label=f'Avg: {np.mean(returns):.1f}%')

        dates = history_df['date'].values
        ax7.set_xticks(x)
        ax7.set_xticklabels([d[:7] for d in dates], rotation=45, ha='right')
        ax7.set_ylabel('Return (%)')
        ax7.set_title('Historical Straddle Returns', fontsize=12, fontweight='bold')
        ax7.legend(loc='best', fontsize=8)
        ax7.grid(True, alpha=0.2, axis='y')

    # --- Plot 8: Win Rate Stats (bottom right) ---
    ax8 = fig.add_subplot(gs[2, 2])
    ax8.axis('off')

    if len(history_df) > 0:
        implied_hist = history_df['implied_move'].values
        realized_hist = history_df['realized_move'].values

        # Win = realized > implied * some threshold (account for premium decay)
        wins = np.sum(realized_hist > implied_hist * 0.8)
        total = len(history_df)
        win_rate = wins / total * 100

        avg_implied = np.mean(implied_hist) * 100
        avg_realized = np.mean(realized_hist) * 100
        implied_premium = (avg_implied - avg_realized) / avg_realized * 100 if avg_realized > 0 else 0

        stats_text = f"""HISTORICAL STATISTICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Events: {total}
Win Rate (80%): {win_rate:.1f}%

Avg Implied: {avg_implied:.2f}%
Avg Realized: {avg_realized:.2f}%
Implied Premium: {implied_premium:.1f}%

MODEL PREDICTION
Predicted Return: {predicted_return*100:.2f}%

TRADE THESIS
• Buy straddle ~14 days before earnings
• Implied vol typically rises into event
• Exit day before announcement
• Profit from IV expansion, not direction"""

        ax8.text(0.05, 0.95, stats_text, transform=ax8.transAxes,
                 fontsize=9, verticalalignment='top', fontfamily='monospace',
                 color=COLORS['fg'], linespacing=1.2)

    # Main title
    fig.suptitle(f'{ticker} Pre-Earnings Straddle Analysis',
                 fontsize=16, fontweight='bold', color=COLORS['fg'], y=0.98)

    save_figure(fig, output_file, dpi=300)
    plt.close()

    print(f"✓ Saved straddle analysis plot: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Visualize pre-earnings straddle analysis')
    parser.add_argument('-t', '--ticker', type=str, required=True,
                        help='Stock ticker symbol')
    parser.add_argument('-d', '--data-dir', type=str, default='pricing/pre_earnings_straddle/data',
                        help='Data directory')
    parser.add_argument('-o', '--output-dir', type=str, default='pricing/pre_earnings_straddle/output/plots',
                        help='Output directory for plots')

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    print(f"Loading data for {args.ticker}...")
    history_df, opp_df, coef_df = load_data(args.ticker, data_dir)

    print(f"Historical events: {len(history_df)}")
    print(f"Generating visualization...")

    output_file = output_dir / f"{args.ticker}_straddle_analysis.png"
    plot_straddle_analysis(args.ticker, history_df, opp_df, coef_df, output_file)

    return 0


if __name__ == '__main__':
    exit(main())

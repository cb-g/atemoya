#!/usr/bin/env python3
"""
Visualize vertical spread analysis.

Creates:
1. Payoff diagram at expiration
2. IV skew curve with spread legs marked
3. Probability distribution with breakeven
4. Summary metrics panel
"""

import argparse
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure


def setup_dark_style():
    """Configure matplotlib for dark mode."""
    setup_dark_mode()


def load_scan_result(ticker: str, data_dir: Path) -> dict:
    """Load the most recent scan result for a ticker."""
    # Look for JSON files
    pattern = f"{ticker}_scan_*.json"
    json_files = sorted(data_dir.glob(pattern), reverse=True)

    if not json_files:
        raise FileNotFoundError(f"No scan results found for {ticker} in {data_dir}")

    with open(json_files[0], 'r') as f:
        return json.load(f)


def load_options_chain(ticker: str, data_dir: Path) -> tuple:
    """Load options chain data."""
    # Find the expiration
    meta_files = list(data_dir.glob(f"{ticker}_*_metadata.csv"))
    if not meta_files:
        raise FileNotFoundError(f"No metadata file found for {ticker}")

    meta_file = meta_files[0]
    meta_df = pd.read_csv(meta_file)
    spot = meta_df['spot_price'].iloc[0]

    # Extract expiration from filename
    exp = meta_file.stem.split('_')[1]

    calls_file = data_dir / f"{ticker}_{exp}_calls.csv"
    puts_file = data_dir / f"{ticker}_{exp}_puts.csv"

    calls_df = pd.read_csv(calls_file)
    puts_df = pd.read_csv(puts_file)

    return spot, calls_df, puts_df


def calculate_payoff(prices: np.ndarray, spread: dict) -> np.ndarray:
    """Calculate spread payoff at expiration."""
    spread_type = spread['type']
    long_strike = spread['long_strike']
    short_strike = spread['short_strike']
    debit = spread['debit']

    if spread_type == 'bull_call':
        # Long lower strike call, short higher strike call
        long_payoff = np.maximum(prices - long_strike, 0)
        short_payoff = np.maximum(prices - short_strike, 0)
        return long_payoff - short_payoff - debit

    elif spread_type == 'bear_put':
        # Long higher strike put, short lower strike put
        long_payoff = np.maximum(long_strike - prices, 0)
        short_payoff = np.maximum(short_strike - prices, 0)
        return long_payoff - short_payoff - debit

    elif spread_type == 'bull_put':
        # Short higher strike put, long lower strike put (credit)
        short_payoff = np.maximum(short_strike - prices, 0)
        long_payoff = np.maximum(long_strike - prices, 0)
        credit = -debit  # debit is negative for credit spreads
        return credit - short_payoff + long_payoff

    elif spread_type == 'bear_call':
        # Short lower strike call, long higher strike call (credit)
        short_payoff = np.maximum(prices - short_strike, 0)
        long_payoff = np.maximum(prices - long_strike, 0)
        credit = -debit
        return credit - short_payoff + long_payoff

    return np.zeros_like(prices)


def plot_spread_analysis(scan_result: dict, spot: float, calls_df: pd.DataFrame,
                          puts_df: pd.DataFrame, output_file: Path):
    """Create comprehensive spread visualization."""
    setup_dark_style()

    fig = plt.figure(figsize=(16, 12))

    spread = scan_result['spread']
    skew = scan_result['skew']
    momentum = scan_result['momentum']

    # Create grid layout
    gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)

    # --- Plot 1: Payoff Diagram (top left, spans 2 cols) ---
    ax1 = fig.add_subplot(gs[0, :2])

    # Price range
    price_min = spot * 0.7
    price_max = spot * 1.3
    prices = np.linspace(price_min, price_max, 200)

    payoff = calculate_payoff(prices, spread)

    # Plot payoff
    ax1.fill_between(prices, payoff, 0, where=(payoff >= 0),
                     color=COLORS['green'], alpha=0.3, label='Profit')
    ax1.fill_between(prices, payoff, 0, where=(payoff < 0),
                     color=COLORS['red'], alpha=0.3, label='Loss')
    ax1.plot(prices, payoff, color=COLORS['blue'], linewidth=2)

    # Mark key levels
    ax1.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.3)
    ax1.axvline(spot, color=COLORS['yellow'], linestyle='--', alpha=0.7, label=f'Spot ${spot:.2f}')
    ax1.axvline(spread['breakeven'], color=COLORS['cyan'], linestyle='--', alpha=0.7,
                label=f'Breakeven ${spread["breakeven"]:.2f}')
    ax1.axvline(spread['long_strike'], color=COLORS['green'], linestyle=':', alpha=0.7,
                label=f'Long ${spread["long_strike"]:.0f}')
    ax1.axvline(spread['short_strike'], color=COLORS['red'], linestyle=':', alpha=0.7,
                label=f'Short ${spread["short_strike"]:.0f}')

    # Mark max profit/loss
    ax1.axhline(spread['max_profit'], color=COLORS['green'], linestyle=':', alpha=0.5)
    ax1.axhline(-spread['max_loss'], color=COLORS['red'], linestyle=':', alpha=0.5)

    ax1.set_xlabel('Stock Price at Expiration ($)')
    ax1.set_ylabel('Profit/Loss ($)')
    ax1.set_title(f'{spread["type"].upper()} Spread Payoff Diagram', fontsize=14, fontweight='bold')
    ax1.legend(loc='best', fontsize=8)
    ax1.grid(True, alpha=0.2)

    # --- Plot 2: Summary Metrics (top right) ---
    ax2 = fig.add_subplot(gs[0, 2])
    ax2.axis('off')

    # Determine if credit or debit
    is_credit = spread['debit'] < 0
    cost_label = "Credit" if is_credit else "Debit"
    cost_value = abs(spread['debit'])

    metrics_text = f"""{scan_result['ticker']} {spread['type'].upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━
Exp: {spread['expiration']} ({spread['days_to_expiry']}d)

Long:  ${spread['long_strike']:.0f} @ ${spread['long_price']:.2f}
Short: ${spread['short_strike']:.0f} @ ${spread['short_price']:.2f}

{cost_label}: ${cost_value:.2f}  |  R/R: {spread['reward_risk_ratio']:.1f}:1
Max Profit: ${spread['max_profit']:.2f}
Max Loss: ${spread['max_loss']:.2f}
Breakeven: ${spread['breakeven']:.2f}

Prob Profit: {spread['prob_profit']*100:.1f}%
Exp. Value: ${spread['expected_value']:.2f}
Exp. Return: {spread['expected_return_pct']:.1f}%

{scan_result['recommendation']} ({scan_result['edge_score']:.0f}/100)"""

    ax2.text(0.05, 0.98, metrics_text, transform=ax2.transAxes,
             fontsize=9, verticalalignment='top', fontfamily='monospace',
             color=COLORS['fg'], linespacing=1.1)

    # --- Plot 3: IV Skew Curve (middle left) ---
    ax3 = fig.add_subplot(gs[1, 0])

    # Filter options with reasonable IV
    calls_clean = calls_df[(calls_df['implied_vol'] > 0.05) & (calls_df['implied_vol'] < 1.5)]
    puts_clean = puts_df[(puts_df['implied_vol'] > 0.05) & (puts_df['implied_vol'] < 1.5)]

    ax3.scatter(calls_clean['strike'], calls_clean['implied_vol'] * 100,
                color=COLORS['cyan'], alpha=0.6, s=30, label='Calls')
    ax3.scatter(puts_clean['strike'], puts_clean['implied_vol'] * 100,
                color=COLORS['magenta'], alpha=0.6, s=30, label='Puts')

    # Mark spread legs
    ax3.axvline(spread['long_strike'], color=COLORS['green'], linestyle='--', alpha=0.8)
    ax3.axvline(spread['short_strike'], color=COLORS['red'], linestyle='--', alpha=0.8)
    ax3.axvline(spot, color=COLORS['yellow'], linestyle='-', alpha=0.5, label='Spot')

    # Mark ATM IV
    ax3.axhline(skew['atm_iv'] * 100, color=COLORS['fg'], linestyle=':', alpha=0.5, label='ATM IV')

    ax3.set_xlabel('Strike ($)')
    ax3.set_ylabel('Implied Volatility (%)')
    ax3.set_title('IV Skew Curve', fontsize=12, fontweight='bold')
    ax3.legend(loc='best', fontsize=8)
    ax3.grid(True, alpha=0.2)
    ax3.set_xlim(spot * 0.7, spot * 1.3)

    # --- Plot 4: Price Distribution (middle center) ---
    ax4 = fig.add_subplot(gs[1, 1])

    # Generate price distribution based on ATM IV
    t = spread['days_to_expiry'] / 365.0
    sigma = skew['atm_iv'] * np.sqrt(t)

    # Log-normal distribution for stock prices
    prices_dist = np.linspace(spot * 0.6, spot * 1.4, 200)

    # Approximate with normal distribution on log returns
    log_returns = np.log(prices_dist / spot)
    pdf = norm.pdf(log_returns, loc=0, scale=sigma) / prices_dist

    ax4.fill_between(prices_dist, pdf, alpha=0.3, color=COLORS['blue'])
    ax4.plot(prices_dist, pdf, color=COLORS['blue'], linewidth=2)

    # Mark breakeven
    ax4.axvline(spread['breakeven'], color=COLORS['cyan'], linestyle='--', linewidth=2,
                label=f'Breakeven ${spread["breakeven"]:.2f}')
    ax4.axvline(spot, color=COLORS['yellow'], linestyle='-', linewidth=2,
                label=f'Current ${spot:.2f}')

    # Shade profit region
    if spread['type'] in ['bull_call', 'bull_put']:
        profit_mask = prices_dist >= spread['breakeven']
    else:  # bear spreads
        profit_mask = prices_dist <= spread['breakeven']

    ax4.fill_between(prices_dist, pdf, where=profit_mask,
                     color=COLORS['green'], alpha=0.3, label='Profit Zone')

    ax4.set_xlabel('Stock Price at Expiration ($)')
    ax4.set_ylabel('Probability Density')
    ax4.set_title('Price Distribution at Expiry', fontsize=12, fontweight='bold')
    ax4.legend(loc='best', fontsize=8)
    ax4.grid(True, alpha=0.2)

    # --- Plot 5: Momentum Chart (middle right) ---
    ax5 = fig.add_subplot(gs[1, 2])

    returns = [momentum['return_1w'], momentum['return_1m'], momentum['return_3m']]
    labels = ['1W', '1M', '3M']
    colors = [COLORS['green'] if r > 0 else COLORS['red'] for r in returns]

    bars = ax5.bar(labels, [r * 100 for r in returns], color=colors, alpha=0.7, edgecolor=COLORS['fg'])
    ax5.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.3)

    # Add value labels
    for bar, val in zip(bars, returns):
        height = bar.get_height()
        ax5.text(bar.get_x() + bar.get_width()/2., height,
                f'{val*100:.1f}%', ha='center', va='bottom' if height > 0 else 'top',
                fontsize=9, color=COLORS['fg'])

    ax5.set_ylabel('Return (%)')
    ax5.set_title(f'Momentum (Score: {momentum["momentum_score"]:.2f})', fontsize=12, fontweight='bold')
    ax5.grid(True, alpha=0.2, axis='y')

    # --- Plot 6: Risk/Reward Visualization (bottom left) ---
    ax6 = fig.add_subplot(gs[2, 0])

    # Pie chart of probability
    sizes = [spread['prob_profit'], 1 - spread['prob_profit']]
    colors_pie = [COLORS['green'], COLORS['red']]
    labels_pie = [f'Win {spread["prob_profit"]*100:.1f}%', f'Lose {(1-spread["prob_profit"])*100:.1f}%']

    wedges, texts, autotexts = ax6.pie(sizes, colors=colors_pie, labels=labels_pie,
                                        autopct='', startangle=90,
                                        wedgeprops={'edgecolor': COLORS['fg'], 'linewidth': 1})
    ax6.set_title('Win/Lose Probability', fontsize=12, fontweight='bold')

    # --- Plot 7: Skew Metrics (bottom center) ---
    ax7 = fig.add_subplot(gs[2, 1])

    metrics = ['ATM IV', 'Realized Vol', 'Call Skew', 'Put Skew', 'VRP']
    values = [
        skew['atm_iv'] * 100,
        skew['realized_vol_30d'] * 100,
        skew['call_skew'] * 100,
        skew['put_skew'] * 100,
        skew['vrp'] * 100
    ]

    colors_bar = [COLORS['blue'], COLORS['cyan'], COLORS['magenta'], COLORS['magenta'],
                  COLORS['green'] if skew['vrp'] > 0 else COLORS['red']]

    y_pos = np.arange(len(metrics))
    bars = ax7.barh(y_pos, values, color=colors_bar, alpha=0.7, edgecolor=COLORS['fg'])
    ax7.set_yticks(y_pos)
    ax7.set_yticklabels(metrics)
    ax7.set_xlabel('Value (%)')
    ax7.set_title('Volatility Metrics', fontsize=12, fontweight='bold')
    ax7.axvline(0, color=COLORS['fg'], linestyle='-', alpha=0.3)
    ax7.grid(True, alpha=0.2, axis='x')

    # --- Plot 8: Filter Status (bottom right) ---
    ax8 = fig.add_subplot(gs[2, 2])
    ax8.axis('off')

    filters = [
        ('Skew Filter', scan_result['filters']['passes_skew_filter']),
        ('IV/RV Filter', scan_result['filters']['passes_ivrv_filter']),
        ('Momentum Filter', scan_result['filters']['passes_momentum_filter']),
    ]

    filter_text = "FILTER STATUS\n━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for name, passed in filters:
        status = "✓ PASS" if passed else "✗ FAIL"
        color = "green" if passed else "red"
        filter_text += f"{name}: {status}\n"

    filter_text += f"\n\nNotes: {scan_result['notes']}"

    ax8.text(0.05, 0.95, filter_text, transform=ax8.transAxes,
             fontsize=10, verticalalignment='top', fontfamily='monospace',
             color=COLORS['fg'])

    # Add title
    fig.suptitle(f'{scan_result["ticker"]} Vertical Spread Analysis',
                 fontsize=16, fontweight='bold', color=COLORS['fg'], y=0.98)

    save_figure(fig, output_file, dpi=300)
    plt.close()

    print(f"✓ Saved spread analysis plot: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Visualize vertical spread analysis')
    parser.add_argument('-t', '--ticker', type=str, required=True,
                        help='Stock ticker symbol')
    parser.add_argument('-d', '--data-dir', type=str, default='pricing/skew_verticals/data',
                        help='Data directory with options chain')
    parser.add_argument('-s', '--scan-dir', type=str, default='pricing/skew_verticals/output',
                        help='Directory with scan results')
    parser.add_argument('-o', '--output-dir', type=str, default='pricing/skew_verticals/output/plots',
                        help='Output directory for plots')

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    scan_dir = Path(args.scan_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    print(f"Loading scan results for {args.ticker}...")
    scan_result = load_scan_result(args.ticker, scan_dir)

    print(f"Loading options chain...")
    spot, calls_df, puts_df = load_options_chain(args.ticker, data_dir)

    print(f"Generating visualization...")
    output_file = output_dir / f"{args.ticker}_spread_analysis.png"
    plot_spread_analysis(scan_result, spot, calls_df, puts_df, output_file)

    return 0


if __name__ == '__main__':
    exit(main())

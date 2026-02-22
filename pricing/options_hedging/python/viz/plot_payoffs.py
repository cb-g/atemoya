#!/usr/bin/env python3
"""
Plot strategy payoff diagrams
"""

import argparse
import sys
import json
import traceback
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

# Apply dark theme
setup_dark_mode()
sns.set_palette([COLORS['blue'], COLORS['green'], COLORS['red'], COLORS['magenta']])


def parse_strategy_type(strategy_str):
    """Parse strategy type string from CSV"""
    if strategy_str.startswith('ProtectivePut'):
        strike = float(strategy_str.split('K=')[1].rstrip(')'))
        return ('protective_put', {'put_strike': strike})
    elif strategy_str.startswith('Collar'):
        parts = strategy_str.split(',')
        put_strike = float(parts[0].split('=')[1])
        call_strike = float(parts[1].split('=')[1].rstrip(')'))
        return ('collar', {'put_strike': put_strike, 'call_strike': call_strike})
    elif strategy_str.startswith('VerticalSpread'):
        parts = strategy_str.split(',')
        long_strike = float(parts[0].split('=')[1])
        short_strike = float(parts[1].split('=')[1].rstrip(')'))
        return ('vertical_spread', {'long_strike': long_strike, 'short_strike': short_strike})
    elif strategy_str.startswith('CoveredCall'):
        strike = float(strategy_str.split('K=')[1].rstrip(')'))
        return ('covered_call', {'call_strike': strike})
    else:
        raise ValueError(f"Unknown strategy type: {strategy_str}")


def compute_payoff(strategy_type, params, spot_at_expiry, position_size):
    """Compute strategy payoff at expiry"""
    stock_value = position_size * spot_at_expiry

    if strategy_type == 'protective_put':
        # Long stock + long put
        put_strike = params['put_strike']
        return position_size * max(spot_at_expiry, put_strike)

    elif strategy_type == 'collar':
        # Long stock + long put + short call
        put_strike = params['put_strike']
        call_strike = params['call_strike']
        clamped_spot = max(put_strike, min(spot_at_expiry, call_strike))
        return position_size * clamped_spot

    elif strategy_type == 'vertical_spread':
        # Long stock + long put + short put
        long_strike = params['long_strike']
        short_strike = params['short_strike']
        long_payoff = max(0, long_strike - spot_at_expiry)
        short_payoff = max(0, short_strike - spot_at_expiry)
        return stock_value + position_size * (long_payoff - short_payoff)

    elif strategy_type == 'covered_call':
        # Long stock + short call
        call_strike = params['call_strike']
        call_payoff = max(0, spot_at_expiry - call_strike)
        return stock_value - position_size * call_payoff

    else:
        return stock_value


def plot_payoff_diagram(strategy_data, output_file, spot, position_size=100, ticker=''):
    """
    Plot payoff diagram for a strategy

    2-panel chart:
    - Top: Payoff at expiry
    - Bottom: P&L (including premium paid)
    """
    strategy_type, params = parse_strategy_type(strategy_data['strategy_type'])
    cost = float(strategy_data['cost'])

    # Spot price range
    spot_range = np.linspace(0.6 * spot, 1.4 * spot, 200)

    # Unhedged payoff
    unhedged = spot_range * position_size

    # Hedged payoff
    hedged = np.array([
        compute_payoff(strategy_type, params, s, position_size)
        for s in spot_range
    ])

    # Create figure
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    fig.patch.set_facecolor(COLORS['bg'])
    for ax in (ax1, ax2):
        ax.set_facecolor(COLORS['bg'])

    # Payoff diagram (top)
    ax1.plot(spot_range, unhedged, '--', color=COLORS['gray'], label='Unhedged', linewidth=2)
    ax1.plot(spot_range, hedged, '-', color=COLORS['blue'], label='Hedged', linewidth=2.5)
    ax1.axvline(spot, color=COLORS['yellow'], linestyle=':', alpha=0.7, label='Current Spot')
    ax1.set_ylabel('Portfolio Value ($)', fontsize=12)
    title_prefix = f'{ticker} — ' if ticker else ''
    ax1.set_title(f'{title_prefix}Payoff Diagram - {strategy_data["strategy_type"]}', fontsize=14, fontweight='bold')
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.2)

    # P&L diagram (bottom)
    pnl_unhedged = unhedged - spot * position_size
    pnl_hedged = hedged - spot * position_size - cost

    ax2.plot(spot_range, pnl_unhedged, '--', color=COLORS['gray'], label='Unhedged', linewidth=2)
    ax2.plot(spot_range, pnl_hedged, '-', color=COLORS['green'], label='Hedged', linewidth=2.5)
    ax2.axhline(0, color=COLORS['fg'], linestyle='-', alpha=0.3)
    ax2.axvline(spot, color=COLORS['yellow'], linestyle=':', alpha=0.7, label='Current Spot')

    # Fill regions
    ax2.fill_between(spot_range, 0, pnl_hedged,
                      where=(pnl_hedged >= 0), alpha=0.2, color=COLORS['green'], interpolate=True)
    ax2.fill_between(spot_range, 0, pnl_hedged,
                      where=(pnl_hedged < 0), alpha=0.2, color=COLORS['red'], interpolate=True)

    ax2.set_xlabel('Spot Price at Expiry ($)', fontsize=12)
    ax2.set_ylabel('Profit/Loss ($)', fontsize=12)
    ax2.set_title('P&L (Including Hedge Cost)', fontsize=14, fontweight='bold')
    ax2.legend(loc='upper left')
    ax2.grid(True, alpha=0.2)

    # Add text box with strategy details
    info_text = f"Cost: ${cost:.2f}\nProtection: ${float(strategy_data['protection_level']):.2f}"
    ax1.text(0.98, 0.02, info_text, transform=ax1.transAxes,
             fontsize=10, verticalalignment='bottom', horizontalalignment='right',
             bbox=dict(boxstyle='round', facecolor=COLORS['bg'], alpha=0.8, edgecolor=COLORS['gray']))

    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    print(f"Saved payoff diagram to {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Plot strategy payoff diagrams')
    parser.add_argument('--ticker', help='Stock ticker (auto-detects underlying file)')
    parser.add_argument('--strategy-file', default='pricing/options_hedging/output/recommended_strategy.csv',
                       help='Strategy CSV file')
    parser.add_argument('--underlying-file', help='Underlying data file (overrides --ticker)')
    parser.add_argument('--data-dir', default='pricing/options_hedging/data', help='Data directory')
    parser.add_argument('--output-dir', default='pricing/options_hedging/output/plots',
                       help='Output directory')
    parser.add_argument('--position', type=float, default=100,
                       help='Position size (shares)')

    args = parser.parse_args()

    try:
        # Load strategy
        strategy_file = Path(args.strategy_file)
        if not strategy_file.exists():
            raise FileNotFoundError(f"Strategy file not found: {strategy_file}")

        df_strategy = pd.read_csv(strategy_file)
        strategy_data = df_strategy.set_index('field')['value'].to_dict()

        # Load underlying data for spot price
        if args.underlying_file:
            underlying_file = Path(args.underlying_file)
        elif args.ticker:
            underlying_file = Path(args.data_dir) / f"{args.ticker}_underlying.csv"
        else:
            # Auto-detect: find any *_underlying.csv in data dir
            data_dir = Path(args.data_dir)
            candidates = sorted(data_dir.glob('*_underlying.csv'), key=lambda p: p.stat().st_mtime, reverse=True)
            if not candidates:
                raise FileNotFoundError(f"No underlying data found in {data_dir}. Pass --ticker.")
            underlying_file = candidates[0]
        if not underlying_file.exists():
            raise FileNotFoundError(f"Underlying file not found: {underlying_file}")

        df_underlying = pd.read_csv(underlying_file)
        spot = df_underlying['spot_price'].iloc[0]

        # Create output directory
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Derive ticker from underlying file
        ticker = args.ticker or underlying_file.stem.replace('_underlying', '')

        # Plot payoff diagram
        output_file = output_dir / 'strategy_payoff.png'
        plot_payoff_diagram(strategy_data, output_file, spot, args.position, ticker=ticker)

        print(f"\n✓ Successfully generated payoff diagram")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

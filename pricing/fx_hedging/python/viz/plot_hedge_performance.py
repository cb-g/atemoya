#!/usr/bin/env python3
"""
Visualize FX/crypto hedging backtest results.

Usage:
    python plot_hedge_performance.py 6E
    python plot_hedge_performance.py BTC --output btc_hedge.png
    python plot_hedge_performance.py ETH --show-exposure
"""

import argparse
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

# Apply dark theme
setup_dark_mode()

# Contract names
CONTRACT_NAMES = {
    "6E": "EUR/USD", "6J": "JPY/USD", "6B": "GBP/USD",
    "6S": "CHF/USD", "6A": "AUD/USD", "6C": "CAD/USD",
    "M6E": "Micro EUR/USD", "M6J": "Micro JPY/USD", "M6B": "Micro GBP/USD",
    "M6S": "Micro CHF/USD", "M6A": "Micro AUD/USD", "M6C": "Micro CAD/USD",
    "BTC": "Bitcoin", "MBT": "Micro Bitcoin",
    "ETH": "Ethereum", "MET": "Micro Ether",
    "SOL": "Solana", "MSOL": "Micro Solana",
}

def load_backtest_results(contract_code: str) -> pd.DataFrame:
    """Load backtest results from CSV."""
    mod_root = Path(__file__).resolve().parent.parent.parent
    results_file = mod_root / "output" / f"{contract_code}_backtest.csv"

    if not results_file.exists():
        raise FileNotFoundError(
            f"Results file not found: {results_file}\n"
            f"Please run the backtest first:\n"
            f"  cd pricing/fx_hedging/ocaml\n"
            f"  dune exec fx_hedging -- -operation backtest -contract {contract_code}"
        )

    df = pd.read_csv(results_file)
    print(f"Loaded {len(df)} observations from {results_file}")

    return df

def load_exposure_analysis() -> pd.DataFrame:
    """Load portfolio exposure analysis if available."""
    mod_root = Path(__file__).resolve().parent.parent.parent
    exposure_file = mod_root / "output" / "exposure_analysis.csv"

    if exposure_file.exists():
        return pd.read_csv(exposure_file)
    return None

def plot_pnl_comparison(ax, df: pd.DataFrame, contract_name: str):
    """Plot hedged vs unhedged P&L over time."""
    ax.set_facecolor(COLORS['bg'])
    ax.plot(df['timestamp'], df['unhedged_pnl'],
            label='Unhedged P&L', color=COLORS['red'], linewidth=2, alpha=0.8)
    ax.plot(df['timestamp'], df['hedged_pnl'],
            label='Hedged P&L', color=COLORS['green'], linewidth=2, alpha=0.8)

    ax.axhline(y=0, color=COLORS['gray'], linestyle='--', alpha=0.5, linewidth=1)
    ax.fill_between(df['timestamp'], df['unhedged_pnl'], 0,
                     alpha=0.2, color=COLORS['red'])
    ax.fill_between(df['timestamp'], df['hedged_pnl'], 0,
                     alpha=0.2, color=COLORS['green'])

    ax.set_xlabel('Time (days)', fontsize=10, color=COLORS['fg'])
    ax.set_ylabel('P&L ($)', fontsize=10, color=COLORS['fg'])
    ax.set_title(f'{contract_name} Hedging Performance', fontsize=12, fontweight='bold', color=COLORS['fg'])
    ax.legend(loc='best', framealpha=0.9)
    ax.grid(True, alpha=0.2, linestyle='--', color=COLORS['gray'])
    ax.tick_params(colors=COLORS['fg'])

    # Add summary statistics
    final_unhedged = df['unhedged_pnl'].iloc[-1]
    final_hedged = df['hedged_pnl'].iloc[-1]

    textstr = f'Final Unhedged: ${final_unhedged:,.0f}\nFinal Hedged: ${final_hedged:,.0f}'
    props = dict(boxstyle='round', facecolor=COLORS['gray'], alpha=0.8, edgecolor=COLORS['fg'])
    ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', bbox=props, color=COLORS['fg'])

def plot_hedge_pnl(ax, df: pd.DataFrame):
    """Plot hedge-only P&L and transaction costs."""
    ax.set_facecolor(COLORS['bg'])
    ax.plot(df['timestamp'], df['hedge_pnl'],
            label='Futures P&L', color=COLORS['blue'], linewidth=2, alpha=0.8)
    ax.plot(df['timestamp'], -df['cumulative_costs'],
            label='Transaction Costs', color=COLORS['orange'], linewidth=1.5,
            linestyle='--', alpha=0.8)

    ax.axhline(y=0, color=COLORS['gray'], linestyle='--', alpha=0.5, linewidth=1)

    ax.set_xlabel('Time (days)', fontsize=10, color=COLORS['fg'])
    ax.set_ylabel('P&L ($)', fontsize=10, color=COLORS['fg'])
    ax.set_title('Hedge Performance & Costs', fontsize=12, fontweight='bold', color=COLORS['fg'])
    ax.legend(loc='best', framealpha=0.9)
    ax.grid(True, alpha=0.2, linestyle='--', color=COLORS['gray'])
    ax.tick_params(colors=COLORS['fg'])

def plot_fx_rates(ax, df: pd.DataFrame, contract_name: str):
    """Plot FX spot and futures prices."""
    ax.set_facecolor(COLORS['bg'])
    ax.plot(df['timestamp'], df['fx_rate'],
            label='Spot Rate', color=COLORS['purple'], linewidth=2, alpha=0.8)
    ax.plot(df['timestamp'], df['futures_price'],
            label='Futures Price', color=COLORS['cyan'], linewidth=1.5,
            linestyle='--', alpha=0.8)

    ax.set_xlabel('Time (days)', fontsize=10, color=COLORS['fg'])
    ax.set_ylabel('Price', fontsize=10, color=COLORS['fg'])
    ax.set_title(f'{contract_name} Spot vs Futures', fontsize=12, fontweight='bold', color=COLORS['fg'])
    ax.legend(loc='best', framealpha=0.9)
    ax.grid(True, alpha=0.2, linestyle='--', color=COLORS['gray'])
    ax.tick_params(colors=COLORS['fg'])

    # Calculate and display basis
    avg_basis = (df['futures_price'] - df['fx_rate']).mean()
    textstr = f'Avg Basis: {avg_basis:.6f}'
    props = dict(boxstyle='round', facecolor=COLORS['gray'], alpha=0.8, edgecolor=COLORS['fg'])
    ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', bbox=props, color=COLORS['fg'])

def plot_drawdowns(ax, df: pd.DataFrame):
    """Plot rolling drawdowns for hedged vs unhedged."""
    ax.set_facecolor(COLORS['bg'])
    # Calculate running drawdowns based on portfolio value (not raw P&L)
    base_value = df['exposure_value'].iloc[0]
    unhedged_value = base_value + df['unhedged_pnl']
    hedged_value = base_value + df['hedged_pnl']

    unhedged_dd = ((unhedged_value / unhedged_value.cummax()) - 1) * 100
    hedged_dd = ((hedged_value / hedged_value.cummax()) - 1) * 100

    ax.fill_between(df['timestamp'], unhedged_dd, 0,
                     alpha=0.3, color=COLORS['red'], label='Unhedged DD')
    ax.fill_between(df['timestamp'], hedged_dd, 0,
                     alpha=0.3, color=COLORS['green'], label='Hedged DD')

    ax.set_xlabel('Time (days)', fontsize=10, color=COLORS['fg'])
    ax.set_ylabel('Drawdown (%)', fontsize=10, color=COLORS['fg'])
    ax.set_title('Rolling Drawdowns', fontsize=12, fontweight='bold', color=COLORS['fg'])
    ax.legend(loc='best', framealpha=0.9)
    ax.grid(True, alpha=0.2, linestyle='--', color=COLORS['gray'])
    ax.tick_params(colors=COLORS['fg'])
    ax.axhline(y=0, color=COLORS['gray'], linestyle='--', alpha=0.5, linewidth=1)

def plot_margin_account(ax, df: pd.DataFrame):
    """Plot margin balance over time."""
    ax.set_facecolor(COLORS['bg'])
    ax.plot(df['timestamp'], df['margin_balance'],
            color=COLORS['yellow'], linewidth=2, alpha=0.8)
    ax.fill_between(df['timestamp'], df['margin_balance'], 0,
                     alpha=0.2, color=COLORS['yellow'])

    # Add margin call threshold if available
    if 'maintenance_margin' in df.columns:
        ax.axhline(y=df['maintenance_margin'].iloc[0],
                  color=COLORS['red'], linestyle='--', alpha=0.7, linewidth=1.5,
                  label='Maintenance Margin')
        ax.legend(loc='best', framealpha=0.9)

    ax.set_xlabel('Time (days)', fontsize=10, color=COLORS['fg'])
    ax.set_ylabel('Balance ($)', fontsize=10, color=COLORS['fg'])
    ax.set_title('Margin Account Balance', fontsize=12, fontweight='bold', color=COLORS['fg'])
    ax.grid(True, alpha=0.2, linestyle='--', color=COLORS['gray'])
    ax.tick_params(colors=COLORS['fg'])

    # Check for margin calls
    min_balance = df['margin_balance'].min()
    textstr = f'Min Balance: ${min_balance:,.0f}'
    box_color = COLORS['red'] if min_balance < 0 else COLORS['green']
    props = dict(boxstyle='round', facecolor=box_color, alpha=0.5, edgecolor=COLORS['fg'])
    ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', bbox=props, color=COLORS['fg'])

def plot_positions(ax, df: pd.DataFrame):
    """Plot futures positions over time."""
    ax.set_facecolor(COLORS['bg'])
    ax.plot(df['timestamp'], df['futures_position'],
            color=COLORS['purple'], linewidth=2, alpha=0.8, drawstyle='steps-post')
    ax.axhline(y=0, color=COLORS['gray'], linestyle='--', alpha=0.5, linewidth=1)

    ax.set_xlabel('Time (days)', fontsize=10, color=COLORS['fg'])
    ax.set_ylabel('Position (contracts)', fontsize=10, color=COLORS['fg'])
    ax.set_title('Futures Position', fontsize=12, fontweight='bold', color=COLORS['fg'])
    ax.grid(True, alpha=0.2, linestyle='--', color=COLORS['gray'])
    ax.tick_params(colors=COLORS['fg'])

def plot_hedge_payoff(ax, df: pd.DataFrame):
    """At-expiry payoff comparison: unhedged vs futures hedge vs put option hedge.

    Uses the actual spot range from the backtest to show how each strategy
    would perform across different spot outcomes at a 90-day horizon.
    """
    ax.set_facecolor(COLORS['bg'])

    spot_0 = df['fx_rate'].iloc[0]
    exposure = df['exposure_value'].iloc[0]
    n_contracts = abs(df['futures_position'].iloc[0])

    if n_contracts == 0 or spot_0 == 0:
        ax.text(0.5, 0.5, 'No hedge position', ha='center', va='center',
                transform=ax.transAxes, fontsize=10, color=COLORS['fg'])
        ax.axis('off')
        return

    # Infer contract size from data: exposure ≈ n_contracts × contract_size × spot
    contract_size = exposure / (n_contracts * spot_0)

    # Spot range: ±30% from initial
    spots = np.linspace(spot_0 * 0.7, spot_0 * 1.3, 200)
    pct_change = (spots - spot_0) / spot_0 * 100

    # Unhedged P&L
    unhedged = exposure * (spots - spot_0) / spot_0

    # Futures hedge P&L (short futures lock in the rate)
    futures_pnl = -n_contracts * contract_size * (spots - spot_0)
    hedged_futures = unhedged + futures_pnl

    # Put option hedge: 5% OTM put, 90d
    strike = spot_0 * 0.95
    # Estimate premium from historical vol
    returns = np.log(df['fx_rate'] / df['fx_rate'].shift(1)).dropna()
    vol = returns.std() * np.sqrt(252) if len(returns) > 20 else 0.10
    T = 90 / 365.0
    d1 = (np.log(spot_0 / strike) + 0.5 * vol**2 * T) / (vol * np.sqrt(T)) if vol > 0 else 10
    d2 = d1 - vol * np.sqrt(T)
    from scipy.stats import norm
    put_per_unit = np.exp(-0.05 * T) * (strike * norm.cdf(-d2) - spot_0 * norm.cdf(-d1))
    premium_total = put_per_unit * contract_size * n_contracts

    put_payoff = n_contracts * contract_size * np.maximum(strike - spots, 0)
    hedged_options = unhedged + put_payoff - premium_total

    ax.plot(pct_change, unhedged, color=COLORS['red'], linewidth=1.5,
            alpha=0.6, linestyle=':', label='Unhedged')
    ax.plot(pct_change, hedged_futures, color=COLORS['green'], linewidth=2,
            alpha=0.8, label='Futures')
    ax.plot(pct_change, hedged_options, color=COLORS['cyan'], linewidth=2,
            alpha=0.8, label=f'Put K={strike:.2f} (${premium_total:,.0f})')
    ax.axhline(y=0, color=COLORS['gray'], linestyle='--', alpha=0.4, linewidth=0.8)
    ax.axvline(x=0, color=COLORS['gray'], linestyle='--', alpha=0.4, linewidth=0.8)

    ax.set_xlabel('Spot Change (%)', fontsize=10, color=COLORS['fg'])
    ax.set_ylabel('P&L ($)', fontsize=10, color=COLORS['fg'])
    ax.set_title('Hedge Payoff at Expiry', fontsize=12, fontweight='bold', color=COLORS['fg'])
    ax.legend(loc='best', framealpha=0.9, fontsize=8)
    ax.grid(True, alpha=0.2, linestyle='--', color=COLORS['gray'])
    ax.tick_params(colors=COLORS['fg'])


def create_summary_table(ax, df: pd.DataFrame, contract_code: str):
    """Create summary statistics table."""
    ax.axis('off')
    ax.set_facecolor(COLORS['bg'])

    # Calculate statistics
    final_unhedged = df['unhedged_pnl'].iloc[-1]
    final_hedged = df['hedged_pnl'].iloc[-1]
    final_hedge = df['hedge_pnl'].iloc[-1]
    total_costs = df['cumulative_costs'].iloc[-1]

    # Calculate hedge effectiveness
    unhedged_vol = df['unhedged_pnl'].std()
    hedged_vol = df['hedged_pnl'].std()
    hedge_effectiveness = (1 - (hedged_vol / unhedged_vol)) * 100 if unhedged_vol > 0 else 0

    # Calculate max drawdowns based on portfolio value (exposure + P&L) to avoid
    # degenerate results when P&L starts at 0
    base_value = df['exposure_value'].iloc[0]
    unhedged_value = base_value + df['unhedged_pnl']
    hedged_value = base_value + df['hedged_pnl']
    max_dd_unhedged = ((unhedged_value / unhedged_value.cummax()) - 1).min() * 100
    max_dd_hedged = ((hedged_value / hedged_value.cummax()) - 1).min() * 100

    # Calculate Sharpe ratios (approximate)
    returns_unhedged = df['unhedged_pnl'].diff().dropna()
    returns_hedged = df['hedged_pnl'].diff().dropna()
    sharpe_unhedged = returns_unhedged.mean() / returns_unhedged.std() * np.sqrt(252) if returns_unhedged.std() > 0 else 0
    sharpe_hedged = returns_hedged.mean() / returns_hedged.std() * np.sqrt(252) if returns_hedged.std() > 0 else 0

    def fmt_pnl(v):
        if abs(v) >= 1_000_000:
            return f'${v / 1_000_000:.1f}M'
        if abs(v) >= 10_000:
            return f'${v / 1_000:.0f}K'
        return f'${v:,.0f}'

    def fmt_dd(v):
        if abs(v) > 999:
            return f'{v / 100:.0f}×'
        return f'{v:.1f}%'

    data = [
        ['Metric', 'Unhedged', 'Hedged', 'Hedge'],
        ['Final P&L', fmt_pnl(final_unhedged), fmt_pnl(final_hedged), fmt_pnl(final_hedge)],
        ['Volatility', fmt_pnl(unhedged_vol), fmt_pnl(hedged_vol), '-'],
        ['Max Drawdown', fmt_dd(max_dd_unhedged), fmt_dd(max_dd_hedged), '-'],
        ['Sharpe Ratio', f'{sharpe_unhedged:.2f}', f'{sharpe_hedged:.2f}', '-'],
        ['Transaction Costs', '-', fmt_pnl(total_costs), '-'],
        ['Effectiveness', '-', f'{hedge_effectiveness:.1f}%', '-'],
    ]

    table = ax.table(cellText=data, cellLoc='left', loc='center',
                     colWidths=[0.32, 0.22, 0.22, 0.22])
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 2)

    # Style header row
    for i in range(4):
        table[(0, i)].set_facecolor(COLORS['gray'])
        table[(0, i)].set_text_props(weight='bold', color=COLORS['fg'])
        table[(0, i)].set_edgecolor(COLORS['fg'])

    # Style data rows
    for i in range(1, len(data)):
        for j in range(4):
            table[(i, j)].set_facecolor(COLORS['bg'])
            table[(i, j)].set_text_props(color=COLORS['fg'])
            table[(i, j)].set_edgecolor(COLORS['gray'])

    ax.set_title(f'{CONTRACT_NAMES.get(contract_code, contract_code)} Summary Statistics',
                 fontsize=12, fontweight='bold', pad=20, color=COLORS['fg'])

def plot_exposure_breakdown(ax, exposure_df: pd.DataFrame):
    """Plot portfolio FX exposure breakdown."""
    ax.set_facecolor(COLORS['bg'])

    if exposure_df is None or len(exposure_df) == 0:
        ax.text(0.5, 0.5, 'No exposure data available',
                ha='center', va='center', transform=ax.transAxes, color=COLORS['fg'])
        ax.axis('off')
        return

    currencies = exposure_df['currency'].values
    exposures = exposure_df['net_exposure_usd'].values

    # Use Kanagawa colors for pie chart
    colors = [COLORS['blue'], COLORS['red'], COLORS['green'], COLORS['yellow'], COLORS['purple'], COLORS['cyan']]

    wedges, texts, autotexts = ax.pie(np.abs(exposures), labels=currencies, autopct='%1.1f%%',
                                        colors=colors[:len(currencies)], startangle=90)

    for text in texts:
        text.set_color(COLORS['fg'])

    for autotext in autotexts:
        autotext.set_color(COLORS['bg'])
        autotext.set_fontweight('bold')

    ax.set_title('Portfolio FX Exposure', fontsize=12, fontweight='bold', color=COLORS['fg'])

def main():
    parser = argparse.ArgumentParser(
        description="Visualize FX/crypto hedging backtest results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Plot EUR/USD hedging results
  python plot_hedge_performance.py 6E

  # Plot Bitcoin hedge and save to file
  python plot_hedge_performance.py BTC --output btc_hedge.png

  # Plot Ethereum with exposure analysis
  python plot_hedge_performance.py ETH --show-exposure
        """
    )

    parser.add_argument("contract", type=str,
                       help="Contract code (6E=EUR, 6J=JPY, BTC=Bitcoin, ETH=Ethereum)")
    parser.add_argument("--output", type=str, default=None,
                       help="Output file path (default: show plot)")
    parser.add_argument("--show-exposure", action="store_true",
                       help="Include portfolio exposure breakdown")

    args = parser.parse_args()

    try:
        # Load data
        df = load_backtest_results(args.contract)
        exposure_df = load_exposure_analysis() if args.show_exposure else None

        contract_name = CONTRACT_NAMES.get(args.contract, args.contract)

        # Create figure with Kanagawa background
        fig = plt.figure(figsize=(16, 10))
        fig.patch.set_facecolor(COLORS['bg'])
        gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.3, wspace=0.3,
                               width_ratios=[1, 1, 1])

        # Row 0: P&L comparison (full width)
        ax1 = fig.add_subplot(gs[0, :])
        # Row 1: Summary table, FX rates, Drawdowns
        ax2 = fig.add_subplot(gs[1, 0])
        ax4 = fig.add_subplot(gs[1, 1])
        ax5 = fig.add_subplot(gs[1, 2])
        # Row 2: Hedge P&L, Margin account, Hedge payoff
        ax3 = fig.add_subplot(gs[2, 0])
        ax6 = fig.add_subplot(gs[2, 1])
        ax8 = fig.add_subplot(gs[2, 2])

        # Generate plots
        plot_pnl_comparison(ax1, df, contract_name)
        create_summary_table(ax2, df, args.contract)
        plot_fx_rates(ax4, df, contract_name)
        plot_drawdowns(ax5, df)
        plot_hedge_pnl(ax3, df)
        plot_margin_account(ax6, df)
        plot_hedge_payoff(ax8, df)

        fig.suptitle(f'FX Hedging Analysis: {contract_name}',
                     fontsize=16, fontweight='bold', y=0.995, color=COLORS['fg'])

        # Save or show
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            save_figure(fig, output_path, dpi=300)
            print(f"Saved plot to: {output_path}")
        else:
            plt.show()

        print(f"\n✓ Visualization complete")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

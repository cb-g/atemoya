#!/usr/bin/env python3
"""
Plot crypto treasury valuation results.
"""

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from lib.python.theme import setup_dark_mode, save_figure, KANAGAWA_DRAGON as COLORS

setup_dark_mode()


def load_results(output_dir: Path) -> dict:
    """Load valuation results from JSON."""
    results_file = output_dir / "crypto_treasury_all.json"
    if not results_file.exists():
        raise FileNotFoundError(f"Results file not found: {results_file}. Run crypto_valuation.py first.")

    with open(results_file) as f:
        return json.load(f)


def plot_crypto_comparison(results: list, btc_price: float, eth_price: float, output_dir: Path):
    """Create comparison chart for crypto treasury companies."""

    # Filter out companies with extreme mNAV (not pure crypto plays)
    pure_crypto = [r for r in results if r["mnav"] < 20 and r["market_cap"] > 0]

    if not pure_crypto:
        print("No valid crypto treasury data to plot")
        return

    # Sort by mNAV
    pure_crypto.sort(key=lambda x: x["mnav"])

    tickers = [r["ticker"] for r in pure_crypto]
    premiums = [r["premium_pct"] for r in pure_crypto]
    btc_holdings = [r["btc_holdings"] for r in pure_crypto]
    eth_holdings = [r.get("eth_holdings", 0) for r in pure_crypto]
    holding_types = [r.get("holding_type", "BTC") for r in pure_crypto]
    debt_to_nav = [r.get("debt_to_nav", 0) for r in pure_crypto]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    fig.suptitle(
        f'Crypto Treasury Valuation \u2014 mNAV Model  '
        f'(BTC \\${btc_price:,.0f} | ETH \\${eth_price:,.0f})',
        fontsize=14, fontweight='bold')

    # --- 1. Premium/Discount (top-left) ---
    ax = axes[0, 0]
    colors_pd = [
        COLORS['green'] if p < 0
        else COLORS['red'] if p > 50
        else COLORS['yellow']
        for p in premiums
    ]
    # Clip extreme premiums for readability
    max_display = 500
    clipped = [min(p, max_display) for p in premiums]
    bars = ax.barh(tickers, clipped, color=colors_pd, edgecolor=COLORS['gray'], alpha=0.85)
    ax.axvline(x=0, color=COLORS['fg'], linewidth=0.5, alpha=0.4)
    ax.set_xlabel('Premium/Discount (%)')
    ax.set_title('mNAV Premium/Discount', fontsize=11, fontweight='bold')

    for bar, pct in zip(bars, premiums):
        x = bar.get_width()
        label = f'{pct:+.0f}%' if abs(pct) > 100 else f'{pct:+.1f}%'
        ax.text(x + 2, bar.get_y() + bar.get_height() / 2,
                label, va='center', ha='left', fontsize=8,
                color=COLORS['fg'])

    # --- 2. Holdings Value (top-right) ---
    ax = axes[0, 1]
    btc_values = [h * btc_price / 1e9 for h in btc_holdings]
    eth_values = [h * eth_price / 1e9 for h in eth_holdings]

    bars_btc = ax.barh(tickers, btc_values, color=COLORS['orange'],
                       edgecolor=COLORS['gray'], alpha=0.85, label='BTC')
    bars_eth = ax.barh(tickers, eth_values, left=btc_values,
                       color=COLORS['blue'], edgecolor=COLORS['gray'],
                       alpha=0.85, label='ETH')
    ax.set_xlabel('NAV ($B)')
    ax.set_title('Crypto Holdings Value', fontsize=11, fontweight='bold')
    ax.legend(loc='best', fontsize=8)

    for bar_btc, bar_eth, htype in zip(bars_btc, bars_eth, holding_types):
        total = bar_btc.get_width() + bar_eth.get_width()
        ax.text(total + 0.1, bar_btc.get_y() + bar_btc.get_height() / 2,
                f'({htype})', va='center', ha='left', fontsize=8,
                color=COLORS['gray'])

    # --- 3. Leverage (bottom-left) ---
    ax = axes[1, 0]
    colors_lev = [
        COLORS['green'] if d < 0.5
        else COLORS['red'] if d > 1.0
        else COLORS['yellow']
        for d in debt_to_nav
    ]
    ax.barh(tickers, debt_to_nav, color=colors_lev, edgecolor=COLORS['gray'], alpha=0.85)
    ax.axvline(x=1.0, color=COLORS['red'], linestyle='--', linewidth=1,
               alpha=0.7, label='Risk threshold')
    ax.set_xlabel('Debt / NAV')
    ax.set_title('Leverage (Debt/NAV)', fontsize=11, fontweight='bold')
    ax.legend(loc='best', fontsize=8)

    # --- 4. Summary Table (bottom-right) ---
    ax = axes[1, 1]
    ax.axis('off')
    ax.set_title('Crypto Treasury Summary', fontsize=11, fontweight='bold')

    headers = ['Ticker', 'Type', 'Price', 'mNAV', 'Signal']
    table_data = []
    for r in pure_crypto:
        table_data.append([
            r['ticker'],
            r.get('holding_type', 'BTC'),
            f"${r['price']:,.2f}",
            f"{r['mnav']:.2f}x",
            r['signal'],
        ])

    table = ax.table(cellText=table_data, colLabels=headers,
                     loc='center', cellLoc='center',
                     colWidths=[0.15, 0.12, 0.22, 0.18, 0.33])
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.1, 1.5)

    for key, cell in table.get_celld().items():
        cell.set_edgecolor(COLORS['gray'])
        if key[0] == 0:  # header
            cell.set_facecolor(COLORS['bg_light'])
            cell.set_text_props(fontweight='bold', color=COLORS['fg'])
        else:
            cell.set_facecolor(COLORS['bg'])
            cell.set_text_props(color=COLORS['fg'])
            # Color signal column
            if key[1] == 4:
                row_idx = key[0] - 1
                if row_idx < len(pure_crypto):
                    sc = pure_crypto[row_idx].get('signal_color', '')
                    if sc == 'green':
                        cell.set_facecolor(COLORS['green'])
                    elif sc == 'red':
                        cell.set_facecolor(COLORS['red'])
                    elif sc == 'yellow':
                        cell.set_facecolor(COLORS['yellow'])
                    cell.set_text_props(color=COLORS['fg'], fontweight='bold')

    plt.tight_layout()
    output_file = output_dir / 'crypto_treasury_comparison'
    save_figure(fig, output_file, dpi=150)
    plt.close()


def main():
    output_dir = Path(__file__).parent.parent / "output"

    try:
        data = load_results(output_dir)
        btc_price = data["btc_price"]
        eth_price = data.get("eth_price", 0)
        results = data["results"]

        plot_crypto_comparison(results, btc_price, eth_price, output_dir)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Visualize earnings volatility analysis.

Creates:
1. IV term structure curve
2. IV vs RV comparison
3. Price history with realized vol
4. Filter status and recommendation
"""

import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure


def setup_dark_style():
    """Configure matplotlib for dark mode."""
    setup_dark_mode()


def load_data(ticker: str, data_dir: Path) -> tuple:
    """Load all data files."""
    # Load earnings info
    earnings_file = data_dir / f'{ticker}_earnings.csv'
    earnings_df = pd.read_csv(earnings_file)

    # Load IV term structure
    iv_file = data_dir / f'{ticker}_iv_term.csv'
    iv_df = pd.read_csv(iv_file)

    # Load price history
    prices_file = data_dir / f'{ticker}_prices.csv'
    prices_df = pd.read_csv(prices_file)

    return earnings_df, iv_df, prices_df


def calculate_realized_vol(prices: np.ndarray, window: int = 30) -> float:
    """Calculate annualized realized volatility."""
    if len(prices) < window + 1:
        return 0.0

    returns = np.diff(prices[-window-1:]) / prices[-window-1:-1]
    return np.std(returns) * np.sqrt(252)


def calculate_rolling_vol(prices: np.ndarray, window: int = 30) -> np.ndarray:
    """Calculate rolling realized volatility."""
    if len(prices) < window + 1:
        return np.array([])

    rolling_vol = []
    for i in range(window, len(prices)):
        returns = np.diff(prices[i-window:i+1]) / prices[i-window:i]
        vol = np.std(returns) * np.sqrt(252)
        rolling_vol.append(vol)

    return np.array(rolling_vol)


def apply_filters(term_slope: float, volume: float, iv_rv_ratio: float) -> dict:
    """Apply filter criteria."""
    min_term_slope = -0.05
    min_volume = 1_000_000
    min_iv_rv_ratio = 1.1

    passes_term = term_slope >= min_term_slope
    passes_volume = volume >= min_volume
    passes_iv_rv = iv_rv_ratio >= min_iv_rv_ratio

    all_pass = passes_term and passes_volume and passes_iv_rv

    if all_pass:
        recommendation = "TRADE"
    elif passes_volume and (passes_term or passes_iv_rv):
        recommendation = "CONSIDER"
    else:
        recommendation = "AVOID"

    return {
        'passes_term': passes_term,
        'passes_volume': passes_volume,
        'passes_iv_rv': passes_iv_rv,
        'recommendation': recommendation,
    }


def plot_earnings_vol_analysis(ticker: str, earnings_df: pd.DataFrame,
                                iv_df: pd.DataFrame, prices_df: pd.DataFrame,
                                output_file: Path, data_dir: Path = None):
    """Create comprehensive earnings volatility visualization."""
    setup_dark_style()

    fig = plt.figure(figsize=(16, 12))
    gs = fig.add_gridspec(3, 3, hspace=0.35, wspace=0.3)

    # Extract data
    earnings = earnings_df.iloc[0]
    spot = earnings['spot_price']
    earnings_date = earnings['earnings_date']
    days_to_earnings = earnings['days_to_earnings']
    volume = earnings['avg_volume_30d']

    # IV term structure
    dtes = iv_df['days_to_expiry'].values
    ivs = iv_df['atm_iv'].values * 100

    # Price history
    prices = prices_df['price'].values

    # Calculate metrics
    front_iv = ivs[0] if len(ivs) > 0 else 0
    back_iv = ivs[-1] if len(ivs) > 0 else 0

    # Term structure slope (change per day)
    if len(dtes) >= 2:
        term_slope = (ivs[-1] - ivs[0]) / (dtes[-1] - dtes[0]) / 100
    else:
        term_slope = 0

    # Term ratio
    term_ratio = front_iv / back_iv if back_iv > 0 else 1.0

    # Realized volatility
    realized_vol = calculate_realized_vol(prices) * 100
    iv_rv_ratio = front_iv / realized_vol if realized_vol > 0 else 1.0

    # Apply filters
    filters = apply_filters(term_slope, volume, iv_rv_ratio)

    # --- Plot 1: IV Term Structure (top left, spans 2 cols) ---
    ax1 = fig.add_subplot(gs[0, :2])

    ax1.plot(dtes, ivs, 'o-', color=COLORS['cyan'], markersize=10, linewidth=2,
             markeredgecolor=COLORS['fg'], markeredgewidth=2, label='ATM IV')

    # Add trend line
    z = np.polyfit(dtes, ivs, 1)
    p = np.poly1d(z)
    ax1.plot(dtes, p(dtes), '--', color=COLORS['yellow'], linewidth=2,
             label=f'Trend (slope: {term_slope*100:.3f}%/day)')

    # Mark earnings date
    if days_to_earnings <= max(dtes):
        ax1.axvline(days_to_earnings, color=COLORS['red'], linestyle='--',
                    alpha=0.7, label=f'Earnings ({days_to_earnings}d)')

    # Shade contango/backwardation
    if term_slope > 0:
        ax1.fill_between(dtes, ivs, ivs[0], alpha=0.1, color=COLORS['green'],
                         label='Contango')
    else:
        ax1.fill_between(dtes, ivs, ivs[-1], alpha=0.1, color=COLORS['red'],
                         label='Backwardation')

    ax1.set_xlabel('Days to Expiration')
    ax1.set_ylabel('Implied Volatility (%)')
    ax1.set_title('IV Term Structure', fontsize=14, fontweight='bold')
    ax1.legend(loc='best', fontsize=9)
    ax1.grid(True, alpha=0.2)

    # --- Plot 2: Summary Panel (top right) ---
    ax2 = fig.add_subplot(gs[0, 2])
    ax2.axis('off')

    rec_color = COLORS['green'] if filters['recommendation'] == 'TRADE' else \
                COLORS['yellow'] if filters['recommendation'] == 'CONSIDER' else COLORS['red']

    # Timing warning
    timing_warn = ''
    if days_to_earnings < 5:
        timing_warn = f'\nTOO CLOSE ({days_to_earnings}d)\nlimited entry window'
    elif days_to_earnings > 45:
        timing_warn = f'\nTOO FAR ({days_to_earnings}d)\nvol crush uncertain'

    summary_text = f"""{ticker} EARNINGS VOL
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Earnings: {earnings_date}
Days to Earnings: {days_to_earnings}
Spot: ${spot:.2f}

TERM STRUCTURE
Front IV: {front_iv:.1f}%
Back IV: {back_iv:.1f}%
Term Slope: {term_slope*100:.3f}%/day
Term Ratio: {term_ratio:.2f}x

IV vs REALIZED
Implied Vol: {front_iv:.1f}%
Realized Vol: {realized_vol:.1f}%
IV/RV Ratio: {iv_rv_ratio:.2f}x

VOLUME
30d Avg: {volume/1e6:.1f}M

{filters['recommendation']}"""

    ax2.text(0.05, 0.98, summary_text, transform=ax2.transAxes,
             fontsize=9, verticalalignment='top', fontfamily='monospace',
             color=COLORS['fg'], linespacing=1.1)

    if timing_warn:
        ax2.text(0.95, 0.98, timing_warn, transform=ax2.transAxes,
                 fontsize=7, verticalalignment='top', ha='right',
                 fontfamily='monospace', color=COLORS['bg'],
                 bbox=dict(boxstyle='round,pad=0.4', facecolor=COLORS['orange'],
                           edgecolor=COLORS['orange'], alpha=0.9))

    # --- Plot 3: IV vs RV Comparison (middle left) ---
    ax3 = fig.add_subplot(gs[1, 0])

    labels = ['Implied Vol', 'Realized Vol']
    values = [front_iv, realized_vol]
    colors_bar = [COLORS['blue'], COLORS['green']]

    bars = ax3.bar(labels, values, color=colors_bar, alpha=0.7, edgecolor=COLORS['fg'])

    # Add IV/RV ratio annotation
    ax3.axhline(realized_vol, color=COLORS['green'], linestyle='--', alpha=0.5)

    # Value labels
    for bar, val in zip(bars, values):
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                f'{val:.1f}%', ha='center', va='bottom', fontsize=11, color=COLORS['fg'])

    ax3.set_ylabel('Volatility (%)')
    ax3.set_title(f'IV vs RV (Ratio: {iv_rv_ratio:.2f}x)', fontsize=12, fontweight='bold')
    ax3.grid(True, alpha=0.2, axis='y')

    # --- Plot 4: Price History (middle center) ---
    ax4 = fig.add_subplot(gs[1, 1])

    ax4.plot(prices, color=COLORS['cyan'], linewidth=1.5)
    ax4.axhline(spot, color=COLORS['yellow'], linestyle='--', alpha=0.7,
                label=f'Current ${spot:.2f}')

    ax4.set_xlabel('Trading Days')
    ax4.set_ylabel('Price ($)')
    ax4.set_title('Price History', fontsize=12, fontweight='bold')
    ax4.legend(loc='best', fontsize=8)
    ax4.grid(True, alpha=0.2)

    # --- Plot 5: Rolling Volatility (middle right) ---
    ax5 = fig.add_subplot(gs[1, 2])

    rolling_vol = calculate_rolling_vol(prices, window=30) * 100

    if len(rolling_vol) > 0:
        ax5.plot(rolling_vol, color=COLORS['green'], linewidth=1.5, label='30d RV')
        ax5.axhline(front_iv, color=COLORS['blue'], linestyle='--', alpha=0.7,
                    label=f'Current IV ({front_iv:.1f}%)')
        ax5.axhline(realized_vol, color=COLORS['green'], linestyle=':', alpha=0.7,
                    label=f'Current RV ({realized_vol:.1f}%)')

    ax5.set_xlabel('Trading Days')
    ax5.set_ylabel('Volatility (%)')
    ax5.set_title('Rolling Realized Volatility', fontsize=12, fontweight='bold')
    ax5.legend(loc='best', fontsize=8)
    ax5.grid(True, alpha=0.2)

    # --- Plot 6: Filter Status (bottom left) ---
    ax6 = fig.add_subplot(gs[2, 0])
    ax6.set_xlim(0, 1)
    ax6.set_ylim(-0.5, 3.5)
    ax6.axis('off')

    filter_names = ['Term Slope', 'Volume', 'IV/RV Ratio']
    filter_values = [f'{term_slope*100:.3f}%/d', f'{volume/1e6:.1f}M', f'{iv_rv_ratio:.2f}x']
    filter_thresholds = ['≥ −0.05', '≥ 1M', '≥ 1.1']
    filter_status = [filters['passes_term'], filters['passes_volume'], filters['passes_iv_rv']]

    # Overall recommendation at top
    ax6.text(0.5, 3.2, filters['recommendation'], transform=ax6.transData,
             ha='center', va='center', fontsize=14, fontweight='bold', color=rec_color)

    for i, (name, value, thresh, passed) in enumerate(
            zip(filter_names, filter_values, filter_thresholds, filter_status)):
        y = 2.0 - i * 0.9
        color = COLORS['green'] if passed else COLORS['red']
        symbol = '●' if passed else '○'
        ax6.text(0.08, y, symbol, transform=ax6.transData,
                 ha='left', va='center', fontsize=16, color=color)
        ax6.text(0.22, y, name, transform=ax6.transData,
                 ha='left', va='center', fontsize=10, color=COLORS['fg'])
        ax6.text(0.92, y, f'{value}', transform=ax6.transData,
                 ha='right', va='center', fontsize=10, fontweight='bold', color=color)
        ax6.text(0.92, y - 0.3, f'(thresh: {thresh})', transform=ax6.transData,
                 ha='right', va='center', fontsize=7, color=COLORS['fg'], alpha=0.5)

    ax6.set_title('Trade Premise Check', fontsize=12, fontweight='bold')

    # --- Plot 7: IV Smile / Data Source Notice (bottom center) ---
    ax7 = fig.add_subplot(gs[2, 1])

    # Check for real strike-level IV data (from IBKR)
    smile_file = data_dir / f'{ticker}_iv_smile.csv' if data_dir else None
    has_real_smile = smile_file is not None and smile_file.exists()

    if has_real_smile:
        smile_df = pd.read_csv(smile_file)
        ax7.plot(smile_df['strike'], smile_df['iv'] * 100, 'o-',
                 color=COLORS['magenta'], markersize=8, linewidth=2,
                 markeredgecolor=COLORS['fg'])
        ax7.axvline(spot, color=COLORS['yellow'], linestyle='--', alpha=0.7,
                    label=f'Spot ${spot:.0f}')
        ax7.set_xlabel('Strike ($)')
        ax7.set_ylabel('Implied Volatility (%)')
        ax7.set_title('IV Smile (IBKR)', fontsize=12, fontweight='bold')
        ax7.legend(loc='best', fontsize=8)
        ax7.grid(True, alpha=0.2)
    else:
        ax7.axis('off')
        notice = (
            "IV SMILE\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Requires IBKR market data.\n"
            "yfinance provides ATM IV\n"
            "per expiration only — no\n"
            "strike-level smile data.\n"
            "\n"
            "PREMIUM & SIZING\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Contract counts use synthetic\n"
            "premium estimates. With IBKR\n"
            "credentials, real chain prices\n"
            "and smile data are fetched\n"
            "automatically."
        )
        ax7.text(0.05, 0.95, notice, transform=ax7.transAxes,
                 fontsize=9, verticalalignment='top', fontfamily='monospace',
                 color=COLORS['fg'], alpha=0.7, linespacing=1.2)

    # --- Plot 8: Trade Thesis (bottom right) ---
    ax8 = fig.add_subplot(gs[2, 2])
    ax8.axis('off')

    # Position recommendation
    if iv_rv_ratio > 1.2 and term_slope < 0:
        position = "SHORT STRADDLE"
        thesis = "• IV elevated vs RV\n• Term backwardation\n• Sell premium"
    elif iv_rv_ratio > 1.1:
        position = "LONG CALENDAR"
        thesis = "• IV premium exists\n• Sell front, buy back\n• Theta positive"
    else:
        position = "NO TRADE"
        thesis = "• Insufficient edge\n• Wait for better setup"

    stats_text = f"""TRADE RECOMMENDATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Position: {position}

THESIS
{thesis}

FILTER CRITERIA
Term Slope ≥ -0.05: {term_slope:.4f}
Volume ≥ 1M: {volume/1e6:.1f}M
IV/RV ≥ 1.1: {iv_rv_ratio:.2f}

RISK MANAGEMENT
• Size: 2-4% of portfolio
• Max loss: Premium paid
• Exit: Before earnings
• Adjust if IV spikes"""

    ax8.text(0.05, 0.95, stats_text, transform=ax8.transAxes,
             fontsize=9, verticalalignment='top', fontfamily='monospace',
             color=COLORS['fg'], linespacing=1.2)

    # Main title
    fig.suptitle(f'{ticker} Earnings Volatility Analysis',
                 fontsize=16, fontweight='bold', color=COLORS['fg'], y=0.98)

    save_figure(fig, output_file, dpi=300)
    plt.close()

    print(f"✓ Saved earnings vol analysis plot: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Visualize earnings volatility analysis')
    parser.add_argument('-t', '--ticker', type=str, default='NVDA',
                        help='Stock ticker symbol')
    parser.add_argument('-d', '--data-dir', type=str, default='data',
                        help='Data directory')
    parser.add_argument('-o', '--output-dir', type=str, default='pricing/earnings_vol/output/plots',
                        help='Output directory for plots')

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading data for {args.ticker}...")
    earnings_df, iv_df, prices_df = load_data(args.ticker, data_dir)

    print(f"Generating visualization...")
    output_file = output_dir / f"{args.ticker}_earnings_vol.png"
    plot_earnings_vol_analysis(args.ticker, earnings_df, iv_df, prices_df, output_file,
                               data_dir=data_dir)

    return 0


if __name__ == '__main__':
    exit(main())

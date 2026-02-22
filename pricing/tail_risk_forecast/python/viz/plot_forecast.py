#!/usr/bin/env python3
"""
Tail Risk Forecast Visualization

Creates a 2x2 dashboard showing:
1. VaR/ES risk gauges
2. Volatility forecast with confidence bands
3. HAR model coefficients
4. Risk metrics summary
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

setup_dark_mode()


def load_forecast(path: str) -> dict:
    """Load forecast JSON file."""
    with open(path) as f:
        return json.load(f)


def draw_risk_gauge(ax, var_95: float, var_99: float, es_95: float, es_99: float):
    """Draw VaR/ES risk gauge visualization."""
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('Value-at-Risk & Expected Shortfall', fontsize=12, fontweight='bold')

    # Risk level thresholds (annualized basis for interpretation)
    var_95_pct = var_95 * 100
    var_99_pct = var_99 * 100
    es_95_pct = es_95 * 100
    es_99_pct = es_99 * 100

    # Color based on VaR 95% level
    if var_95_pct < 2:
        color = COLORS['green']  # Green - low risk
        risk_label = 'LOW'
    elif var_95_pct < 4:
        color = COLORS['yellow']  # Yellow - moderate
        risk_label = 'MODERATE'
    elif var_95_pct < 6:
        color = COLORS['orange']  # Orange - elevated
        risk_label = 'ELEVATED'
    else:
        color = COLORS['red']  # Red - high
        risk_label = 'HIGH'

    # Draw main risk indicator circle
    circle = plt.Circle((2.5, 3), 2, color=color, alpha=0.3)
    ax.add_patch(circle)
    circle_border = plt.Circle((2.5, 3), 2, fill=False, color=color, linewidth=3)
    ax.add_patch(circle_border)

    # Risk label in circle
    ax.text(2.5, 3.5, risk_label, ha='center', va='center', fontsize=14, fontweight='bold', color=color)
    ax.text(2.5, 2.5, 'RISK', ha='center', va='center', fontsize=10, color=COLORS['gray'])

    # VaR/ES values on the right
    ax.text(6, 5, 'Next-Day Risk Metrics', ha='left', va='center', fontsize=10, fontweight='bold')

    ax.text(6, 4.2, f'VaR 95%:', ha='left', va='center', fontsize=9)
    ax.text(9, 4.2, f'{var_95_pct:.2f}%', ha='right', va='center', fontsize=9, fontweight='bold')

    ax.text(6, 3.6, f'VaR 99%:', ha='left', va='center', fontsize=9)
    ax.text(9, 3.6, f'{var_99_pct:.2f}%', ha='right', va='center', fontsize=9, fontweight='bold')

    ax.text(6, 2.8, f'ES 95%:', ha='left', va='center', fontsize=9)
    ax.text(9, 2.8, f'{es_95_pct:.2f}%', ha='right', va='center', fontsize=9, fontweight='bold')

    ax.text(6, 2.2, f'ES 99%:', ha='left', va='center', fontsize=9)
    ax.text(9, 2.2, f'{es_99_pct:.2f}%', ha='right', va='center', fontsize=9, fontweight='bold')

    # Interpretation
    ax.text(5, 0.3, f'5% chance of losing more than {var_95_pct:.1f}% tomorrow',
            ha='center', va='center', fontsize=10, style='italic', color=COLORS['fg'])


def draw_volatility_forecast(ax, vol_forecast: float, rv_forecast: float, ticker: str):
    """Draw volatility forecast with annualized context."""
    ax.set_title('Volatility Forecast', fontsize=12, fontweight='bold')

    # Annualize
    daily_vol = vol_forecast * 100
    annual_vol = vol_forecast * np.sqrt(252) * 100

    # Bar chart showing daily vs annualized
    categories = ['Daily\nVolatility', 'Annualized\nVolatility']
    values = [daily_vol, annual_vol]
    bar_colors = [COLORS['blue'], COLORS['cyan']]

    bars = ax.bar(categories, values, color=bar_colors, alpha=0.7, edgecolor=COLORS['fg'])

    # Add value labels
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f'{val:.1f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax.set_ylabel('Volatility (%)', fontsize=10)
    ax.set_ylim(0, max(values) * 1.3)

    # Add RV annotation
    ax.text(0.95, 0.95, f'RV: {rv_forecast*10000:.1f} bps', transform=ax.transAxes,
            ha='right', va='top', fontsize=9, color=COLORS['gray'])


def draw_har_coefficients(ax, har_model: dict):
    """Draw HAR model coefficients bar chart."""
    ax.set_title('HAR-RV Model Coefficients', fontsize=12, fontweight='bold')

    coefs = ['β_daily', 'β_weekly', 'β_monthly']
    values = [har_model['beta_daily'], har_model['beta_weekly'], har_model['beta_monthly']]

    bar_colors = [COLORS['green'], COLORS['blue'], COLORS['magenta']]
    bars = ax.bar(coefs, values, color=bar_colors, alpha=0.7, edgecolor=COLORS['fg'])

    ax.axhline(y=0, color=COLORS['fg'], linestyle='-', linewidth=0.5, alpha=0.5)
    ax.set_ylabel('Coefficient', fontsize=10)

    # Add value labels — inside bar if tall enough, outside otherwise
    y_min, y_max = ax.get_ylim()
    bar_threshold = (y_max - y_min) * 0.2
    for bar, val in zip(bars, values):
        x_center = bar.get_x() + bar.get_width() / 2
        if abs(val) > bar_threshold:
            # Label inside bar
            y_pos = bar.get_height() * 0.5
            ax.text(x_center, y_pos, f'{val:.3f}',
                    ha='center', va='center', fontsize=9, fontweight='bold')
        else:
            # Label outside bar
            y_pos = bar.get_height() + 0.02 if val >= 0 else bar.get_height() - 0.05
            ax.text(x_center, y_pos, f'{val:.3f}',
                    ha='center', va='bottom' if val >= 0 else 'top', fontsize=9)

    # R-squared annotation
    r_sq = har_model.get('r_squared', 0)
    ax.text(0.95, 0.95, f'R² = {r_sq:.3f}', transform=ax.transAxes,
            ha='right', va='top', fontsize=9,
            bbox=dict(boxstyle='round', facecolor=COLORS['bg_light'], edgecolor=COLORS['gray'], alpha=0.8))


def draw_summary(ax, data: dict):
    """Draw summary statistics table."""
    ax.axis('off')
    ax.set_title('Analysis Summary', fontsize=12, fontweight='bold')

    forecast = data['forecast']

    rows = [
        ['Ticker', data['ticker']],
        ['Analysis Date', data['analysis_date']],
        ['Observations', str(data['total_observations'])],
        ['Jump Intensity', f"{data['jump_intensity']*100:.1f}%"],
        ['Jump Adjusted', 'Yes' if forecast['jump_adjusted'] else 'No'],
    ]

    table = ax.table(cellText=rows, loc='center', cellLoc='left',
                     colWidths=[0.5, 0.5])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.8)

    # Style the table with Kanagawa colors
    for i in range(len(rows)):
        table[(i, 0)].set_facecolor(COLORS['bg_light'])
        table[(i, 0)].set_text_props(fontweight='bold', color=COLORS['fg'])
        table[(i, 1)].set_facecolor(COLORS['bg'])
        table[(i, 1)].set_text_props(color=COLORS['fg'])


def plot_forecast(data: dict, output_path: str):
    """Create the full forecast visualization."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.suptitle(f'Tail Risk Forecast - {data["ticker"]}', fontsize=14, fontweight='bold')

    forecast = data['forecast']
    har_model = data['har_model']

    # 1. Risk gauge (top-left)
    draw_risk_gauge(axes[0, 0],
                    forecast['var_95'], forecast['var_99'],
                    forecast['es_95'], forecast['es_99'])

    # 2. Volatility forecast (top-right)
    draw_volatility_forecast(axes[0, 1], forecast['vol_forecast'],
                             forecast['rv_forecast'], data['ticker'])

    # 3. HAR coefficients (bottom-left)
    draw_har_coefficients(axes[1, 0], har_model)

    # 4. Summary (bottom-right)
    draw_summary(axes[1, 1], data)

    plt.tight_layout()
    save_figure(fig, output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Plot tail risk forecast')
    parser.add_argument('--input', required=True, help='Input forecast JSON file')
    parser.add_argument('--output', help='Output PNG path')
    args = parser.parse_args()

    data = load_forecast(args.input)
    ticker = data['ticker']

    if args.output:
        output_path = args.output
    else:
        output_dir = Path(__file__).resolve().parent.parent.parent / "output" / "plots"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f'{ticker}_tail_risk.png')

    plot_forecast(data, output_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())

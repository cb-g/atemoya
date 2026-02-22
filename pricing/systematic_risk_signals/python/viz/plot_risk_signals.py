#!/usr/bin/env python3
"""
Systematic Risk Signals Visualization

Creates a 2x2 dashboard showing:
1. Risk regime gauge
2. Eigenvalue concentration (absorption ratio)
3. Network centrality distribution
4. Signal history over time
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


def load_result(path: str) -> dict:
    """Load risk signals result JSON file."""
    with open(path) as f:
        return json.load(f)


def draw_regime_gauge(ax, regime: str, transition_prob: float):
    """Draw current risk regime as a gauge."""
    C = COLORS
    ax.set_title('Current Risk Regime', fontsize=11, fontweight='bold')
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.set_aspect('equal', adjustable='datalim')
    ax.axis('off')

    regime_colors = {
        'Low Risk': C['green'],
        'Normal': C['blue'],
        'Elevated': C['yellow'],
        'High Risk': C['red'],
        'Crisis': C['magenta']
    }

    color = regime_colors.get(regime, C['gray'])

    circle = plt.Circle((5, 3.5), 2, color=color, alpha=0.3)
    ax.add_patch(circle)
    circle_border = plt.Circle((5, 3.5), 2, fill=False, color=color, linewidth=4)
    ax.add_patch(circle_border)

    ax.text(5, 3.5, regime.upper(), ha='center', va='center',
            fontsize=14, fontweight='bold', color=color)

    ax.text(5, 1, f'Transition Probability: {transition_prob*100:.1f}%',
            ha='center', va='center', fontsize=10, color=C['gray'])

    levels = ['Low', 'Normal', 'Elevated', 'High', 'Crisis']
    level_colors = [C['green'], C['blue'], C['yellow'], C['red'], C['magenta']]

    for i, (level, c) in enumerate(zip(levels, level_colors)):
        x = 1 + i * 2
        rect = mpatches.Rectangle((x - 0.4, 0.2), 0.8, 0.4, color=c, alpha=0.5)
        ax.add_patch(rect)
        ax.text(x, 0.1, level, ha='center', va='top', fontsize=7)


def draw_eigenvalue_analysis(ax, signals: dict):
    """Draw eigenvalue concentration (absorption ratio)."""
    C = COLORS
    ax.set_title('Eigenvalue Concentration', fontsize=11, fontweight='bold')

    var_first = signals.get('var_explained_first', 0) * 100
    var_2_to_5 = signals.get('var_explained_2_to_5', 0) * 100
    var_rest = max(0, 100 - var_first - var_2_to_5)

    sizes = [var_first, var_2_to_5, var_rest]
    labels = [f'PC1\n{var_first:.1f}%', f'PC2-5\n{var_2_to_5:.1f}%', f'Rest\n{var_rest:.1f}%']
    pie_colors = [C['red'], C['orange'], C['blue']]
    explode = (0.05, 0, 0)

    ax.pie(sizes, explode=explode, labels=labels, colors=pie_colors,
           autopct='', startangle=90, textprops={'fontsize': 9, 'color': C['fg']})

    if var_first > 50:
        interpretation = "HIGH concentration\n(Systemic risk elevated)"
        interp_color = C['red']
    elif var_first > 30:
        interpretation = "MODERATE concentration\n(Monitor closely)"
        interp_color = C['yellow']
    else:
        interpretation = "LOW concentration\n(Diversification working)"
        interp_color = C['green']

    ax.text(0, -1.4, interpretation, ha='center', va='top',
            fontsize=9, color=interp_color, fontweight='bold')


def draw_centrality_distribution(ax, centralities: list, signals: dict):
    """Draw eigenvector centrality distribution."""
    C = COLORS
    ax.set_title('Network Centrality Distribution', fontsize=11, fontweight='bold')

    mean_c = signals.get('mean_eigenvector_centrality', 0)
    std_c = signals.get('std_eigenvector_centrality', 0)

    if not centralities:
        ax.text(0.5, 0.5, 'No centrality data', ha='center', va='center',
                transform=ax.transAxes, fontsize=12, color=C['gray'])
        return

    # Histogram of centralities
    ax.hist(centralities, bins=15, color=C['blue'], alpha=0.7, edgecolor=C['bg_light'])

    # Mean line
    ax.axvline(x=mean_c, color=C['orange'], linestyle='--', linewidth=2,
               label=f'Mean: {mean_c:.3f}')

    # ±1 std range
    ax.axvspan(mean_c - std_c, mean_c + std_c, alpha=0.2, color=C['orange'],
               label=f'±1σ: {std_c:.3f}')

    ax.set_xlabel('Eigenvector Centrality')
    ax.set_ylabel('Count')
    ax.legend(loc='upper right', fontsize=8)


def draw_summary_metrics(ax, data: dict):
    """Draw summary metrics table."""
    C = COLORS
    ax.axis('off')
    ax.set_title('Risk Signal Summary', fontsize=11, fontweight='bold')

    signals = data.get('latest_signals', {})
    config = data.get('config', {})
    tickers = data.get('tickers', config.get('tickers', []))

    rows = [
        ['Analysis Date', data.get('timestamp', 'N/A')[:10]],
        ['Assets Analyzed', str(len(tickers))],
        ['Lookback Days', str(config.get('lookback_days', 'N/A'))],
        ['PC1 Variance', f"{signals.get('var_explained_first', 0)*100:.1f}%"],
        ['Mean Centrality', f"{signals.get('mean_eigenvector_centrality', 0):.4f}"],
        ['Std Centrality', f"{signals.get('std_eigenvector_centrality', 0):.4f}"],
    ]

    table = ax.table(cellText=rows, loc='center', cellLoc='left',
                     colWidths=[0.55, 0.45])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.6)

    for i in range(len(rows)):
        table[(i, 0)].set_facecolor(C['bg_light'])
        table[(i, 0)].set_text_props(fontweight='bold', color=C['fg'])
        table[(i, 0)].set_edgecolor(C['gray'])
        table[(i, 1)].set_facecolor(C['bg'])
        table[(i, 1)].set_text_props(color=C['fg'])
        table[(i, 1)].set_edgecolor(C['gray'])


def plot_risk_signals(data: dict, output_path: str):
    """Create the full risk signals visualization."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.suptitle('Systematic Risk Early-Warning Signals', fontsize=14, fontweight='bold')

    signals = data.get('latest_signals', {})
    centralities = data.get('centralities', [])

    # 1. Regime gauge (top-left)
    draw_regime_gauge(axes[0, 0],
                      data.get('current_regime', 'Normal'),
                      data.get('transition_probability', 0))

    # 2. Eigenvalue analysis (top-right)
    draw_eigenvalue_analysis(axes[0, 1], signals)

    # 3. Centrality distribution (bottom-left)
    draw_centrality_distribution(axes[1, 0], centralities, signals)

    # 4. Summary metrics (bottom-right)
    draw_summary_metrics(axes[1, 1], data)

    plt.tight_layout()
    save_figure(fig, output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Plot systematic risk signals')
    parser.add_argument('--input', required=True, help='Input risk signals JSON file')
    parser.add_argument('--output', help='Output PNG path')
    args = parser.parse_args()

    data = load_result(args.input)

    if args.output:
        output_path = args.output
    else:
        output_dir = Path(__file__).resolve().parent.parent.parent / "output" / "plots"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / 'risk_signals_dashboard.png')

    plot_risk_signals(data, output_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())

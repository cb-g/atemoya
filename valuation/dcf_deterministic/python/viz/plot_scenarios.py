#!/usr/bin/env python3
"""
Visualize scenario analysis results (bull/base/bear) from DCF deterministic valuation.
"""

import argparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Set plotting style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 10

def load_scenario_data(csv_path):
    """Load scenario comparison data from CSV."""
    df = pd.read_csv(csv_path)
    return df

def plot_valuation_comparison(df, ticker, price, output_dir):
    """Create bar chart comparing scenario valuations vs market price."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    scenarios = df['scenario'].values
    fcfe_values = df['ivps_fcfe'].values
    fcff_values = df['ivps_fcff'].values

    colors = {
        'Bull': '#2E7D32',  # Green
        'Base': '#1976D2',  # Blue
        'Bear': '#C62828',  # Red
    }
    scenario_colors = [colors[s] for s in scenarios]

    # FCFE comparison
    x = range(len(scenarios))
    bars1 = ax1.bar(x, fcfe_values, color=scenario_colors, alpha=0.7, edgecolor='black')
    ax1.axhline(y=price, color='orange', linestyle='--', linewidth=2, label=f'Market Price: ${price:.2f}')
    ax1.set_xlabel('Scenario', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Intrinsic Value per Share ($)', fontsize=12, fontweight='bold')
    ax1.set_title(f'{ticker} - FCFE Valuation Scenarios', fontsize=14, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticks(x)
    ax1.set_xticklabels(scenarios, fontsize=11)
    ax1.legend(fontsize=10)
    ax1.grid(axis='y', alpha=0.3)

    # Add value labels on bars
    for i, (bar, val) in enumerate(zip(bars1, fcfe_values)):
        height = bar.get_height()
        mos = df.loc[i, 'mos_fcfe'] * 100
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'${val:.2f}\n({mos:+.1f}%)',
                ha='center', va='bottom', fontsize=9, fontweight='bold')

    # FCFF comparison
    bars2 = ax2.bar(x, fcff_values, color=scenario_colors, alpha=0.7, edgecolor='black')
    ax2.axhline(y=price, color='orange', linestyle='--', linewidth=2, label=f'Market Price: ${price:.2f}')
    ax2.set_xlabel('Scenario', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Intrinsic Value per Share ($)', fontsize=12, fontweight='bold')
    ax2.set_title(f'{ticker} - FCFF Valuation Scenarios', fontsize=14, fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels(scenarios, fontsize=11)
    ax2.legend(fontsize=10)
    ax2.grid(axis='y', alpha=0.3)

    # Add value labels on bars
    for i, (bar, val) in enumerate(zip(bars2, fcff_values)):
        height = bar.get_height()
        mos = df.loc[i, 'mos_fcff'] * 100
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'${val:.2f}\n({mos:+.1f}%)',
                ha='center', va='bottom', fontsize=9, fontweight='bold')

    plt.tight_layout()

    # Save
    output_path = Path(output_dir) / f'{ticker}_scenarios.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()

def plot_sensitivity_ranges(df, ticker, price, output_dir):
    """Create range plot showing valuation sensitivity."""
    fig, ax = plt.subplots(figsize=(10, 6))

    # Calculate ranges
    fcfe_bear = df.loc[df['scenario'] == 'Bear', 'ivps_fcfe'].values[0]
    fcfe_base = df.loc[df['scenario'] == 'Base', 'ivps_fcfe'].values[0]
    fcfe_bull = df.loc[df['scenario'] == 'Bull', 'ivps_fcfe'].values[0]

    fcff_bear = df.loc[df['scenario'] == 'Bear', 'ivps_fcff'].values[0]
    fcff_base = df.loc[df['scenario'] == 'Base', 'ivps_fcff'].values[0]
    fcff_bull = df.loc[df['scenario'] == 'Bull', 'ivps_fcff'].values[0]

    # Plot horizontal ranges
    y_positions = [1, 0]
    methods = ['FCFE', 'FCFF']

    # FCFE range
    ax.plot([fcfe_bear, fcfe_bull], [y_positions[0], y_positions[0]],
            'o-', color='#1976D2', linewidth=3, markersize=8, label='Valuation Range')
    ax.plot(fcfe_base, y_positions[0], 'D', color='#1976D2', markersize=10,
            markeredgecolor='black', markeredgewidth=1.5, label='Base Case')

    # FCFF range
    ax.plot([fcff_bear, fcff_bull], [y_positions[1], y_positions[1]],
            'o-', color='#1976D2', linewidth=3, markersize=8)
    ax.plot(fcff_base, y_positions[1], 'D', color='#1976D2', markersize=10,
            markeredgecolor='black', markeredgewidth=1.5)

    # Market price line
    ax.axvline(x=price, color='orange', linestyle='--', linewidth=2, label=f'Market Price: ${price:.2f}')

    # Labels
    ax.set_yticks(y_positions)
    ax.set_yticklabels(methods, fontsize=12, fontweight='bold')
    ax.set_xlabel('Intrinsic Value per Share ($)', fontsize=12, fontweight='bold')
    ax.set_title(f'{ticker} - Valuation Sensitivity to Scenarios', fontsize=14, fontweight='bold')
    ax.legend(fontsize=10, loc='best')
    ax.grid(axis='x', alpha=0.3)

    # Add value annotations
    ax.text(fcfe_bear, y_positions[0] + 0.1, f'${fcfe_bear:.2f}', ha='center', va='bottom', fontsize=9)
    ax.text(fcfe_base, y_positions[0] + 0.1, f'${fcfe_base:.2f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    ax.text(fcfe_bull, y_positions[0] + 0.1, f'${fcfe_bull:.2f}', ha='center', va='bottom', fontsize=9)

    ax.text(fcff_bear, y_positions[1] - 0.1, f'${fcff_bear:.2f}', ha='center', va='top', fontsize=9)
    ax.text(fcff_base, y_positions[1] - 0.1, f'${fcff_base:.2f}', ha='center', va='top', fontsize=9, fontweight='bold')
    ax.text(fcff_bull, y_positions[1] - 0.1, f'${fcff_bull:.2f}', ha='center', va='top', fontsize=9)

    plt.tight_layout()

    # Save
    output_path = Path(output_dir) / f'{ticker}_scenario_ranges.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()

def plot_parameter_comparison(df, ticker, output_dir):
    """Create comparison of parameters across scenarios."""
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))

    scenarios = df['scenario'].values
    colors = {
        'Bull': '#2E7D32',
        'Base': '#1976D2',
        'Bear': '#C62828',
    }
    scenario_colors = [colors[s] for s in scenarios]

    x = range(len(scenarios))

    # Cost of Equity
    ce_values = df['cost_of_equity'].values * 100
    bars1 = ax1.bar(x, ce_values, color=scenario_colors, alpha=0.7, edgecolor='black')
    ax1.set_xlabel('Scenario', fontsize=11, fontweight='bold')
    ax1.set_ylabel('Cost of Equity (%)', fontsize=11, fontweight='bold')
    ax1.set_title('Cost of Equity by Scenario', fontsize=12, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(scenarios)
    ax1.grid(axis='y', alpha=0.3)
    for bar, val in zip(bars1, ce_values):
        ax1.text(bar.get_x() + bar.get_width()/2., val,
                f'{val:.2f}%', ha='center', va='bottom', fontsize=9)

    # WACC
    wacc_values = df['wacc'].values * 100
    bars2 = ax2.bar(x, wacc_values, color=scenario_colors, alpha=0.7, edgecolor='black')
    ax2.set_xlabel('Scenario', fontsize=11, fontweight='bold')
    ax2.set_ylabel('WACC (%)', fontsize=11, fontweight='bold')
    ax2.set_title('WACC by Scenario', fontsize=12, fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels(scenarios)
    ax2.grid(axis='y', alpha=0.3)
    for bar, val in zip(bars2, wacc_values):
        ax2.text(bar.get_x() + bar.get_width()/2., val,
                f'{val:.2f}%', ha='center', va='bottom', fontsize=9)

    # FCFE Growth
    fcfe_growth = df['growth_fcfe'].values * 100
    bars3 = ax3.bar(x, fcfe_growth, color=scenario_colors, alpha=0.7, edgecolor='black')
    ax3.set_xlabel('Scenario', fontsize=11, fontweight='bold')
    ax3.set_ylabel('FCFE Growth Rate (%)', fontsize=11, fontweight='bold')
    ax3.set_title('FCFE Growth by Scenario', fontsize=12, fontweight='bold')
    ax3.set_xticks(x)
    ax3.set_xticklabels(scenarios)
    ax3.grid(axis='y', alpha=0.3)
    for bar, val in zip(bars3, fcfe_growth):
        ax3.text(bar.get_x() + bar.get_width()/2., val,
                f'{val:.2f}%', ha='center', va='bottom', fontsize=9)

    # FCFF Growth
    fcff_growth = df['growth_fcff'].values * 100
    bars4 = ax4.bar(x, fcff_growth, color=scenario_colors, alpha=0.7, edgecolor='black')
    ax4.set_xlabel('Scenario', fontsize=11, fontweight='bold')
    ax4.set_ylabel('FCFF Growth Rate (%)', fontsize=11, fontweight='bold')
    ax4.set_title('FCFF Growth by Scenario', fontsize=12, fontweight='bold')
    ax4.set_xticks(x)
    ax4.set_xticklabels(scenarios)
    ax4.grid(axis='y', alpha=0.3)
    for bar, val in zip(bars4, fcff_growth):
        ax4.text(bar.get_x() + bar.get_width()/2., val,
                f'{val:.2f}%', ha='center', va='bottom', fontsize=9)

    plt.tight_layout()

    # Save
    output_path = Path(output_dir) / f'{ticker}_scenario_parameters.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Visualize DCF scenario analysis')
    parser.add_argument('--csv', required=True, help='Path to scenario CSV file')
    parser.add_argument('--ticker', required=True, help='Ticker symbol')
    parser.add_argument('--price', required=True, type=float, help='Market price')
    parser.add_argument('--output', default='../output', help='Output directory for plots')

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    df = load_scenario_data(args.csv)

    # Create visualizations
    print(f"Generating scenario visualizations for {args.ticker}...")
    plot_valuation_comparison(df, args.ticker, args.price, output_dir)
    plot_sensitivity_ranges(df, args.ticker, args.price, output_dir)
    plot_parameter_comparison(df, args.ticker, output_dir)

    print(f"\nAll visualizations saved to {output_dir}")

if __name__ == '__main__':
    main()

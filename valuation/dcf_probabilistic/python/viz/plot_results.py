#!/usr/bin/env python3
"""
Visualize probabilistic DCF results with KDE plots and efficient frontiers.
"""

import argparse
import sys
from pathlib import Path

try:
    import pandas as pd
    import numpy as np
    import matplotlib.pyplot as plt
    from scipy.stats import gaussian_kde
except ImportError:
    print("Error: Required packages not installed.", file=sys.stderr)
    print("Run: pip install pandas numpy matplotlib scipy", file=sys.stderr)
    sys.exit(1)


# Kanagawa Dragon color palette (dark mode)
KANAGAWA_DRAGON = {
    'bg': '#181616',
    'fg': '#c5c9c5',
    'black': '#0d0c0c',
    'red': '#c4746e',
    'green': '#8a9a7b',
    'yellow': '#c4b28a',
    'blue': '#8ba4b0',
    'magenta': '#a292a3',
    'cyan': '#8ea4a2',
    'white': '#c5c9c5',
    'gray': '#625e5a',
}

# Kanagawa Lotus color palette (light mode)
KANAGAWA_LOTUS = {
    'bg': '#f2ecbc',
    'fg': '#545464',
    'black': '#1f1f28',
    'red': '#c84053',
    'green': '#6f894e',
    'yellow': '#77713f',
    'blue': '#4d699b',
    'magenta': '#b35b79',
    'cyan': '#597b75',
    'white': '#545464',
    'gray': '#b8b5b9',
}


def setup_dark_mode():
    """Configure matplotlib for Kanagawa Dragon dark mode."""
    plt.style.use('dark_background')
    plt.rcParams.update({
        'figure.facecolor': KANAGAWA_DRAGON['bg'],
        'axes.facecolor': KANAGAWA_DRAGON['bg'],
        'axes.edgecolor': KANAGAWA_DRAGON['gray'],
        'axes.labelcolor': KANAGAWA_DRAGON['fg'],
        'text.color': KANAGAWA_DRAGON['fg'],
        'xtick.color': KANAGAWA_DRAGON['fg'],
        'ytick.color': KANAGAWA_DRAGON['fg'],
        'grid.color': KANAGAWA_DRAGON['gray'],
        'legend.facecolor': KANAGAWA_DRAGON['bg'],
        'legend.edgecolor': KANAGAWA_DRAGON['gray'],
    })


def setup_light_mode():
    """Configure matplotlib for Kanagawa Lotus light mode."""
    plt.style.use('default')
    plt.rcParams.update({
        'figure.facecolor': KANAGAWA_LOTUS['bg'],
        'axes.facecolor': KANAGAWA_LOTUS['bg'],
        'axes.edgecolor': KANAGAWA_LOTUS['gray'],
        'axes.labelcolor': KANAGAWA_LOTUS['fg'],
        'text.color': KANAGAWA_LOTUS['fg'],
        'xtick.color': KANAGAWA_LOTUS['fg'],
        'ytick.color': KANAGAWA_LOTUS['fg'],
        'grid.color': KANAGAWA_LOTUS['gray'],
        'legend.facecolor': KANAGAWA_LOTUS['bg'],
        'legend.edgecolor': KANAGAWA_LOTUS['gray'],
    })


def plot_kde_distribution(ticker, simulations, price, output_file, method="FCFE", dark_mode=False):
    """Plot kernel density estimate of intrinsic value distribution."""
    # Set colors based on mode
    if dark_mode:
        dist_color = KANAGAWA_DRAGON['cyan']
        price_color = KANAGAWA_DRAGON['red']
        mean_color = KANAGAWA_DRAGON['yellow']
    else:
        dist_color = KANAGAWA_LOTUS['cyan']
        price_color = KANAGAWA_LOTUS['red']
        mean_color = KANAGAWA_LOTUS['yellow']

    fig, ax = plt.subplots(figsize=(10, 6))

    # Compute KDE
    kde = gaussian_kde(simulations)
    x_range = np.linspace(simulations.min() * 0.8, simulations.max() * 1.2, 1000)
    density = kde(x_range)

    # Plot distribution
    ax.plot(x_range, density, color=dist_color, linewidth=2, label='Intrinsic Value Distribution')
    ax.fill_between(x_range, density, alpha=0.3, color=dist_color)

    # Mark market price
    ax.axvline(price, color=price_color, linestyle='--', linewidth=2, label=f'Market Price: ${price:.2f}')

    # Mark mean
    mean_val = simulations.mean()
    ax.axvline(mean_val, color=mean_color, linestyle='--', linewidth=2, label=f'Mean: ${mean_val:.2f}')

    # Calculate probabilities
    prob_under = (simulations > price).mean()
    prob_over = (simulations < price).mean()

    # Formatting
    ax.set_xlabel('Intrinsic Value per Share ($)', fontsize=12)
    ax.set_ylabel('Probability Density', fontsize=12)
    ax.set_title(f'{ticker} - {method} Valuation Distribution\nP(Undervalued) = {prob_under:.1%}', fontsize=14)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, linewidth=0.6)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"KDE plot saved: {output_file}")


def plot_value_surplus_distribution(ticker, simulations, price, output_file, method="FCFE", dark_mode=False):
    """Plot distribution of value surplus percentage."""
    # Set colors based on mode
    if dark_mode:
        dist_color = KANAGAWA_DRAGON['cyan']
        price_color = KANAGAWA_DRAGON['red']
        mean_color = KANAGAWA_DRAGON['yellow']
        upside_color = KANAGAWA_DRAGON['green']
        downside_color = KANAGAWA_DRAGON['red']
    else:
        dist_color = KANAGAWA_LOTUS['cyan']
        price_color = KANAGAWA_LOTUS['red']
        mean_color = KANAGAWA_LOTUS['yellow']
        upside_color = KANAGAWA_LOTUS['green']
        downside_color = KANAGAWA_LOTUS['red']

    fig, ax = plt.subplots(figsize=(10, 6))

    # Calculate surplus percentage
    surplus_pct = (simulations - price) / price * 100

    # Compute KDE
    kde = gaussian_kde(surplus_pct)
    x_range = np.linspace(surplus_pct.min() * 1.2, surplus_pct.max() * 1.2, 1000)
    density = kde(x_range)

    # Plot distribution
    ax.plot(x_range, density, color=dist_color, linewidth=2)
    ax.fill_between(x_range, density, alpha=0.3, color=dist_color)

    # Mark zero (market price)
    ax.axvline(0, color=price_color, linestyle='--', linewidth=2, label='Market Price (0%)')

    # Mark mean
    mean_surplus = surplus_pct.mean()
    ax.axvline(mean_surplus, color=mean_color, linestyle='--', linewidth=2, label=f'Mean Surplus: {mean_surplus:.1f}%')

    # Shade upside/downside
    ax.fill_between(x_range[x_range > 0], density[x_range > 0], alpha=0.2, color=upside_color, label='Upside Potential')
    ax.fill_between(x_range[x_range < 0], density[x_range < 0], alpha=0.2, color=downside_color, label='Downside Risk')

    # Formatting
    ax.set_xlabel('Value Surplus (%)', fontsize=12)
    ax.set_ylabel('Probability Density', fontsize=12)
    ax.set_title(f'{ticker} - {method} Value Surplus Distribution', fontsize=14)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, linewidth=0.6)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Surplus distribution plot saved: {output_file}")


def plot_combined_kde_distribution(ticker, fcfe_sims, fcff_sims, price, output_file):
    """Plot vertically stacked KDE distributions for FCFE and FCFF with shared x-axis."""
    dist_color = KANAGAWA_DRAGON['cyan']
    price_color = KANAGAWA_DRAGON['red']
    mean_color = KANAGAWA_DRAGON['yellow']
    upside_color = KANAGAWA_DRAGON['green']
    downside_color = KANAGAWA_DRAGON['red']

    # Determine common x-axis range for both plots
    all_vals = np.concatenate([fcfe_sims, fcff_sims])
    x_min = all_vals.min() * 0.8
    x_max = all_vals.max() * 1.2

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 12), sharex=True)

    # FCFF plot (top)
    kde_fcff = gaussian_kde(fcff_sims)
    x_range = np.linspace(x_min, x_max, 1000)
    density_fcff = kde_fcff(x_range)

    ax1.plot(x_range, density_fcff, color=dist_color, linewidth=2, label='Intrinsic Value Distribution')
    ax1.fill_between(x_range, density_fcff, alpha=0.3, color=dist_color)

    # Shade upside/downside regions
    ax1.fill_between(x_range[x_range > price], density_fcff[x_range > price], alpha=0.2, color=upside_color, label='Upside Potential')
    ax1.fill_between(x_range[x_range < price], density_fcff[x_range < price], alpha=0.2, color=downside_color, label='Downside Risk')

    ax1.axvline(price, color=price_color, linestyle='--', linewidth=2, label=f'Market Price: ${price:.2f}')
    mean_fcff = fcff_sims.mean()
    ax1.axvline(mean_fcff, color=mean_color, linestyle='--', linewidth=2, label=f'Mean: ${mean_fcff:.2f}')
    prob_under_fcff = (fcff_sims > price).mean()
    ax1.set_ylabel('Probability Density', fontsize=12)
    ax1.set_title(f'{ticker} - FCFF Valuation Distribution\nP(Undervalued) = {prob_under_fcff:.1%}', fontsize=14)
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3, linewidth=0.6)

    # FCFE plot (bottom)
    kde_fcfe = gaussian_kde(fcfe_sims)
    density_fcfe = kde_fcfe(x_range)

    ax2.plot(x_range, density_fcfe, color=dist_color, linewidth=2, label='Intrinsic Value Distribution')
    ax2.fill_between(x_range, density_fcfe, alpha=0.3, color=dist_color)

    # Shade upside/downside regions
    ax2.fill_between(x_range[x_range > price], density_fcfe[x_range > price], alpha=0.2, color=upside_color, label='Upside Potential')
    ax2.fill_between(x_range[x_range < price], density_fcfe[x_range < price], alpha=0.2, color=downside_color, label='Downside Risk')

    ax2.axvline(price, color=price_color, linestyle='--', linewidth=2, label=f'Market Price: ${price:.2f}')
    mean_fcfe = fcfe_sims.mean()
    ax2.axvline(mean_fcfe, color=mean_color, linestyle='--', linewidth=2, label=f'Mean: ${mean_fcfe:.2f}')
    prob_under_fcfe = (fcfe_sims > price).mean()
    ax2.set_xlabel('Intrinsic Value per Share ($)', fontsize=12)
    ax2.set_ylabel('Probability Density', fontsize=12)
    ax2.set_title(f'{ticker} - FCFE Valuation Distribution\nP(Undervalued) = {prob_under_fcfe:.1%}', fontsize=14)
    ax2.legend(fontsize=10)
    ax2.grid(True, alpha=0.3, linewidth=0.6)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Combined KDE plot saved: {output_file}")


def plot_combined_surplus_distribution(ticker, fcfe_sims, fcff_sims, price, output_file):
    """Plot vertically stacked surplus distributions for FCFE and FCFF with shared x-axis."""
    dist_color = KANAGAWA_DRAGON['cyan']
    price_color = KANAGAWA_DRAGON['red']
    mean_color = KANAGAWA_DRAGON['yellow']
    upside_color = KANAGAWA_DRAGON['green']
    downside_color = KANAGAWA_DRAGON['red']

    # Calculate surplus percentages
    surplus_fcfe = (fcfe_sims - price) / price * 100
    surplus_fcff = (fcff_sims - price) / price * 100

    # Determine common x-axis range for both plots
    all_surplus = np.concatenate([surplus_fcfe, surplus_fcff])
    x_min = all_surplus.min() * 1.2
    x_max = all_surplus.max() * 1.2

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 12), sharex=True)

    # FCFF surplus (top)
    kde_fcff = gaussian_kde(surplus_fcff)
    x_range = np.linspace(x_min, x_max, 1000)
    density_fcff = kde_fcff(x_range)

    ax1.plot(x_range, density_fcff, color=dist_color, linewidth=2, label='Surplus Distribution')
    ax1.fill_between(x_range, density_fcff, alpha=0.3, color=dist_color)

    # Shade upside/downside regions
    ax1.fill_between(x_range[x_range > 0], density_fcff[x_range > 0], alpha=0.2, color=upside_color, label='Upside Potential')
    ax1.fill_between(x_range[x_range < 0], density_fcff[x_range < 0], alpha=0.2, color=downside_color, label='Downside Risk')

    ax1.axvline(0, color=price_color, linestyle='--', linewidth=2, label='Market Price (0%)')
    mean_surplus_fcff = surplus_fcff.mean()
    ax1.axvline(mean_surplus_fcff, color=mean_color, linestyle='--', linewidth=2, label=f'Mean Surplus: {mean_surplus_fcff:.1f}%')
    ax1.set_ylabel('Probability Density', fontsize=12)
    ax1.set_title(f'{ticker} - FCFF Value Surplus Distribution', fontsize=14)
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3, linewidth=0.6)

    # FCFE surplus (bottom)
    kde_fcfe = gaussian_kde(surplus_fcfe)
    density_fcfe = kde_fcfe(x_range)

    ax2.plot(x_range, density_fcfe, color=dist_color, linewidth=2, label='Surplus Distribution')
    ax2.fill_between(x_range, density_fcfe, alpha=0.3, color=dist_color)

    # Shade upside/downside regions
    ax2.fill_between(x_range[x_range > 0], density_fcfe[x_range > 0], alpha=0.2, color=upside_color, label='Upside Potential')
    ax2.fill_between(x_range[x_range < 0], density_fcfe[x_range < 0], alpha=0.2, color=downside_color, label='Downside Risk')

    ax2.axvline(0, color=price_color, linestyle='--', linewidth=2, label='Market Price (0%)')
    mean_surplus_fcfe = surplus_fcfe.mean()
    ax2.axvline(mean_surplus_fcfe, color=mean_color, linestyle='--', linewidth=2, label=f'Mean Surplus: {mean_surplus_fcfe:.1f}%')
    ax2.set_xlabel('Value Surplus (%)', fontsize=12)
    ax2.set_ylabel('Probability Density', fontsize=12)
    ax2.set_title(f'{ticker} - FCFE Value Surplus Distribution', fontsize=14)
    ax2.legend(fontsize=10)
    ax2.grid(True, alpha=0.3, linewidth=0.6)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Combined surplus plot saved: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Visualize probabilistic DCF results")
    parser.add_argument("--output-dir", default="../output", help="Output directory with CSV files")
    parser.add_argument("--viz-dir", default="../output", help="Directory to save visualizations")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    # Create organized directory structure
    data_dir = output_dir / "data"
    single_asset_dir = output_dir / "single_asset"

    data_dir.mkdir(parents=True, exist_ok=True)
    single_asset_dir.mkdir(parents=True, exist_ok=True)

    # For backward compatibility, also accept old viz_dir argument
    if args.viz_dir != "../output":
        output_dir = Path(args.viz_dir)
        data_dir = output_dir / "data"
        single_asset_dir = output_dir / "single_asset"
        data_dir.mkdir(parents=True, exist_ok=True)
        single_asset_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Load data from data directory (try new structure first, fall back to old)
        fcfe_matrix_file = data_dir / "simulations_fcfe.csv"
        if not fcfe_matrix_file.exists():
            fcfe_matrix_file = output_dir / "simulations_fcfe.csv"

        fcff_matrix_file = data_dir / "simulations_fcff.csv"
        if not fcff_matrix_file.exists():
            fcff_matrix_file = output_dir / "simulations_fcff.csv"

        prices_file = data_dir / "market_prices.csv"
        if not prices_file.exists():
            prices_file = output_dir / "market_prices.csv"

        if not fcfe_matrix_file.exists():
            print(f"Error: {fcfe_matrix_file} not found", file=sys.stderr)
            sys.exit(1)

        fcfe_sims = pd.read_csv(fcfe_matrix_file)
        fcff_sims = pd.read_csv(fcff_matrix_file)
        prices = pd.read_csv(prices_file)

        # Set up dark mode (Kanagawa Dragon)
        setup_dark_mode()

        # Generate plots for each ticker (dark mode only)
        for ticker in fcfe_sims.columns:
            if ticker not in prices['ticker'].values:
                continue

            price = prices[prices['ticker'] == ticker]['price'].values[0]

            # Get simulation data
            fcfe_vals = fcfe_sims[ticker].dropna().values
            fcff_vals = fcff_sims[ticker].dropna().values

            # Generate combined plots
            if len(fcfe_vals) > 10 and len(fcff_vals) > 10:
                plot_combined_kde_distribution(
                    ticker, fcfe_vals, fcff_vals, price,
                    single_asset_dir / f"{ticker}_kde_combined.png"
                )
                plot_combined_surplus_distribution(
                    ticker, fcfe_vals, fcff_vals, price,
                    single_asset_dir / f"{ticker}_surplus_combined.png"
                )

        print(f"\nAll visualizations saved to: {single_asset_dir}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

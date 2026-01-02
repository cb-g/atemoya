#!/usr/bin/env python3
"""
Portfolio Efficient Frontier - Multi-Risk-Measure Visualization

Generates 6 efficient frontier plots for multi-asset portfolios based on
probabilistic DCF simulation results:

1. μ–σ: Expected return vs standard deviation (Sharpe ratio)
2. μ–p_loss: Expected return vs probability of loss
3. μ–σ_downside: Expected return vs downside deviation (Sortino ratio)
4. μ–CVaR: Expected return vs Conditional Value-at-Risk
5. μ–VaR: Expected return vs Value-at-Risk
6. μ–max_drawdown: Expected return vs maximum drawdown (Calmar ratio)

All frontiers use correlation-adjusted portfolio risk via covariance matrix.
"""

import argparse
import sys
from pathlib import Path

try:
    import pandas as pd
    import numpy as np
    import matplotlib.pyplot as plt
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


def generate_random_portfolios(n_assets, n_portfolios=5000):
    """Generate random portfolio weights using Dirichlet distribution."""
    # Dirichlet(1,1,...,1) generates uniform distribution over simplex
    weights = np.random.dirichlet(np.ones(n_assets), size=n_portfolios)
    return weights


def format_portfolio_composition(weights, tickers, top_n=15):
    """
    Format portfolio composition showing top N holdings.

    Args:
        weights: Array of portfolio weights
        tickers: List of ticker symbols
        top_n: Number of top holdings to show (default 15)

    Returns:
        Formatted string for display in plot
    """
    # Create ticker-weight pairs and sort by weight descending
    holdings = sorted(zip(tickers, weights), key=lambda x: x[1], reverse=True)

    # Take top N
    top_holdings = holdings[:top_n]

    # Calculate "Other" if there are more than top_n holdings
    other_weight = sum(w for _, w in holdings[top_n:])

    # Format as compact string
    lines = []
    for ticker, weight in top_holdings:
        if weight >= 0.01:  # Only show if >= 1%
            lines.append(f"{ticker}: {weight*100:.1f}%")

    if other_weight >= 0.01:
        lines.append(f"Other: {other_weight*100:.1f}%")

    return "\n".join(lines)


def choose_best_legend_location(star_positions, x_range, y_range):
    """
    Choose the best legend location to avoid overlapping with star markers.

    Args:
        star_positions: List of (x, y) tuples for star marker positions
        x_range: Tuple of (x_min, x_max) for the plot
        y_range: Tuple of (y_min, y_max) for the plot

    Returns:
        str: One of 'upper right', 'upper left', 'lower right', 'lower left'
    """
    x_min, x_max = x_range
    y_min, y_max = y_range

    # Normalize star positions to [0, 1] range
    normalized_stars = []
    for x, y in star_positions:
        norm_x = (x - x_min) / (x_max - x_min) if x_max > x_min else 0.5
        norm_y = (y - y_min) / (y_max - y_min) if y_max > y_min else 0.5
        normalized_stars.append((norm_x, norm_y))

    # Define quadrants (with some margin)
    quadrants = {
        'upper right': lambda x, y: x > 0.65 and y > 0.65,
        'upper left': lambda x, y: x < 0.35 and y > 0.65,
        'lower right': lambda x, y: x > 0.65 and y < 0.35,
        'lower left': lambda x, y: x < 0.35 and y < 0.35,
    }

    # Count stars in each quadrant
    quadrant_counts = {loc: 0 for loc in quadrants}
    for x, y in normalized_stars:
        for loc, in_quadrant in quadrants.items():
            if in_quadrant(x, y):
                quadrant_counts[loc] += 1

    # Choose quadrant with fewest stars (prefer upper right as default)
    min_count = min(quadrant_counts.values())
    if quadrant_counts['upper right'] == min_count:
        return 'upper right'

    # Otherwise, choose the quadrant with fewest stars
    for loc in ['upper left', 'lower right', 'lower left']:
        if quadrant_counts[loc] == min_count:
            return loc

    return 'upper right'  # Fallback


def compute_correlation_matrix(simulations_df, prices_df):
    """
    Compute correlation matrix of returns from simulation data.

    Args:
        simulations_df: DataFrame with simulation results (N_sims × N_assets)
        prices_df: DataFrame with current market prices

    Returns:
        correlation_matrix: (N_assets × N_assets) correlation matrix
        covariance_matrix: (N_assets × N_assets) covariance matrix
        returns_df: DataFrame with returns for each simulation
    """
    tickers = simulations_df.columns
    prices = prices_df.set_index('ticker').loc[tickers, 'price'].values

    # Compute returns for each asset: (IV - Price) / Price
    returns = np.zeros_like(simulations_df.values, dtype=float)
    for i, (ticker, price) in enumerate(zip(tickers, prices)):
        intrinsic_values = simulations_df[ticker].values
        returns[:, i] = (intrinsic_values - price) / price

    # Create returns DataFrame
    returns_df = pd.DataFrame(returns, columns=tickers)

    # Compute correlation and covariance matrices
    # pandas .corr() and .cov() handle NaN values with pairwise deletion by default
    correlation_matrix = returns_df.corr(method='pearson', min_periods=100)
    covariance_matrix = returns_df.cov(min_periods=100)

    return correlation_matrix, covariance_matrix, returns_df


def compute_portfolio_stats(simulations_df, prices_df, weights, covariance_matrix=None):
    """
    Compute portfolio statistics from simulation matrices.

    Args:
        simulations_df: DataFrame with simulation results (N_sims × N_assets)
        prices_df: DataFrame with current market prices
        weights: Array of portfolio weights (N_assets,)
        covariance_matrix: (N_assets × N_assets) covariance matrix of returns (optional)

    Returns:
        dict with mean_return, std_return, prob_loss, mean_surplus_pct
    """
    tickers = simulations_df.columns

    # Get intrinsic values and prices
    intrinsic_values = simulations_df[tickers].values  # (N_sims, N_assets)
    prices = prices_df.set_index('ticker').loc[tickers, 'price'].values  # (N_assets,)

    # Drop rows with any NaN values (incomplete simulations)
    valid_mask = ~np.isnan(intrinsic_values).any(axis=1)
    intrinsic_values_clean = intrinsic_values[valid_mask]

    if len(intrinsic_values_clean) < 10:
        # Not enough valid simulations - return NaN stats
        return {
            'mean_return': np.nan,
            'std_return': np.nan,
            'downside_deviation': np.nan,
            'var_5': np.nan,
            'var_1': np.nan,
            'cvar_5': np.nan,
            'cvar_1': np.nan,
            'max_drawdown': np.nan,
            'prob_loss': np.nan,
            'mean_surplus_pct': np.nan,
            'weights': weights.copy()
        }

    # Portfolio intrinsic value = weighted average of individual intrinsic values
    portfolio_intrinsic = intrinsic_values_clean @ weights  # (N_sims_clean,)

    # Portfolio price = weighted average of individual prices
    portfolio_price = prices @ weights

    # Returns (as percentage surplus over market)
    portfolio_returns = (portfolio_intrinsic - portfolio_price) / portfolio_price

    # Compute portfolio risk metrics
    mean_return = np.nanmean(portfolio_returns)

    # 1. Standard deviation (total volatility)
    if covariance_matrix is not None:
        # Use proper portfolio variance formula: σ²_p = w^T Σ w
        portfolio_variance = weights @ covariance_matrix.values @ weights
        std_return = np.sqrt(portfolio_variance) if portfolio_variance >= 0 else 0.0
    else:
        # Fallback to empirical std (assumes independence)
        std_return = np.nanstd(portfolio_returns)

    # 2. Downside deviation (semi-deviation, only below-mean volatility)
    downside_returns = portfolio_returns[portfolio_returns < mean_return]
    downside_deviation = np.nanstd(downside_returns) if len(downside_returns) > 1 else 0.0

    # 3. VaR (Value-at-Risk) at 5% and 1%
    var_5 = np.nanpercentile(portfolio_returns, 5)   # 5th percentile
    var_1 = np.nanpercentile(portfolio_returns, 1)   # 1st percentile

    # 4. CVaR (Conditional VaR / Expected Shortfall) at 5% and 1%
    worst_5_pct = portfolio_returns[portfolio_returns <= var_5]
    cvar_5 = np.nanmean(worst_5_pct) if len(worst_5_pct) > 0 else var_5

    worst_1_pct = portfolio_returns[portfolio_returns <= var_1]
    cvar_1 = np.nanmean(worst_1_pct) if len(worst_1_pct) > 0 else var_1

    # 5. Max Drawdown (from median to worst case)
    median_return = np.nanmedian(portfolio_returns)
    min_return = np.nanmin(portfolio_returns)
    max_drawdown = median_return - min_return

    # 6. Probability of loss
    valid_returns = portfolio_returns[~np.isnan(portfolio_returns)]
    prob_loss = (valid_returns < 0).mean() if len(valid_returns) > 0 else 0.0

    stats = {
        'mean_return': mean_return,
        'std_return': std_return,
        'downside_deviation': downside_deviation,
        'var_5': var_5,
        'var_1': var_1,
        'cvar_5': cvar_5,
        'cvar_1': cvar_1,
        'max_drawdown': max_drawdown,
        'prob_loss': prob_loss,
        'mean_surplus_pct': mean_return * 100,
        'weights': weights.copy()
    }

    return stats


def plot_efficient_frontier(portfolio_stats, output_file, tickers=None, title="Efficient Frontier"):
    """Plot risk-return efficient frontier."""
    fig, ax = plt.subplots(figsize=(14, 8))

    means = [p['mean_return'] * 100 for p in portfolio_stats]
    stds = [p['std_return'] * 100 for p in portfolio_stats]

    # Color by Sharpe ratio (assume risk-free rate ~2%)
    rf_rate = 2.0
    sharpe_ratios = [(m - rf_rate) / s if s > 0 else 0 for m, s in zip(means, stds)]

    scatter = ax.scatter(stds, means, c=sharpe_ratios, cmap='RdPu',
                        alpha=0.6, s=20, edgecolors='none')

    # Mark special portfolios
    min_risk_idx = np.argmin(stds)
    max_return_idx = np.argmax(means)
    max_sharpe_idx = np.argmax(sharpe_ratios)

    ax.scatter(stds[min_risk_idx], means[min_risk_idx],
              marker='*', s=250, c='blue', edgecolors='black',
              linewidths=0.8, label='Min Variance', zorder=10)
    ax.scatter(stds[max_return_idx], means[max_return_idx],
              marker='*', s=250, c='green', edgecolors='black',
              linewidths=0.8, label='Max Return', zorder=10)
    ax.scatter(stds[max_sharpe_idx], means[max_sharpe_idx],
              marker='*', s=250, c='gold', edgecolors='black',
              linewidths=0.8, label='Max Sharpe', zorder=10)

    # Add portfolio composition legends (if tickers provided)
    # Position them outside the plot area on the right side, past the colorbar
    if tickers is not None:
        # Max Sharpe portfolio composition (top right, outside plot and colorbar)
        sharpe_comp = format_portfolio_composition(
            portfolio_stats[max_sharpe_idx]['weights'], tickers, top_n=15
        )
        textstr_sharpe = f"Max Sharpe\nPortfolio:\n{sharpe_comp}"
        # Position at (1.25, 1.0) - past colorbar, aligned with top
        ax.text(1.25, 1.0, textstr_sharpe, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        # Max Return portfolio composition (right side, middle)
        maxret_comp = format_portfolio_composition(
            portfolio_stats[max_return_idx]['weights'], tickers, top_n=15
        )
        textstr_maxret = f"Max Return\nPortfolio:\n{maxret_comp}"
        # Position at (1.25, 0.7) - past colorbar, middle
        ax.text(1.25, 0.7, textstr_maxret, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        # Min Variance portfolio composition (right side, bottom)
        minvar_comp = format_portfolio_composition(
            portfolio_stats[min_risk_idx]['weights'], tickers, top_n=15
        )
        textstr_minvar = f"Min Variance\nPortfolio:\n{minvar_comp}"
        # Position at (1.25, 0.4) - past colorbar, bottom
        ax.text(1.25, 0.4, textstr_minvar, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    # Determine best legend location based on star positions
    star_positions = [
        (stds[min_risk_idx], means[min_risk_idx]),
        (stds[max_return_idx], means[max_return_idx]),
        (stds[max_sharpe_idx], means[max_sharpe_idx])
    ]
    x_range = (min(stds), max(stds))
    y_range = (min(means), max(means))
    legend_loc = choose_best_legend_location(star_positions, x_range, y_range)

    # Formatting
    ax.set_xlabel('Portfolio Risk (Std Dev of Return, %)', fontsize=12)
    ax.set_ylabel('Expected Return (%)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=10, loc=legend_loc)

    # Add colorbar
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label('Sharpe Ratio', fontsize=10)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Risk-return frontier saved: {output_file}")

    # Print stats for special portfolios
    print(f"\nMin Variance Portfolio:")
    print(f"  Risk: {stds[min_risk_idx]:.2f}%, Return: {means[min_risk_idx]:.2f}%")
    print(f"  Weights: {portfolio_stats[min_risk_idx]['weights']}")

    print(f"\nMax Sharpe Portfolio:")
    print(f"  Risk: {stds[max_sharpe_idx]:.2f}%, Return: {means[max_sharpe_idx]:.2f}%")
    print(f"  Sharpe: {sharpe_ratios[max_sharpe_idx]:.3f}")
    print(f"  Weights: {portfolio_stats[max_sharpe_idx]['weights']}")


def plot_tail_risk_frontier(portfolio_stats, output_file, tickers=None, title="Tail Risk Frontier"):
    """Plot expected return vs probability of loss."""
    fig, ax = plt.subplots(figsize=(14, 8))

    means = [p['mean_return'] * 100 for p in portfolio_stats]
    prob_losses = [p['prob_loss'] * 100 for p in portfolio_stats]

    # Color by mean return
    scatter = ax.scatter(prob_losses, means, c=means, cmap='RdPu',
                        alpha=0.6, s=20, edgecolors='none')

    # Mark special portfolios
    min_loss_idx = np.argmin(prob_losses)
    max_return_idx = np.argmax(means)

    ax.scatter(prob_losses[min_loss_idx], means[min_loss_idx],
              marker='*', s=250, c='blue', edgecolors='black',
              linewidths=0.8, label='Min P(Loss)', zorder=10)
    ax.scatter(prob_losses[max_return_idx], means[max_return_idx],
              marker='*', s=250, c='green', edgecolors='black',
              linewidths=0.8, label='Max Return', zorder=10)

    # Add portfolio composition legends (if tickers provided)
    # Position outside the plot area on the right side, past the colorbar
    if tickers is not None:
        # Min P(Loss) portfolio composition (top)
        comp = format_portfolio_composition(portfolio_stats[min_loss_idx]['weights'], tickers, top_n=15)
        textstr = f"Min P(Loss)\nPortfolio:\n{comp}"
        # Position at (1.25, 1.0) - past colorbar, aligned with top
        ax.text(1.25, 1.0, textstr, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        # Max Return portfolio composition (bottom)
        maxret_comp = format_portfolio_composition(portfolio_stats[max_return_idx]['weights'], tickers, top_n=15)
        textstr_maxret = f"Max Return\nPortfolio:\n{maxret_comp}"
        # Position at (1.25, 0.7) - past colorbar, bottom
        ax.text(1.25, 0.7, textstr_maxret, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    # Determine best legend location based on star positions
    star_positions = [
        (prob_losses[min_loss_idx], means[min_loss_idx]),
        (prob_losses[max_return_idx], means[max_return_idx])
    ]
    x_range = (min(prob_losses), max(prob_losses))
    y_range = (min(means), max(means))
    legend_loc = choose_best_legend_location(star_positions, x_range, y_range)

    # Formatting
    ax.set_xlabel('Probability of Loss (%)', fontsize=12)
    ax.set_ylabel('Expected Return (%)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=10, loc=legend_loc)

    # Add colorbar
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label('Expected Return (%)', fontsize=10)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Tail risk frontier saved: {output_file}")

    # Print stats
    print(f"\nMin P(Loss) Portfolio:")
    print(f"  P(Loss): {prob_losses[min_loss_idx]:.2f}%, Return: {means[min_loss_idx]:.2f}%")
    print(f"  Weights: {portfolio_stats[min_loss_idx]['weights']}")


def plot_downside_deviation_frontier(portfolio_stats, output_file, tickers=None, title="Downside Deviation Frontier"):
    """Plot expected return vs downside deviation (semi-deviation)."""
    fig, ax = plt.subplots(figsize=(14, 8))

    means = [p['mean_return'] * 100 for p in portfolio_stats]
    downside_devs = [p['downside_deviation'] * 100 for p in portfolio_stats]

    # Color by Sortino ratio (return per unit downside risk)
    rf_rate = 2.0
    sortino_ratios = [(m - rf_rate) / dd if dd > 0 else 0 for m, dd in zip(means, downside_devs)]

    scatter = ax.scatter(downside_devs, means, c=sortino_ratios, cmap='RdPu',
                        alpha=0.6, s=20, edgecolors='none')

    # Mark special portfolios
    min_downside_idx = np.argmin(downside_devs)
    max_return_idx = np.argmax(means)
    max_sortino_idx = np.argmax(sortino_ratios)

    ax.scatter(downside_devs[min_downside_idx], means[min_downside_idx],
              marker='*', s=250, c='blue', edgecolors='black',
              linewidths=0.8, label='Min Downside Risk', zorder=10)
    ax.scatter(downside_devs[max_return_idx], means[max_return_idx],
              marker='*', s=250, c='green', edgecolors='black',
              linewidths=0.8, label='Max Return', zorder=10)
    ax.scatter(downside_devs[max_sortino_idx], means[max_sortino_idx],
              marker='*', s=250, c='gold', edgecolors='black',
              linewidths=0.8, label='Max Sortino', zorder=10)

    # Add portfolio composition legends (if tickers provided)
    # Position outside the plot area on the right side, past the colorbar
    if tickers is not None:
        # Max Sortino portfolio composition (top)
        comp = format_portfolio_composition(portfolio_stats[max_sortino_idx]['weights'], tickers, top_n=15)
        textstr = f"Max Sortino\nPortfolio:\n{comp}"
        # Position at (1.25, 1.0) - past colorbar, aligned with top
        ax.text(1.25, 1.0, textstr, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        # Max Return portfolio composition (middle)
        maxret_comp = format_portfolio_composition(portfolio_stats[max_return_idx]['weights'], tickers, top_n=15)
        textstr_maxret = f"Max Return\nPortfolio:\n{maxret_comp}"
        # Position at (1.25, 0.7) - past colorbar, middle
        ax.text(1.25, 0.7, textstr_maxret, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        # Min Downside Risk portfolio composition (bottom)
        mindown_comp = format_portfolio_composition(portfolio_stats[min_downside_idx]['weights'], tickers, top_n=15)
        textstr_mindown = f"Min Downside\nRisk Portfolio:\n{mindown_comp}"
        # Position at (1.25, 0.4) - past colorbar, bottom
        ax.text(1.25, 0.4, textstr_mindown, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    # Determine best legend location based on star positions
    star_positions = [
        (downside_devs[min_downside_idx], means[min_downside_idx]),
        (downside_devs[max_return_idx], means[max_return_idx]),
        (downside_devs[max_sortino_idx], means[max_sortino_idx])
    ]
    x_range = (min(downside_devs), max(downside_devs))
    y_range = (min(means), max(means))
    legend_loc = choose_best_legend_location(star_positions, x_range, y_range)

    # Formatting
    ax.set_xlabel('Downside Deviation (Semi-Std Dev, %)', fontsize=12)
    ax.set_ylabel('Expected Return (%)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=10, loc=legend_loc)

    # Add colorbar
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label('Sortino Ratio', fontsize=10)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Downside deviation frontier saved: {output_file}")

    # Print stats
    print(f"\nMax Sortino Portfolio:")
    print(f"  Downside Risk: {downside_devs[max_sortino_idx]:.2f}%, Return: {means[max_sortino_idx]:.2f}%")
    print(f"  Sortino: {sortino_ratios[max_sortino_idx]:.3f}")
    print(f"  Weights: {portfolio_stats[max_sortino_idx]['weights']}")


def plot_cvar_frontier(portfolio_stats, output_file, tickers=None, title="CVaR Efficient Frontier"):
    """Plot expected return vs CVaR (Conditional Value-at-Risk)."""
    fig, ax = plt.subplots(figsize=(14, 8))

    means = [p['mean_return'] * 100 for p in portfolio_stats]
    # Negate CVaR for plotting (more negative CVaR = more risk)
    cvars = [-p['cvar_5'] * 100 for p in portfolio_stats]

    # Color by return/CVaR ratio
    cvar_ratios = [m / cv if cv > 0 else 0 for m, cv in zip(means, cvars)]

    scatter = ax.scatter(cvars, means, c=cvar_ratios, cmap='RdPu',
                        alpha=0.6, s=20, edgecolors='none')

    # Mark special portfolios
    min_cvar_idx = np.argmin(cvars)
    max_return_idx = np.argmax(means)
    max_ratio_idx = np.argmax(cvar_ratios)

    ax.scatter(cvars[min_cvar_idx], means[min_cvar_idx],
              marker='*', s=250, c='blue', edgecolors='black',
              linewidths=0.8, label='Min CVaR', zorder=10)
    ax.scatter(cvars[max_return_idx], means[max_return_idx],
              marker='*', s=250, c='green', edgecolors='black',
              linewidths=0.8, label='Max Return', zorder=10)
    ax.scatter(cvars[max_ratio_idx], means[max_ratio_idx],
              marker='*', s=250, c='gold', edgecolors='black',
              linewidths=0.8, label='Max Return/CVaR', zorder=10)

    # Add portfolio composition legends (if tickers provided)
    # Position outside the plot area on the right side, past the colorbar
    if tickers is not None:
        # Max Return/CVaR portfolio composition (top)
        comp = format_portfolio_composition(portfolio_stats[max_ratio_idx]['weights'], tickers, top_n=15)
        textstr = f"Max Return/CVaR\nPortfolio:\n{comp}"
        # Position at (1.25, 1.0) - past colorbar, aligned with top
        ax.text(1.25, 1.0, textstr, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        # Max Return portfolio composition (middle)
        maxret_comp = format_portfolio_composition(portfolio_stats[max_return_idx]['weights'], tickers, top_n=15)
        textstr_maxret = f"Max Return\nPortfolio:\n{maxret_comp}"
        # Position at (1.25, 0.7) - past colorbar, middle
        ax.text(1.25, 0.7, textstr_maxret, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        # Min CVaR portfolio composition (bottom)
        mincvar_comp = format_portfolio_composition(portfolio_stats[min_cvar_idx]['weights'], tickers, top_n=15)
        textstr_mincvar = f"Min CVaR\nPortfolio:\n{mincvar_comp}"
        # Position at (1.25, 0.4) - past colorbar, bottom
        ax.text(1.25, 0.4, textstr_mincvar, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    # Determine best legend location based on star positions
    star_positions = [
        (cvars[min_cvar_idx], means[min_cvar_idx]),
        (cvars[max_return_idx], means[max_return_idx]),
        (cvars[max_ratio_idx], means[max_ratio_idx])
    ]
    x_range = (min(cvars), max(cvars))
    y_range = (min(means), max(means))
    legend_loc = choose_best_legend_location(star_positions, x_range, y_range)

    # Formatting
    ax.set_xlabel('CVaR (5%, Expected Loss in Worst 5%, %)', fontsize=12)
    ax.set_ylabel('Expected Return (%)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=10, loc=legend_loc)

    # Add colorbar
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label('Return/CVaR Ratio', fontsize=10)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"CVaR frontier saved: {output_file}")

    # Print stats
    print(f"\nMin CVaR Portfolio:")
    print(f"  CVaR: {cvars[min_cvar_idx]:.2f}%, Return: {means[min_cvar_idx]:.2f}%")
    print(f"  Weights: {portfolio_stats[min_cvar_idx]['weights']}")


def plot_var_frontier(portfolio_stats, output_file, tickers=None, title="VaR Efficient Frontier"):
    """Plot expected return vs VaR (Value-at-Risk)."""
    fig, ax = plt.subplots(figsize=(14, 8))

    means = [p['mean_return'] * 100 for p in portfolio_stats]
    # Negate VaR for plotting (more negative VaR = more risk)
    vars = [-p['var_5'] * 100 for p in portfolio_stats]

    # Color by return/VaR ratio
    var_ratios = [m / v if v > 0 else 0 for m, v in zip(means, vars)]

    scatter = ax.scatter(vars, means, c=var_ratios, cmap='RdPu',
                        alpha=0.6, s=20, edgecolors='none')

    # Mark special portfolios
    min_var_idx = np.argmin(vars)
    max_return_idx = np.argmax(means)
    max_ratio_idx = np.argmax(var_ratios)

    ax.scatter(vars[min_var_idx], means[min_var_idx],
              marker='*', s=250, c='blue', edgecolors='black',
              linewidths=0.8, label='Min VaR', zorder=10)
    ax.scatter(vars[max_return_idx], means[max_return_idx],
              marker='*', s=250, c='green', edgecolors='black',
              linewidths=0.8, label='Max Return', zorder=10)
    ax.scatter(vars[max_ratio_idx], means[max_ratio_idx],
              marker='*', s=250, c='gold', edgecolors='black',
              linewidths=0.8, label='Max Return/VaR', zorder=10)

    # Add portfolio composition legends (if tickers provided)
    # Position outside the plot area on the right side, past the colorbar
    if tickers is not None:
        # Max Return/VaR portfolio composition (top)
        comp = format_portfolio_composition(portfolio_stats[max_ratio_idx]['weights'], tickers, top_n=15)
        textstr = f"Max Return/VaR\nPortfolio:\n{comp}"
        # Position at (1.25, 1.0) - past colorbar, aligned with top
        ax.text(1.25, 1.0, textstr, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        # Max Return portfolio composition (middle)
        maxret_comp = format_portfolio_composition(portfolio_stats[max_return_idx]['weights'], tickers, top_n=15)
        textstr_maxret = f"Max Return\nPortfolio:\n{maxret_comp}"
        # Position at (1.25, 0.7) - past colorbar, middle
        ax.text(1.25, 0.7, textstr_maxret, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        # Min VaR portfolio composition (bottom)
        minvar_comp = format_portfolio_composition(portfolio_stats[min_var_idx]['weights'], tickers, top_n=15)
        textstr_minvar = f"Min VaR\nPortfolio:\n{minvar_comp}"
        # Position at (1.25, 0.4) - past colorbar, bottom
        ax.text(1.25, 0.4, textstr_minvar, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    # Determine best legend location based on star positions
    star_positions = [
        (vars[min_var_idx], means[min_var_idx]),
        (vars[max_return_idx], means[max_return_idx]),
        (vars[max_ratio_idx], means[max_ratio_idx])
    ]
    x_range = (min(vars), max(vars))
    y_range = (min(means), max(means))
    legend_loc = choose_best_legend_location(star_positions, x_range, y_range)

    # Formatting
    ax.set_xlabel('VaR (5%, 5th Percentile Loss, %)', fontsize=12)
    ax.set_ylabel('Expected Return (%)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=10, loc=legend_loc)

    # Add colorbar
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label('Return/VaR Ratio', fontsize=10)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"VaR frontier saved: {output_file}")

    # Print stats
    print(f"\nMin VaR Portfolio:")
    print(f"  VaR: {vars[min_var_idx]:.2f}%, Return: {means[min_var_idx]:.2f}%")
    print(f"  Weights: {portfolio_stats[min_var_idx]['weights']}")


def plot_max_drawdown_frontier(portfolio_stats, output_file, tickers=None, title="Max Drawdown Frontier"):
    """Plot expected return vs maximum drawdown."""
    fig, ax = plt.subplots(figsize=(14, 8))

    means = [p['mean_return'] * 100 for p in portfolio_stats]
    max_drawdowns = [p['max_drawdown'] * 100 for p in portfolio_stats]

    # Color by Calmar ratio (return per unit drawdown)
    calmar_ratios = [m / dd if dd > 0 else 0 for m, dd in zip(means, max_drawdowns)]

    scatter = ax.scatter(max_drawdowns, means, c=calmar_ratios, cmap='RdPu',
                        alpha=0.6, s=20, edgecolors='none')

    # Mark special portfolios
    min_dd_idx = np.argmin(max_drawdowns)
    max_return_idx = np.argmax(means)
    max_calmar_idx = np.argmax(calmar_ratios)

    ax.scatter(max_drawdowns[min_dd_idx], means[min_dd_idx],
              marker='*', s=250, c='blue', edgecolors='black',
              linewidths=0.8, label='Min Drawdown', zorder=10)
    ax.scatter(max_drawdowns[max_return_idx], means[max_return_idx],
              marker='*', s=250, c='green', edgecolors='black',
              linewidths=0.8, label='Max Return', zorder=10)
    ax.scatter(max_drawdowns[max_calmar_idx], means[max_calmar_idx],
              marker='*', s=250, c='gold', edgecolors='black',
              linewidths=0.8, label='Max Calmar', zorder=10)

    # Add portfolio composition legends (if tickers provided)
    # Position outside the plot area on the right side, past the colorbar
    if tickers is not None:
        # Max Calmar portfolio composition (top)
        comp = format_portfolio_composition(portfolio_stats[max_calmar_idx]['weights'], tickers, top_n=15)
        textstr = f"Max Calmar\nPortfolio:\n{comp}"
        # Position at (1.25, 1.0) - past colorbar, aligned with top
        ax.text(1.25, 1.0, textstr, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        # Max Return portfolio composition (middle)
        maxret_comp = format_portfolio_composition(portfolio_stats[max_return_idx]['weights'], tickers, top_n=15)
        textstr_maxret = f"Max Return\nPortfolio:\n{maxret_comp}"
        # Position at (1.25, 0.7) - past colorbar, middle
        ax.text(1.25, 0.7, textstr_maxret, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        # Min Drawdown portfolio composition (bottom)
        mindd_comp = format_portfolio_composition(portfolio_stats[min_dd_idx]['weights'], tickers, top_n=15)
        textstr_mindd = f"Min Drawdown\nPortfolio:\n{mindd_comp}"
        # Position at (1.25, 0.4) - past colorbar, bottom
        ax.text(1.25, 0.4, textstr_mindd, transform=ax.transAxes, fontsize=7,
                verticalalignment='top', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    # Determine best legend location based on star positions
    star_positions = [
        (max_drawdowns[min_dd_idx], means[min_dd_idx]),
        (max_drawdowns[max_return_idx], means[max_return_idx]),
        (max_drawdowns[max_calmar_idx], means[max_calmar_idx])
    ]
    x_range = (min(max_drawdowns), max(max_drawdowns))
    y_range = (min(means), max(means))
    legend_loc = choose_best_legend_location(star_positions, x_range, y_range)

    # Formatting
    ax.set_xlabel('Max Drawdown (Median to Worst Case, %)', fontsize=12)
    ax.set_ylabel('Expected Return (%)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=10, loc=legend_loc)

    # Add colorbar
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label('Calmar Ratio', fontsize=10)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Max drawdown frontier saved: {output_file}")

    # Print stats
    print(f"\nMax Calmar Portfolio:")
    print(f"  Max Drawdown: {max_drawdowns[max_calmar_idx]:.2f}%, Return: {means[max_calmar_idx]:.2f}%")
    print(f"  Calmar: {calmar_ratios[max_calmar_idx]:.3f}")
    print(f"  Weights: {portfolio_stats[max_calmar_idx]['weights']}")


def plot_combined_efficient_frontier(portfolio_stats_fcff, portfolio_stats_fcfe, output_file, tickers=None):
    """Plot combined FCFF and FCFE risk-return efficient frontiers with shared x-axis."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12), sharex=True)

    rf_rate = 2.0

    # FCFF (top)
    means_fcff = [p['mean_return'] * 100 for p in portfolio_stats_fcff]
    stds_fcff = [p['std_return'] * 100 for p in portfolio_stats_fcff]
    sharpe_ratios_fcff = [(m - rf_rate) / s if s > 0 else 0 for m, s in zip(means_fcff, stds_fcff)]

    scatter1 = ax1.scatter(stds_fcff, means_fcff, c=sharpe_ratios_fcff, cmap='RdPu',
                          alpha=0.6, s=20, edgecolors='none')

    min_risk_idx_fcff = np.argmin(stds_fcff)
    max_return_idx_fcff = np.argmax(means_fcff)
    max_sharpe_idx_fcff = np.argmax(sharpe_ratios_fcff)

    ax1.scatter(stds_fcff[min_risk_idx_fcff], means_fcff[min_risk_idx_fcff],
               marker='*', s=250, c='blue', edgecolors='black',
               linewidths=0.8, label='Min Variance', zorder=10)
    ax1.scatter(stds_fcff[max_return_idx_fcff], means_fcff[max_return_idx_fcff],
               marker='*', s=250, c='green', edgecolors='black',
               linewidths=0.8, label='Max Return', zorder=10)
    ax1.scatter(stds_fcff[max_sharpe_idx_fcff], means_fcff[max_sharpe_idx_fcff],
               marker='*', s=250, c='gold', edgecolors='black',
               linewidths=0.8, label='Max Sharpe', zorder=10)

    ax1.set_ylabel('Expected Return (%) - FCFF', fontsize=12)
    ax1.set_title('Portfolio Efficient Frontier (FCFF Top, FCFE Bottom)', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=10, loc='upper left')

    cbar1 = plt.colorbar(scatter1, ax=ax1)
    cbar1.set_label('Sharpe Ratio', fontsize=10)

    # Add portfolio composition legends for FCFF (top plot)
    if tickers is not None:
        sharpe_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[max_sharpe_idx_fcff]['weights'], tickers, top_n=15)
        textstr_sharpe_fcff = f"Max Sharpe (FCFF):\n{sharpe_comp_fcff}"
        ax1.text(1.25, 1.0, textstr_sharpe_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        maxret_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[max_return_idx_fcff]['weights'], tickers, top_n=15)
        textstr_maxret_fcff = f"Max Return (FCFF):\n{maxret_comp_fcff}"
        ax1.text(1.25, 0.65, textstr_maxret_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        minvar_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[min_risk_idx_fcff]['weights'], tickers, top_n=15)
        textstr_minvar_fcff = f"Min Variance (FCFF):\n{minvar_comp_fcff}"
        ax1.text(1.25, 0.3, textstr_minvar_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    # FCFE (bottom)
    means_fcfe = [p['mean_return'] * 100 for p in portfolio_stats_fcfe]
    stds_fcfe = [p['std_return'] * 100 for p in portfolio_stats_fcfe]
    sharpe_ratios_fcfe = [(m - rf_rate) / s if s > 0 else 0 for m, s in zip(means_fcfe, stds_fcfe)]

    scatter2 = ax2.scatter(stds_fcfe, means_fcfe, c=sharpe_ratios_fcfe, cmap='RdPu',
                          alpha=0.6, s=20, edgecolors='none')

    min_risk_idx_fcfe = np.argmin(stds_fcfe)
    max_return_idx_fcfe = np.argmax(means_fcfe)
    max_sharpe_idx_fcfe = np.argmax(sharpe_ratios_fcfe)

    ax2.scatter(stds_fcfe[min_risk_idx_fcfe], means_fcfe[min_risk_idx_fcfe],
               marker='*', s=250, c='blue', edgecolors='black',
               linewidths=0.8, label='Min Variance', zorder=10)
    ax2.scatter(stds_fcfe[max_return_idx_fcfe], means_fcfe[max_return_idx_fcfe],
               marker='*', s=250, c='green', edgecolors='black',
               linewidths=0.8, label='Max Return', zorder=10)
    ax2.scatter(stds_fcfe[max_sharpe_idx_fcfe], means_fcfe[max_sharpe_idx_fcfe],
               marker='*', s=250, c='gold', edgecolors='black',
               linewidths=0.8, label='Max Sharpe', zorder=10)

    ax2.set_xlabel('Portfolio Risk (Std Dev of Return, %)', fontsize=12)
    ax2.set_ylabel('Expected Return (%) - FCFE', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=10, loc='upper left')

    cbar2 = plt.colorbar(scatter2, ax=ax2)
    cbar2.set_label('Sharpe Ratio', fontsize=10)

    # Add portfolio composition legends for FCFE (bottom plot)
    if tickers is not None:
        sharpe_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[max_sharpe_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_sharpe_fcfe = f"Max Sharpe (FCFE):\n{sharpe_comp_fcfe}"
        ax2.text(1.25, 1.0, textstr_sharpe_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        maxret_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[max_return_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_maxret_fcfe = f"Max Return (FCFE):\n{maxret_comp_fcfe}"
        ax2.text(1.25, 0.65, textstr_maxret_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        minvar_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[min_risk_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_minvar_fcfe = f"Min Variance (FCFE):\n{minvar_comp_fcfe}"
        ax2.text(1.25, 0.3, textstr_minvar_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Combined risk-return frontier saved: {output_file}")


def plot_combined_tail_risk_frontier(portfolio_stats_fcff, portfolio_stats_fcfe, output_file, tickers=None):
    """Plot combined FCFF and FCFE tail risk frontiers with shared x-axis."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12), sharex=True)

    # FCFF (top)
    means_fcff = [p['mean_return'] * 100 for p in portfolio_stats_fcff]
    prob_losses_fcff = [p['prob_loss'] * 100 for p in portfolio_stats_fcff]

    scatter1 = ax1.scatter(prob_losses_fcff, means_fcff, c=means_fcff, cmap='RdPu',
                          alpha=0.6, s=20, edgecolors='none')

    min_loss_idx_fcff = np.argmin(prob_losses_fcff)
    max_return_idx_fcff = np.argmax(means_fcff)

    ax1.scatter(prob_losses_fcff[min_loss_idx_fcff], means_fcff[min_loss_idx_fcff],
               marker='*', s=250, c='blue', edgecolors='black',
               linewidths=0.8, label='Min P(Loss)', zorder=10)
    ax1.scatter(prob_losses_fcff[max_return_idx_fcff], means_fcff[max_return_idx_fcff],
               marker='*', s=250, c='green', edgecolors='black',
               linewidths=0.8, label='Max Return', zorder=10)

    ax1.set_ylabel('Expected Return (%) - FCFF', fontsize=12)
    ax1.set_title('Portfolio Tail Risk Frontier (FCFF Top, FCFE Bottom)', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=10, loc='upper right')

    cbar1 = plt.colorbar(scatter1, ax=ax1)
    cbar1.set_label('Expected Return (%)', fontsize=10)

    # Add portfolio composition legends for FCFF
    if tickers is not None:
        minloss_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[min_loss_idx_fcff]['weights'], tickers, top_n=15)
        textstr_minloss_fcff = f"Min P(Loss) (FCFF):\n{minloss_comp_fcff}"
        ax1.text(1.25, 1.0, textstr_minloss_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        maxret_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[max_return_idx_fcff]['weights'], tickers, top_n=15)
        textstr_maxret_fcff = f"Max Return (FCFF):\n{maxret_comp_fcff}"
        ax1.text(1.25, 0.6, textstr_maxret_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    # FCFE (bottom)
    means_fcfe = [p['mean_return'] * 100 for p in portfolio_stats_fcfe]
    prob_losses_fcfe = [p['prob_loss'] * 100 for p in portfolio_stats_fcfe]

    scatter2 = ax2.scatter(prob_losses_fcfe, means_fcfe, c=means_fcfe, cmap='RdPu',
                          alpha=0.6, s=20, edgecolors='none')

    min_loss_idx_fcfe = np.argmin(prob_losses_fcfe)
    max_return_idx_fcfe = np.argmax(means_fcfe)

    ax2.scatter(prob_losses_fcfe[min_loss_idx_fcfe], means_fcfe[min_loss_idx_fcfe],
               marker='*', s=250, c='blue', edgecolors='black',
               linewidths=0.8, label='Min P(Loss)', zorder=10)
    ax2.scatter(prob_losses_fcfe[max_return_idx_fcfe], means_fcfe[max_return_idx_fcfe],
               marker='*', s=250, c='green', edgecolors='black',
               linewidths=0.8, label='Max Return', zorder=10)

    ax2.set_xlabel('Probability of Loss (%)', fontsize=12)
    ax2.set_ylabel('Expected Return (%) - FCFE', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=10, loc='upper right')

    cbar2 = plt.colorbar(scatter2, ax=ax2)
    cbar2.set_label('Expected Return (%)', fontsize=10)

    # Add portfolio composition legends for FCFE
    if tickers is not None:
        minloss_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[min_loss_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_minloss_fcfe = f"Min P(Loss) (FCFE):\n{minloss_comp_fcfe}"
        ax2.text(1.25, 1.0, textstr_minloss_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        maxret_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[max_return_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_maxret_fcfe = f"Max Return (FCFE):\n{maxret_comp_fcfe}"
        ax2.text(1.25, 0.6, textstr_maxret_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Combined tail risk frontier saved: {output_file}")


def plot_combined_downside_deviation_frontier(portfolio_stats_fcff, portfolio_stats_fcfe, output_file, tickers=None):
    """Plot combined FCFF and FCFE downside deviation frontiers with shared x-axis."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12), sharex=True)

    rf_rate = 2.0

    # FCFF (top)
    means_fcff = [p['mean_return'] * 100 for p in portfolio_stats_fcff]
    downside_devs_fcff = [p['downside_deviation'] * 100 for p in portfolio_stats_fcff]
    sortino_ratios_fcff = [(m - rf_rate) / dd if dd > 0 else 0 for m, dd in zip(means_fcff, downside_devs_fcff)]

    scatter1 = ax1.scatter(downside_devs_fcff, means_fcff, c=sortino_ratios_fcff, cmap='RdPu',
                          alpha=0.6, s=20, edgecolors='none')

    min_downside_idx_fcff = np.argmin(downside_devs_fcff)
    max_return_idx_fcff = np.argmax(means_fcff)
    max_sortino_idx_fcff = np.argmax(sortino_ratios_fcff)

    ax1.scatter(downside_devs_fcff[min_downside_idx_fcff], means_fcff[min_downside_idx_fcff],
               marker='*', s=250, c='blue', edgecolors='black',
               linewidths=0.8, label='Min Downside Risk', zorder=10)
    ax1.scatter(downside_devs_fcff[max_return_idx_fcff], means_fcff[max_return_idx_fcff],
               marker='*', s=250, c='green', edgecolors='black',
               linewidths=0.8, label='Max Return', zorder=10)
    ax1.scatter(downside_devs_fcff[max_sortino_idx_fcff], means_fcff[max_sortino_idx_fcff],
               marker='*', s=250, c='gold', edgecolors='black',
               linewidths=0.8, label='Max Sortino', zorder=10)

    ax1.set_ylabel('Expected Return (%) - FCFF', fontsize=12)
    ax1.set_title('Downside Deviation Frontier (FCFF Top, FCFE Bottom)', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=10, loc='upper left')

    cbar1 = plt.colorbar(scatter1, ax=ax1)
    cbar1.set_label('Sortino Ratio', fontsize=10)

    # Add portfolio composition legends for FCFF
    if tickers is not None:
        sortino_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[max_sortino_idx_fcff]['weights'], tickers, top_n=15)
        textstr_sortino_fcff = f"Max Sortino (FCFF):\n{sortino_comp_fcff}"
        ax1.text(1.25, 1.0, textstr_sortino_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        maxret_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[max_return_idx_fcff]['weights'], tickers, top_n=15)
        textstr_maxret_fcff = f"Max Return (FCFF):\n{maxret_comp_fcff}"
        ax1.text(1.25, 0.65, textstr_maxret_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        mindown_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[min_downside_idx_fcff]['weights'], tickers, top_n=15)
        textstr_mindown_fcff = f"Min Downside Risk (FCFF):\n{mindown_comp_fcff}"
        ax1.text(1.25, 0.3, textstr_mindown_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    # FCFE (bottom)
    means_fcfe = [p['mean_return'] * 100 for p in portfolio_stats_fcfe]
    downside_devs_fcfe = [p['downside_deviation'] * 100 for p in portfolio_stats_fcfe]
    sortino_ratios_fcfe = [(m - rf_rate) / dd if dd > 0 else 0 for m, dd in zip(means_fcfe, downside_devs_fcfe)]

    scatter2 = ax2.scatter(downside_devs_fcfe, means_fcfe, c=sortino_ratios_fcfe, cmap='RdPu',
                          alpha=0.6, s=20, edgecolors='none')

    min_downside_idx_fcfe = np.argmin(downside_devs_fcfe)
    max_return_idx_fcfe = np.argmax(means_fcfe)
    max_sortino_idx_fcfe = np.argmax(sortino_ratios_fcfe)

    ax2.scatter(downside_devs_fcfe[min_downside_idx_fcfe], means_fcfe[min_downside_idx_fcfe],
               marker='*', s=250, c='blue', edgecolors='black',
               linewidths=0.8, label='Min Downside Risk', zorder=10)
    ax2.scatter(downside_devs_fcfe[max_return_idx_fcfe], means_fcfe[max_return_idx_fcfe],
               marker='*', s=250, c='green', edgecolors='black',
               linewidths=0.8, label='Max Return', zorder=10)
    ax2.scatter(downside_devs_fcfe[max_sortino_idx_fcfe], means_fcfe[max_sortino_idx_fcfe],
               marker='*', s=250, c='gold', edgecolors='black',
               linewidths=0.8, label='Max Sortino', zorder=10)

    ax2.set_xlabel('Downside Deviation (Semi-Std Dev, %)', fontsize=12)
    ax2.set_ylabel('Expected Return (%) - FCFE', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=10, loc='upper left')

    cbar2 = plt.colorbar(scatter2, ax=ax2)
    cbar2.set_label('Sortino Ratio', fontsize=10)

    # Add portfolio composition legends for FCFE
    if tickers is not None:
        sortino_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[max_sortino_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_sortino_fcfe = f"Max Sortino (FCFE):\n{sortino_comp_fcfe}"
        ax2.text(1.25, 1.0, textstr_sortino_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        maxret_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[max_return_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_maxret_fcfe = f"Max Return (FCFE):\n{maxret_comp_fcfe}"
        ax2.text(1.25, 0.65, textstr_maxret_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        mindown_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[min_downside_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_mindown_fcfe = f"Min Downside Risk (FCFE):\n{mindown_comp_fcfe}"
        ax2.text(1.25, 0.3, textstr_mindown_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Combined downside deviation frontier saved: {output_file}")


def plot_combined_cvar_frontier(portfolio_stats_fcff, portfolio_stats_fcfe, output_file, tickers=None):
    """Plot combined FCFF and FCFE CVaR frontiers with shared x-axis."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12), sharex=True)

    # FCFF (top)
    means_fcff = [p['mean_return'] * 100 for p in portfolio_stats_fcff]
    cvars_fcff = [-p['cvar_5'] * 100 for p in portfolio_stats_fcff]
    cvar_ratios_fcff = [m / cv if cv > 0 else 0 for m, cv in zip(means_fcff, cvars_fcff)]

    scatter1 = ax1.scatter(cvars_fcff, means_fcff, c=cvar_ratios_fcff, cmap='RdPu',
                          alpha=0.6, s=20, edgecolors='none')

    min_cvar_idx_fcff = np.argmin(cvars_fcff)
    max_return_idx_fcff = np.argmax(means_fcff)
    max_ratio_idx_fcff = np.argmax(cvar_ratios_fcff)

    ax1.scatter(cvars_fcff[min_cvar_idx_fcff], means_fcff[min_cvar_idx_fcff],
               marker='*', s=250, c='blue', edgecolors='black',
               linewidths=0.8, label='Min CVaR', zorder=10)
    ax1.scatter(cvars_fcff[max_return_idx_fcff], means_fcff[max_return_idx_fcff],
               marker='*', s=250, c='green', edgecolors='black',
               linewidths=0.8, label='Max Return', zorder=10)
    ax1.scatter(cvars_fcff[max_ratio_idx_fcff], means_fcff[max_ratio_idx_fcff],
               marker='*', s=250, c='gold', edgecolors='black',
               linewidths=0.8, label='Max Return/CVaR', zorder=10)

    ax1.set_ylabel('Expected Return (%) - FCFF', fontsize=12)
    ax1.set_title('CVaR Efficient Frontier (FCFF Top, FCFE Bottom)', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=10, loc='upper left')

    cbar1 = plt.colorbar(scatter1, ax=ax1)
    cbar1.set_label('Return/CVaR Ratio', fontsize=10)

    # Add portfolio composition legends for FCFF
    if tickers is not None:
        ratio_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[max_ratio_idx_fcff]['weights'], tickers, top_n=15)
        textstr_ratio_fcff = f"Max Return/CVaR (FCFF):\n{ratio_comp_fcff}"
        ax1.text(1.25, 1.0, textstr_ratio_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        maxret_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[max_return_idx_fcff]['weights'], tickers, top_n=15)
        textstr_maxret_fcff = f"Max Return (FCFF):\n{maxret_comp_fcff}"
        ax1.text(1.25, 0.65, textstr_maxret_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        mincvar_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[min_cvar_idx_fcff]['weights'], tickers, top_n=15)
        textstr_mincvar_fcff = f"Min CVaR (FCFF):\n{mincvar_comp_fcff}"
        ax1.text(1.25, 0.3, textstr_mincvar_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    # FCFE (bottom)
    means_fcfe = [p['mean_return'] * 100 for p in portfolio_stats_fcfe]
    cvars_fcfe = [-p['cvar_5'] * 100 for p in portfolio_stats_fcfe]
    cvar_ratios_fcfe = [m / cv if cv > 0 else 0 for m, cv in zip(means_fcfe, cvars_fcfe)]

    scatter2 = ax2.scatter(cvars_fcfe, means_fcfe, c=cvar_ratios_fcfe, cmap='RdPu',
                          alpha=0.6, s=20, edgecolors='none')

    min_cvar_idx_fcfe = np.argmin(cvars_fcfe)
    max_return_idx_fcfe = np.argmax(means_fcfe)
    max_ratio_idx_fcfe = np.argmax(cvar_ratios_fcfe)

    ax2.scatter(cvars_fcfe[min_cvar_idx_fcfe], means_fcfe[min_cvar_idx_fcfe],
               marker='*', s=250, c='blue', edgecolors='black',
               linewidths=0.8, label='Min CVaR', zorder=10)
    ax2.scatter(cvars_fcfe[max_return_idx_fcfe], means_fcfe[max_return_idx_fcfe],
               marker='*', s=250, c='green', edgecolors='black',
               linewidths=0.8, label='Max Return', zorder=10)
    ax2.scatter(cvars_fcfe[max_ratio_idx_fcfe], means_fcfe[max_ratio_idx_fcfe],
               marker='*', s=250, c='gold', edgecolors='black',
               linewidths=0.8, label='Max Return/CVaR', zorder=10)

    ax2.set_xlabel('CVaR (5%, Expected Loss in Worst 5%, %)', fontsize=12)
    ax2.set_ylabel('Expected Return (%) - FCFE', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=10, loc='upper left')

    cbar2 = plt.colorbar(scatter2, ax=ax2)
    cbar2.set_label('Return/CVaR Ratio', fontsize=10)

    # Add portfolio composition legends for FCFE
    if tickers is not None:
        ratio_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[max_ratio_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_ratio_fcfe = f"Max Return/CVaR (FCFE):\n{ratio_comp_fcfe}"
        ax2.text(1.25, 1.0, textstr_ratio_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        maxret_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[max_return_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_maxret_fcfe = f"Max Return (FCFE):\n{maxret_comp_fcfe}"
        ax2.text(1.25, 0.65, textstr_maxret_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        mincvar_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[min_cvar_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_mincvar_fcfe = f"Min CVaR (FCFE):\n{mincvar_comp_fcfe}"
        ax2.text(1.25, 0.3, textstr_mincvar_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Combined CVaR frontier saved: {output_file}")


def plot_combined_var_frontier(portfolio_stats_fcff, portfolio_stats_fcfe, output_file, tickers=None):
    """Plot combined FCFF and FCFE VaR frontiers with shared x-axis."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12), sharex=True)

    # FCFF (top)
    means_fcff = [p['mean_return'] * 100 for p in portfolio_stats_fcff]
    vars_fcff = [-p['var_5'] * 100 for p in portfolio_stats_fcff]
    var_ratios_fcff = [m / v if v > 0 else 0 for m, v in zip(means_fcff, vars_fcff)]

    scatter1 = ax1.scatter(vars_fcff, means_fcff, c=var_ratios_fcff, cmap='RdPu',
                          alpha=0.6, s=20, edgecolors='none')

    min_var_idx_fcff = np.argmin(vars_fcff)
    max_return_idx_fcff = np.argmax(means_fcff)
    max_ratio_idx_fcff = np.argmax(var_ratios_fcff)

    ax1.scatter(vars_fcff[min_var_idx_fcff], means_fcff[min_var_idx_fcff],
               marker='*', s=250, c='blue', edgecolors='black',
               linewidths=0.8, label='Min VaR', zorder=10)
    ax1.scatter(vars_fcff[max_return_idx_fcff], means_fcff[max_return_idx_fcff],
               marker='*', s=250, c='green', edgecolors='black',
               linewidths=0.8, label='Max Return', zorder=10)
    ax1.scatter(vars_fcff[max_ratio_idx_fcff], means_fcff[max_ratio_idx_fcff],
               marker='*', s=250, c='gold', edgecolors='black',
               linewidths=0.8, label='Max Return/VaR', zorder=10)

    ax1.set_ylabel('Expected Return (%) - FCFF', fontsize=12)
    ax1.set_title('VaR Efficient Frontier (FCFF Top, FCFE Bottom)', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=10, loc='upper left')

    cbar1 = plt.colorbar(scatter1, ax=ax1)
    cbar1.set_label('Return/VaR Ratio', fontsize=10)

    # Add portfolio composition legends for FCFF
    if tickers is not None:
        ratio_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[max_ratio_idx_fcff]['weights'], tickers, top_n=15)
        textstr_ratio_fcff = f"Max Return/VaR (FCFF):\n{ratio_comp_fcff}"
        ax1.text(1.25, 1.0, textstr_ratio_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        maxret_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[max_return_idx_fcff]['weights'], tickers, top_n=15)
        textstr_maxret_fcff = f"Max Return (FCFF):\n{maxret_comp_fcff}"
        ax1.text(1.25, 0.65, textstr_maxret_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        minvar_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[min_var_idx_fcff]['weights'], tickers, top_n=15)
        textstr_minvar_fcff = f"Min VaR (FCFF):\n{minvar_comp_fcff}"
        ax1.text(1.25, 0.3, textstr_minvar_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    # FCFE (bottom)
    means_fcfe = [p['mean_return'] * 100 for p in portfolio_stats_fcfe]
    vars_fcfe = [-p['var_5'] * 100 for p in portfolio_stats_fcfe]
    var_ratios_fcfe = [m / v if v > 0 else 0 for m, v in zip(means_fcfe, vars_fcfe)]

    scatter2 = ax2.scatter(vars_fcfe, means_fcfe, c=var_ratios_fcfe, cmap='RdPu',
                          alpha=0.6, s=20, edgecolors='none')

    min_var_idx_fcfe = np.argmin(vars_fcfe)
    max_return_idx_fcfe = np.argmax(means_fcfe)
    max_ratio_idx_fcfe = np.argmax(var_ratios_fcfe)

    ax2.scatter(vars_fcfe[min_var_idx_fcfe], means_fcfe[min_var_idx_fcfe],
               marker='*', s=250, c='blue', edgecolors='black',
               linewidths=0.8, label='Min VaR', zorder=10)
    ax2.scatter(vars_fcfe[max_return_idx_fcfe], means_fcfe[max_return_idx_fcfe],
               marker='*', s=250, c='green', edgecolors='black',
               linewidths=0.8, label='Max Return', zorder=10)
    ax2.scatter(vars_fcfe[max_ratio_idx_fcfe], means_fcfe[max_ratio_idx_fcfe],
               marker='*', s=250, c='gold', edgecolors='black',
               linewidths=0.8, label='Max Return/VaR', zorder=10)

    ax2.set_xlabel('VaR (5%, 5th Percentile Loss, %)', fontsize=12)
    ax2.set_ylabel('Expected Return (%) - FCFE', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=10, loc='upper left')

    cbar2 = plt.colorbar(scatter2, ax=ax2)
    cbar2.set_label('Return/VaR Ratio', fontsize=10)

    # Add portfolio composition legends for FCFE
    if tickers is not None:
        ratio_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[max_ratio_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_ratio_fcfe = f"Max Return/VaR (FCFE):\n{ratio_comp_fcfe}"
        ax2.text(1.25, 1.0, textstr_ratio_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        maxret_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[max_return_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_maxret_fcfe = f"Max Return (FCFE):\n{maxret_comp_fcfe}"
        ax2.text(1.25, 0.65, textstr_maxret_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        minvar_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[min_var_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_minvar_fcfe = f"Min VaR (FCFE):\n{minvar_comp_fcfe}"
        ax2.text(1.25, 0.3, textstr_minvar_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Combined VaR frontier saved: {output_file}")


def plot_combined_max_drawdown_frontier(portfolio_stats_fcff, portfolio_stats_fcfe, output_file, tickers=None):
    """Plot combined FCFF and FCFE max drawdown frontiers with shared x-axis."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12), sharex=True)

    # FCFF (top)
    means_fcff = [p['mean_return'] * 100 for p in portfolio_stats_fcff]
    max_drawdowns_fcff = [p['max_drawdown'] * 100 for p in portfolio_stats_fcff]
    calmar_ratios_fcff = [m / dd if dd > 0 else 0 for m, dd in zip(means_fcff, max_drawdowns_fcff)]

    scatter1 = ax1.scatter(max_drawdowns_fcff, means_fcff, c=calmar_ratios_fcff, cmap='RdPu',
                          alpha=0.6, s=20, edgecolors='none')

    min_dd_idx_fcff = np.argmin(max_drawdowns_fcff)
    max_return_idx_fcff = np.argmax(means_fcff)
    max_calmar_idx_fcff = np.argmax(calmar_ratios_fcff)

    ax1.scatter(max_drawdowns_fcff[min_dd_idx_fcff], means_fcff[min_dd_idx_fcff],
               marker='*', s=250, c='blue', edgecolors='black',
               linewidths=0.8, label='Min Drawdown', zorder=10)
    ax1.scatter(max_drawdowns_fcff[max_return_idx_fcff], means_fcff[max_return_idx_fcff],
               marker='*', s=250, c='green', edgecolors='black',
               linewidths=0.8, label='Max Return', zorder=10)
    ax1.scatter(max_drawdowns_fcff[max_calmar_idx_fcff], means_fcff[max_calmar_idx_fcff],
               marker='*', s=250, c='gold', edgecolors='black',
               linewidths=0.8, label='Max Calmar', zorder=10)

    ax1.set_ylabel('Expected Return (%) - FCFF', fontsize=12)
    ax1.set_title('Max Drawdown Frontier (FCFF Top, FCFE Bottom)', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=10, loc='upper left')

    cbar1 = plt.colorbar(scatter1, ax=ax1)
    cbar1.set_label('Calmar Ratio', fontsize=10)

    # Add portfolio composition legends for FCFF
    if tickers is not None:
        calmar_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[max_calmar_idx_fcff]['weights'], tickers, top_n=15)
        textstr_calmar_fcff = f"Max Calmar (FCFF):\n{calmar_comp_fcff}"
        ax1.text(1.25, 1.0, textstr_calmar_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        maxret_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[max_return_idx_fcff]['weights'], tickers, top_n=15)
        textstr_maxret_fcff = f"Max Return (FCFF):\n{maxret_comp_fcff}"
        ax1.text(1.25, 0.65, textstr_maxret_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        mindd_comp_fcff = format_portfolio_composition(portfolio_stats_fcff[min_dd_idx_fcff]['weights'], tickers, top_n=15)
        textstr_mindd_fcff = f"Min Drawdown (FCFF):\n{mindd_comp_fcff}"
        ax1.text(1.25, 0.3, textstr_mindd_fcff, transform=ax1.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    # FCFE (bottom)
    means_fcfe = [p['mean_return'] * 100 for p in portfolio_stats_fcfe]
    max_drawdowns_fcfe = [p['max_drawdown'] * 100 for p in portfolio_stats_fcfe]
    calmar_ratios_fcfe = [m / dd if dd > 0 else 0 for m, dd in zip(means_fcfe, max_drawdowns_fcfe)]

    scatter2 = ax2.scatter(max_drawdowns_fcfe, means_fcfe, c=calmar_ratios_fcfe, cmap='RdPu',
                          alpha=0.6, s=20, edgecolors='none')

    min_dd_idx_fcfe = np.argmin(max_drawdowns_fcfe)
    max_return_idx_fcfe = np.argmax(means_fcfe)
    max_calmar_idx_fcfe = np.argmax(calmar_ratios_fcfe)

    ax2.scatter(max_drawdowns_fcfe[min_dd_idx_fcfe], means_fcfe[min_dd_idx_fcfe],
               marker='*', s=250, c='blue', edgecolors='black',
               linewidths=0.8, label='Min Drawdown', zorder=10)
    ax2.scatter(max_drawdowns_fcfe[max_return_idx_fcfe], means_fcfe[max_return_idx_fcfe],
               marker='*', s=250, c='green', edgecolors='black',
               linewidths=0.8, label='Max Return', zorder=10)
    ax2.scatter(max_drawdowns_fcfe[max_calmar_idx_fcfe], means_fcfe[max_calmar_idx_fcfe],
               marker='*', s=250, c='gold', edgecolors='black',
               linewidths=0.8, label='Max Calmar', zorder=10)

    ax2.set_xlabel('Max Drawdown (Median to Worst Case, %)', fontsize=12)
    ax2.set_ylabel('Expected Return (%) - FCFE', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=10, loc='upper left')

    cbar2 = plt.colorbar(scatter2, ax=ax2)
    cbar2.set_label('Calmar Ratio', fontsize=10)

    # Add portfolio composition legends for FCFE
    if tickers is not None:
        calmar_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[max_calmar_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_calmar_fcfe = f"Max Calmar (FCFE):\n{calmar_comp_fcfe}"
        ax2.text(1.25, 1.0, textstr_calmar_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        maxret_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[max_return_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_maxret_fcfe = f"Max Return (FCFE):\n{maxret_comp_fcfe}"
        ax2.text(1.25, 0.65, textstr_maxret_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

        mindd_comp_fcfe = format_portfolio_composition(portfolio_stats_fcfe[min_dd_idx_fcfe]['weights'], tickers, top_n=15)
        textstr_mindd_fcfe = f"Min Drawdown (FCFE):\n{mindd_comp_fcfe}"
        ax2.text(1.25, 0.3, textstr_mindd_fcfe, transform=ax2.transAxes, fontsize=7,
                verticalalignment='top', family='monospace', color='black',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8,
                         edgecolor='black', linewidth=1.5))

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Combined max drawdown frontier saved: {output_file}")


def print_correlation_summary(correlation_matrix):
    """Print summary statistics of correlations."""
    # Get upper triangle (exclude diagonal)
    mask = np.triu(np.ones_like(correlation_matrix, dtype=bool), k=1)
    correlations = correlation_matrix.where(mask).stack()

    print("\n" + "="*60)
    print("CORRELATION SUMMARY")
    print("="*60)
    print(f"Mean correlation: {correlations.mean():.3f}")
    print(f"Median correlation: {correlations.median():.3f}")
    print(f"Min correlation: {correlations.min():.3f}")
    print(f"Max correlation: {correlations.max():.3f}")
    print(f"Std of correlations: {correlations.std():.3f}")

    # Find pairs with strongest correlations
    abs_corr = correlations.abs()
    top_pairs = abs_corr.nlargest(5)

    print(f"\nStrongest correlations:")
    for (asset1, asset2), corr_val in top_pairs.items():
        actual_corr = correlation_matrix.loc[asset1, asset2]
        print(f"  {asset1} <-> {asset2}: {actual_corr:+.3f}")

    # Count negative vs positive correlations
    n_positive = (correlations > 0.1).sum()
    n_negative = (correlations < -0.1).sum()
    n_neutral = len(correlations) - n_positive - n_negative

    print(f"\nCorrelation distribution (|r| > 0.1):")
    print(f"  Positive: {n_positive} ({n_positive/len(correlations)*100:.1f}%)")
    print(f"  Negative: {n_negative} ({n_negative/len(correlations)*100:.1f}%)")
    print(f"  Neutral:  {n_neutral} ({n_neutral/len(correlations)*100:.1f}%)")
    print("="*60)


def main():
    parser = argparse.ArgumentParser(description="Generate portfolio efficient frontier plots")
    parser.add_argument("--output-dir", default="../output", help="Output directory with CSV files")
    parser.add_argument("--viz-dir", default="../output", help="Directory to save visualizations")
    parser.add_argument("--n-portfolios", type=int, default=5000,
                       help="Number of random portfolios to generate")
    parser.add_argument("--method", default="fcfe", choices=["fcfe", "fcff", "combined"],
                       help="Valuation method to use (fcfe, fcff, or combined for vertically stacked plots)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    # Create organized directory structure
    data_dir = output_dir / "data"

    # For combined mode, put directly in multi_asset/
    # For single mode (fcfe/fcff), put in multi_asset/fcfe or multi_asset/fcff
    if args.method == "combined":
        multi_asset_dir = output_dir / "multi_asset"
    else:
        multi_asset_dir = output_dir / "multi_asset" / args.method

    data_dir.mkdir(parents=True, exist_ok=True)
    multi_asset_dir.mkdir(parents=True, exist_ok=True)

    # For backward compatibility, also accept old viz_dir argument
    # but use it as the base output directory
    if args.viz_dir != "../output":
        output_dir = Path(args.viz_dir)
        data_dir = output_dir / "data"
        if args.method == "combined":
            multi_asset_dir = output_dir / "multi_asset"
        else:
            multi_asset_dir = output_dir / "multi_asset" / args.method
        data_dir.mkdir(parents=True, exist_ok=True)
        multi_asset_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Load data (try data directory first, fall back to output_dir for backward compatibility)
        prices_file = data_dir / "market_prices.csv"
        if not prices_file.exists():
            prices_file = output_dir / "market_prices.csv"

        prices = pd.read_csv(prices_file)

        if args.method == "combined":
            # Load both FCFE and FCFF for combined plots
            sim_file_fcfe = data_dir / "simulations_fcfe.csv"
            if not sim_file_fcfe.exists():
                sim_file_fcfe = output_dir / "simulations_fcfe.csv"

            sim_file_fcff = data_dir / "simulations_fcff.csv"
            if not sim_file_fcff.exists():
                sim_file_fcff = output_dir / "simulations_fcff.csv"

            if not sim_file_fcfe.exists() or not sim_file_fcff.exists():
                print(f"Error: Both simulations_fcfe.csv and simulations_fcff.csv are required for combined plots", file=sys.stderr)
                print("Run probabilistic DCF valuation for multiple tickers first.", file=sys.stderr)
                sys.exit(1)

            simulations_fcfe = pd.read_csv(sim_file_fcfe)
            simulations_fcff = pd.read_csv(sim_file_fcff)
            simulations = simulations_fcfe  # Use FCFE as default for initial processing
        elif args.method == "fcfe":
            sim_file = data_dir / "simulations_fcfe.csv"
            if not sim_file.exists():
                sim_file = output_dir / "simulations_fcfe.csv"

            if not sim_file.exists():
                print(f"Error: {sim_file} not found", file=sys.stderr)
                print("Run probabilistic DCF valuation for multiple tickers first.", file=sys.stderr)
                sys.exit(1)

            simulations = pd.read_csv(sim_file)
        else:  # fcff
            sim_file = data_dir / "simulations_fcff.csv"
            if not sim_file.exists():
                sim_file = output_dir / "simulations_fcff.csv"

            if not sim_file.exists():
                print(f"Error: {sim_file} not found", file=sys.stderr)
                print("Run probabilistic DCF valuation for multiple tickers first.", file=sys.stderr)
                sys.exit(1)

            simulations = pd.read_csv(sim_file)

        # Step 1: Handle misaligned simulations
        # For portfolio analysis, we need aligned simulations across all tickers
        all_valid_mask = simulations.notna().all(axis=1)
        common_valid_count = all_valid_mask.sum()
        total_rows = len(simulations)

        if common_valid_count < total_rows:
            print(f"\nSimulation alignment detected:")
            print(f"  Total rows in CSV: {total_rows}")
            print(f"  Rows with ALL tickers valid: {common_valid_count}")
            print(f"\nUsing common valid range ({common_valid_count} simulations) for aligned portfolio analysis...")

            # Use only rows where all tickers have data
            simulations = simulations[all_valid_mask].reset_index(drop=True)
        else:
            print(f"\nAll {total_rows} simulations are aligned across all tickers.")

        # Data quality filtering
        print(f"\nData quality check for {len(simulations.columns)} tickers...")

        tickers_to_keep = []
        tickers_to_remove = []

        for ticker in simulations.columns:
            # Check 1: Missing values
            missing_pct = simulations[ticker].isnull().sum() / len(simulations) * 100
            if missing_pct > 10:
                tickers_to_remove.append((ticker, f"{missing_pct:.1f}% missing data"))
                continue

            # Check 2: Extreme outliers
            try:
                price = prices[prices['ticker'] == ticker]['price'].values[0]
                returns = (simulations[ticker].dropna() - price) / price

                # Filter tickers with extreme outliers (>50x or <-10x)
                max_return = returns.max()
                min_return = returns.min()

                if max_return > 50 or min_return < -10:
                    tickers_to_remove.append((ticker, f"extreme returns [{min_return:.1f}, {max_return:.1f}]"))
                    continue

                tickers_to_keep.append(ticker)
            except:
                tickers_to_remove.append((ticker, "price lookup failed"))
                continue

        # Report filtering results
        if tickers_to_remove:
            print(f"\nRemoved {len(tickers_to_remove)} tickers due to data quality issues:")
            for ticker, reason in tickers_to_remove[:10]:  # Show first 10
                print(f"  - {ticker}: {reason}")
            if len(tickers_to_remove) > 10:
                print(f"  ... and {len(tickers_to_remove) - 10} more")

        # Filter datasets
        simulations = simulations[tickers_to_keep]
        prices = prices[prices['ticker'].isin(tickers_to_keep)]

        # Also filter the separate FCFF and FCFE datasets if in combined mode
        if args.method == "combined":
            simulations_fcfe = simulations_fcfe[tickers_to_keep]
            simulations_fcff = simulations_fcff[tickers_to_keep]

        # Check we have enough tickers remaining
        n_tickers = len(tickers_to_keep)
        if n_tickers < 2:
            print(f"\nError: Need at least 2 valid tickers for portfolio analysis. Found: {n_tickers}",
                  file=sys.stderr)
            print("Most tickers were filtered out due to data quality issues.", file=sys.stderr)
            print("Please re-run probabilistic DCF with valid ticker configurations.", file=sys.stderr)
            sys.exit(1)

        print(f"\nUsing {n_tickers} valid tickers: {list(simulations.columns)}")

        # Set up dark mode (Kanagawa Dragon)
        setup_dark_mode()

        # Get ticker names for portfolio composition legends
        tickers = list(simulations.columns)

        if args.method == "combined":
            # Combined mode: generate FCFF and FCFE stats with same weights, then create combined plots
            print(f"\nGenerating {args.n_portfolios} random portfolios...")
            weights_matrix = generate_random_portfolios(n_tickers, args.n_portfolios)

            # Compute stats for both FCFF and FCFE
            print(f"\nComputing FCFF portfolio statistics...")
            correlation_matrix_fcff, covariance_matrix_fcff, _ = compute_correlation_matrix(simulations_fcff, prices)
            portfolio_stats_fcff = []
            for i, weights in enumerate(weights_matrix):
                if (i + 1) % 1000 == 0:
                    print(f"  Processed {i + 1}/{args.n_portfolios} FCFF portfolios...")
                stats = compute_portfolio_stats(simulations_fcff, prices, weights, covariance_matrix_fcff)
                portfolio_stats_fcff.append(stats)

            print(f"\nComputing FCFE portfolio statistics...")
            correlation_matrix_fcfe, covariance_matrix_fcfe, _ = compute_correlation_matrix(simulations_fcfe, prices)
            portfolio_stats_fcfe = []
            for i, weights in enumerate(weights_matrix):
                if (i + 1) % 1000 == 0:
                    print(f"  Processed {i + 1}/{args.n_portfolios} FCFE portfolios...")
                stats = compute_portfolio_stats(simulations_fcfe, prices, weights, covariance_matrix_fcfe)
                portfolio_stats_fcfe.append(stats)

            # Save correlation matrices
            corr_csv_fcff = data_dir / "correlation_matrix_fcff.csv"
            correlation_matrix_fcff.to_csv(corr_csv_fcff)
            corr_csv_fcfe = data_dir / "correlation_matrix_fcfe.csv"
            correlation_matrix_fcfe.to_csv(corr_csv_fcfe)
            print(f"\nCorrelation matrices saved to: {data_dir}")

            print(f"\nGenerating combined efficient frontier visualizations...")

            # Generate all 6 combined frontier plots
            # 1. Risk-Return (Sharpe)
            risk_return_file = multi_asset_dir / "efficient_frontier_risk_return_combined.png"
            plot_combined_efficient_frontier(portfolio_stats_fcff, portfolio_stats_fcfe, risk_return_file, tickers=tickers)

            # 2. Tail Risk (P[Loss])
            tail_risk_file = multi_asset_dir / "efficient_frontier_tail_risk_combined.png"
            plot_combined_tail_risk_frontier(portfolio_stats_fcff, portfolio_stats_fcfe, tail_risk_file, tickers=tickers)

            # 3. Downside Deviation (Sortino)
            downside_file = multi_asset_dir / "efficient_frontier_downside_combined.png"
            plot_combined_downside_deviation_frontier(portfolio_stats_fcff, portfolio_stats_fcfe, downside_file, tickers=tickers)

            # 4. CVaR
            cvar_file = multi_asset_dir / "efficient_frontier_cvar_combined.png"
            plot_combined_cvar_frontier(portfolio_stats_fcff, portfolio_stats_fcfe, cvar_file, tickers=tickers)

            # 5. VaR
            var_file = multi_asset_dir / "efficient_frontier_var_combined.png"
            plot_combined_var_frontier(portfolio_stats_fcff, portfolio_stats_fcfe, var_file, tickers=tickers)

            # 6. Max Drawdown (Calmar)
            drawdown_file = multi_asset_dir / "efficient_frontier_drawdown_combined.png"
            plot_combined_max_drawdown_frontier(portfolio_stats_fcff, portfolio_stats_fcfe, drawdown_file, tickers=tickers)

            print(f"\nAll 6 combined frontier visualizations saved to: {multi_asset_dir}")

        else:
            # Single method mode (fcfe or fcff)
            print(f"\nComputing correlation matrix...")
            correlation_matrix, covariance_matrix, returns_df = compute_correlation_matrix(simulations, prices)

            # Print correlation summary
            print_correlation_summary(correlation_matrix)

            # Save correlation matrix to CSV in data directory
            corr_csv = data_dir / f"correlation_matrix_{args.method}.csv"
            correlation_matrix.to_csv(corr_csv)
            print(f"\nCorrelation matrix saved to: {corr_csv}")

            # Generate random portfolios
            print(f"\nGenerating {args.n_portfolios} random portfolios...")
            weights_matrix = generate_random_portfolios(n_tickers, args.n_portfolios)

            # Compute statistics for each portfolio (with correlation-adjusted risk)
            portfolio_stats = []
            for i, weights in enumerate(weights_matrix):
                if (i + 1) % 1000 == 0:
                    print(f"  Processed {i + 1}/{args.n_portfolios} portfolios...")

                stats = compute_portfolio_stats(simulations, prices, weights, covariance_matrix)
                portfolio_stats.append(stats)

            print(f"\nGenerating efficient frontier visualizations...")

            # Generate all 6 frontier variants (dark mode only)
            # 1. Risk-Return (Standard Deviation)
            risk_return_file = multi_asset_dir / f"efficient_frontier_risk_return_{args.method}.png"
            plot_efficient_frontier(portfolio_stats, risk_return_file, tickers=tickers,
                                   title=f"Portfolio Efficient Frontier (Std Dev) - {args.method.upper()}")

            # 2. Probability of Loss
            tail_risk_file = multi_asset_dir / f"efficient_frontier_tail_risk_{args.method}.png"
            plot_tail_risk_frontier(portfolio_stats, tail_risk_file, tickers=tickers,
                                   title=f"Portfolio Tail Risk Frontier (P[Loss]) - {args.method.upper()}")

            # 3. Downside Deviation (Sortino)
            downside_file = multi_asset_dir / f"efficient_frontier_downside_{args.method}.png"
            plot_downside_deviation_frontier(portfolio_stats, downside_file, tickers=tickers,
                                            title=f"Downside Deviation Frontier (Sortino) - {args.method.upper()}")

            # 4. CVaR (Conditional Value-at-Risk)
            cvar_file = multi_asset_dir / f"efficient_frontier_cvar_{args.method}.png"
            plot_cvar_frontier(portfolio_stats, cvar_file, tickers=tickers,
                              title=f"CVaR Efficient Frontier - {args.method.upper()}")

            # 5. VaR (Value-at-Risk)
            var_file = multi_asset_dir / f"efficient_frontier_var_{args.method}.png"
            plot_var_frontier(portfolio_stats, var_file, tickers=tickers,
                             title=f"VaR Efficient Frontier - {args.method.upper()}")

            # 6. Max Drawdown (Calmar)
            drawdown_file = multi_asset_dir / f"efficient_frontier_drawdown_{args.method}.png"
            plot_max_drawdown_frontier(portfolio_stats, drawdown_file, tickers=tickers,
                                       title=f"Max Drawdown Frontier (Calmar) - {args.method.upper()}")

            print(f"\nAll 6 frontier visualizations saved to: {multi_asset_dir}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

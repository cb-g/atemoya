#!/usr/bin/env python3
"""
Visualize pairs trading analysis.
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

setup_dark_mode()

def linear_regression(x, y):
    """Simple OLS regression."""
    x_mean = x.mean()
    y_mean = y.mean()

    beta = ((x - x_mean) * (y - y_mean)).sum() / ((x - x_mean) ** 2).sum()
    alpha = y_mean - beta * x_mean

    return alpha, beta

def tls_regression(x, y):
    """Total Least Squares regression (orthogonal/symmetric)."""
    x_mean = x.mean()
    y_mean = y.mean()
    xc = x - x_mean
    yc = y - y_mean

    sxx = (xc * xc).sum()
    sxy = (xc * yc).sum()
    syy = (yc * yc).sum()

    tr = sxx + syy
    det = sxx * syy - sxy * sxy
    disc = max(0, tr * tr - 4 * det)
    lambda_min = (tr - np.sqrt(disc)) / 2

    denom = sxx - lambda_min
    if abs(denom) > 1e-12:
        beta = sxy / denom
    else:
        beta = 1.0

    alpha = y_mean - beta * x_mean
    return alpha, beta

def johansen_trace_test(prices1, prices2):
    """Johansen trace test for 2 variables (VECM with lag=1)."""
    z = np.column_stack([prices1, prices2])
    dz = np.diff(z, axis=0)
    z_lag = z[:-1]

    T = len(dz)

    # Demean (regress on constant)
    dz_dm = dz - dz.mean(axis=0)
    z_dm = z_lag - z_lag.mean(axis=0)

    # Moment matrices
    S00 = dz_dm.T @ dz_dm / T
    S11 = z_dm.T @ z_dm / T
    S01 = dz_dm.T @ z_dm / T
    S10 = S01.T

    try:
        S00_inv = np.linalg.inv(S00)
        S11_inv = np.linalg.inv(S11)
    except np.linalg.LinAlgError:
        return 0.0, 15.41, False, 1.0

    # M = S11^{-1} S10 S00^{-1} S01
    M = S11_inv @ S10 @ S00_inv @ S01

    eigenvalues, eigenvectors = np.linalg.eig(M)
    eigenvalues = np.clip(eigenvalues.real, 0, 0.999)

    # Sort descending
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    # Trace statistic for r=0
    trace_stat = -T * np.sum(np.log(1 - eigenvalues))
    critical_value = 15.41  # 5% for 2 variables, r=0

    is_cointegrated = trace_stat > critical_value

    # Cointegrating vector from largest eigenvalue's eigenvector
    v = eigenvectors[:, 0].real
    hedge_ratio = -v[1] / v[0] if abs(v[0]) > 1e-12 else 1.0

    return trace_stat, critical_value, is_cointegrated, hedge_ratio

def adf_test_simple(series):
    """Simple ADF test (no lags) for cointegration residuals."""
    n = len(series)
    if n < 10:
        return 0.0, -2.86

    delta = np.diff(series)
    lagged = series[:-1]

    # Demean
    lagged_dm = lagged - lagged.mean()
    delta_dm = delta - delta.mean()

    var_x = (lagged_dm ** 2).sum()
    if var_x < 1e-12:
        return 0.0, -2.86

    rho = (lagged_dm * delta_dm).sum() / var_x

    # Residuals and standard error
    residuals = delta_dm - rho * lagged_dm
    sigma2 = (residuals ** 2).sum() / (n - 3)
    se_rho = np.sqrt(sigma2 / var_x)

    t_stat = rho / se_rho if se_rho > 0 else 0.0

    # Approximate critical value
    if n < 50:
        cv = -2.93
    elif n < 100:
        cv = -2.89
    else:
        cv = -2.86

    return t_stat, cv

def compute_half_life(spread_series):
    """Compute half-life from AR(1) model."""
    n = len(spread_series)
    if n < 10:
        return None

    delta = np.diff(spread_series)
    lagged = spread_series[:-1]

    var_x = np.var(lagged)
    if var_x < 1e-12:
        return None

    phi = np.cov(lagged, delta)[0, 1] / np.var(lagged)

    if phi >= 0 or phi <= -1:
        return None

    rho = 1 + phi
    if abs(np.log(rho)) < 1e-10:
        return None

    hl = -np.log(2) / np.log(rho)
    return hl if 0.5 < hl < 252 else None

def rolling_half_life(spread_series, window=60):
    """Compute half-life over rolling windows."""
    n = len(spread_series)
    half_lives = np.full(n, np.nan)

    for i in range(window, n):
        hl = compute_half_life(spread_series[i - window:i])
        if hl is not None:
            half_lives[i] = hl

    return half_lives

def calculate_spread(prices1, prices2, hedge_ratio, alpha):
    """Calculate spread."""
    return prices2 - (hedge_ratio * prices1 + alpha)

def calculate_zscore(series):
    """Calculate rolling z-score."""
    return (series - series.mean()) / series.std()

def plot_pairs_analysis(ticker1_arg=None, ticker2_arg=None):
    """Create comprehensive pairs trading visualization."""

    # Load data
    data_dir = Path(__file__).resolve().parent.parent.parent / "data"

    if ticker1_arg and ticker2_arg:
        pair_tag = f"{ticker1_arg}_{ticker2_arg}"
        df = pd.read_csv(data_dir / f"pair_data_{pair_tag}.csv")
        metadata = pd.read_csv(data_dir / f"metadata_{pair_tag}.csv")
    else:
        df = pd.read_csv(data_dir / "pair_data.csv")
        metadata = pd.read_csv(data_dir / "metadata.csv")

    ticker1 = metadata['ticker1'].values[0]
    ticker2 = metadata['ticker2'].values[0]

    p1 = df['price_1'].values
    p2 = df['price_2'].values

    # === Compute all three methods ===
    ols_alpha, ols_beta = linear_regression(p1, p2)
    tls_alpha, tls_beta = tls_regression(p1, p2)

    # OLS Engle-Granger
    ols_resid = p2 - (ols_alpha + ols_beta * p1)
    ols_adf, ols_cv = adf_test_simple(ols_resid)
    ols_coint = ols_adf < ols_cv

    # TLS Engle-Granger
    tls_resid = p2 - (tls_alpha + tls_beta * p1)
    tls_adf, tls_cv = adf_test_simple(tls_resid)
    tls_coint = tls_adf < tls_cv

    # Johansen
    joh_trace, joh_cv, joh_coint, joh_beta = johansen_trace_test(p1, p2)

    # Spread (OLS-based for signals)
    spread = calculate_spread(df['price_1'], df['price_2'], ols_beta, ols_alpha)
    zscore = calculate_zscore(spread)

    # Rolling half-life
    window = 60
    baseline_hl = compute_half_life(spread.values)
    rolling_hl = rolling_half_life(spread.values, window=window)

    # Current rolling half-life
    valid_hl = rolling_hl[~np.isnan(rolling_hl)]
    current_hl = valid_hl[-1] if len(valid_hl) > 0 else None
    hl_ratio = current_hl / baseline_hl if (current_hl and baseline_hl) else None

    # === Create figure: 6 rows ===
    fig = plt.figure(figsize=(16, 18))
    fig.patch.set_facecolor(COLORS['bg'])

    gs = fig.add_gridspec(6, 2, hspace=0.45, wspace=0.3,
                          height_ratios=[1.2, 1, 1.2, 1, 0.8, 0.8])

    # 1. Price comparison (full width)
    ax1 = fig.add_subplot(gs[0, :])
    ax1.set_facecolor(COLORS['bg'])

    norm1 = (df['price_1'] / df['price_1'].iloc[0]) * 100
    norm2 = (df['price_2'] / df['price_2'].iloc[0]) * 100

    ax1.plot(norm1.values, color=COLORS['blue'], linewidth=2, label=ticker1, alpha=0.9)
    ax1.plot(norm2.values, color=COLORS['red'], linewidth=2, label=ticker2, alpha=0.9)

    ax1.set_xlabel('Days', color=COLORS['fg'])
    ax1.set_ylabel('Normalized Price (Base=100)', color=COLORS['fg'])
    ax1.set_title(f'Price Comparison: {ticker1} vs {ticker2}',
                  fontweight='bold', fontsize=14, color=COLORS['fg'])
    ax1.legend(facecolor=COLORS['bg'], edgecolor=COLORS['gray'])
    ax1.grid(True, alpha=0.2, color=COLORS['gray'])
    ax1.tick_params(colors=COLORS['fg'])

    # 2. Scatter plot with all regression lines (left)
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.set_facecolor(COLORS['bg'])

    ax2.scatter(p1, p2, color=COLORS['blue'], alpha=0.5, s=20, label='Data')

    x_line = np.array([p1.min(), p1.max()])
    ax2.plot(x_line, ols_alpha + ols_beta * x_line, color=COLORS['red'],
             linewidth=2, label=f'OLS: \u03b2={ols_beta:.4f}')
    ax2.plot(x_line, tls_alpha + tls_beta * x_line, color=COLORS['green'],
             linewidth=2, linestyle='--', label=f'TLS: \u03b2={tls_beta:.4f}')

    ax2.set_xlabel(f'{ticker1} Price', color=COLORS['fg'])
    ax2.set_ylabel(f'{ticker2} Price', color=COLORS['fg'])
    ax2.set_title('Regression Comparison (OLS vs TLS)', fontweight='bold', color=COLORS['fg'])
    ax2.legend(facecolor=COLORS['bg'], edgecolor=COLORS['gray'], fontsize=9)
    ax2.grid(True, alpha=0.2, color=COLORS['gray'])
    ax2.tick_params(colors=COLORS['fg'])

    # 3. Spread (right)
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.set_facecolor(COLORS['bg'])

    ax3.plot(spread.values, color=COLORS['cyan'], linewidth=1.5, alpha=0.8)
    ax3.axhline(y=spread.mean(), color=COLORS['yellow'],
                linestyle='--', linewidth=2, label='Mean')
    ax3.axhline(y=spread.mean() + spread.std(), color=COLORS['gray'],
                linestyle=':', linewidth=1, alpha=0.7, label='\u00b11\u03c3')
    ax3.axhline(y=spread.mean() - spread.std(), color=COLORS['gray'],
                linestyle=':', linewidth=1, alpha=0.7)

    ax3.set_xlabel('Days', color=COLORS['fg'])
    ax3.set_ylabel('Spread', color=COLORS['fg'])
    ax3.set_title('Spread Time Series', fontweight='bold', color=COLORS['fg'])
    ax3.legend(facecolor=COLORS['bg'], edgecolor=COLORS['gray'])
    ax3.grid(True, alpha=0.2, color=COLORS['gray'])
    ax3.tick_params(colors=COLORS['fg'])

    # 4. Z-Score (full width)
    ax4 = fig.add_subplot(gs[2, :])
    ax4.set_facecolor(COLORS['bg'])

    ax4.plot(zscore.values, color=COLORS['purple'], linewidth=2, alpha=0.9)
    ax4.axhline(y=0, color=COLORS['fg'], linestyle='-', linewidth=1, alpha=0.5)
    ax4.axhline(y=2.0, color=COLORS['red'], linestyle='--', linewidth=2,
                alpha=0.7, label='Entry thresholds (\u00b12\u03c3)')
    ax4.axhline(y=-2.0, color=COLORS['red'], linestyle='--', linewidth=2, alpha=0.7)
    ax4.axhline(y=0.5, color=COLORS['green'], linestyle=':', linewidth=1.5,
                alpha=0.7, label='Exit thresholds (\u00b10.5\u03c3)')
    ax4.axhline(y=-0.5, color=COLORS['green'], linestyle=':', linewidth=1.5, alpha=0.7)

    ax4.fill_between(range(len(zscore)), 2.0, 4.0, color=COLORS['red'], alpha=0.1)
    ax4.fill_between(range(len(zscore)), -2.0, -4.0, color=COLORS['red'], alpha=0.1)

    ax4.set_xlabel('Days', color=COLORS['fg'])
    ax4.set_ylabel('Z-Score', color=COLORS['fg'])
    ax4.set_title('Spread Z-Score with Trading Thresholds',
                  fontweight='bold', fontsize=14, color=COLORS['fg'])
    ax4.legend(facecolor=COLORS['bg'], edgecolor=COLORS['gray'])
    ax4.grid(True, alpha=0.2, color=COLORS['gray'])
    ax4.tick_params(colors=COLORS['fg'])
    ax4.set_ylim(-4, 4)

    # 5. Rolling Half-Life Monitor (full width)
    ax5 = fig.add_subplot(gs[3, :])
    ax5.set_facecolor(COLORS['bg'])

    valid_idx = ~np.isnan(rolling_hl)
    if valid_idx.any():
        ax5.plot(np.where(valid_idx)[0], rolling_hl[valid_idx],
                 color=COLORS['cyan'], linewidth=2, alpha=0.9, label='Rolling half-life')

        if baseline_hl is not None:
            ax5.axhline(y=baseline_hl, color=COLORS['yellow'],
                        linestyle='--', linewidth=2, label=f'Baseline: {baseline_hl:.1f}d')
            ax5.axhline(y=baseline_hl * 2, color=COLORS['red'],
                        linestyle=':', linewidth=2, alpha=0.7,
                        label=f'Warning (2x): {baseline_hl * 2:.1f}d')

            # Shade danger zone
            ax5.fill_between(range(len(rolling_hl)), baseline_hl * 2,
                            ax5.get_ylim()[1] if ax5.get_ylim()[1] > baseline_hl * 2 else baseline_hl * 3,
                            color=COLORS['red'], alpha=0.08)

    ax5.set_xlabel('Days', color=COLORS['fg'])
    ax5.set_ylabel('Half-Life (days)', color=COLORS['fg'])
    ax5.set_title('Dynamic Half-Life Monitor',
                  fontweight='bold', fontsize=14, color=COLORS['fg'])
    ax5.legend(facecolor=COLORS['bg'], edgecolor=COLORS['gray'])
    ax5.grid(True, alpha=0.2, color=COLORS['gray'])
    ax5.tick_params(colors=COLORS['fg'])

    # Set y-axis based on actual data
    if valid_idx.any():
        max_hl = np.nanmax(rolling_hl[valid_idx])
        ax5.set_ylim(0, max_hl * 1.15)

    # 6. Method Comparison Table (left)
    ax6 = fig.add_subplot(gs[4:, 0])
    ax6.set_facecolor(COLORS['bg'])
    ax6.axis('off')

    # Build method comparison text
    def coint_str(b):
        return "YES" if b else "NO"
    def coint_color(b):
        return COLORS['green'] if b else COLORS['red']

    header = f"{'Method':<22} {'Hedge':>7} {'Stat':>8} {'CV':>7} {'Coint?':>6}"
    sep = "\u2500" * 56
    ols_line  = f"{'Engle-Granger (OLS)':<22} {ols_beta:>7.4f} {ols_adf:>8.2f} {ols_cv:>7.2f} {coint_str(ols_coint):>6}"
    tls_line  = f"{'Engle-Granger (TLS)':<22} {tls_beta:>7.4f} {tls_adf:>8.2f} {tls_cv:>7.2f} {coint_str(tls_coint):>6}"
    joh_line  = f"{'Johansen (Trace)':<22} {joh_beta:>7.4f} {joh_trace:>8.2f} {joh_cv:>7.2f} {coint_str(joh_coint):>6}"

    lines = [
        "Cointegration Test Comparison",
        "",
        header,
        sep,
        ols_line,
        tls_line,
        joh_line,
        "",
    ]

    # Half-life monitor summary
    if baseline_hl is not None:
        lines.append(f"Half-Life Monitor")
        lines.append(f"  Baseline:  {baseline_hl:>6.1f} days")
        if current_hl is not None:
            lines.append(f"  Current:   {current_hl:>6.1f} days  (ratio: {hl_ratio:.2f})")
            if hl_ratio > 2.0:
                lines.append(f"  Status:    WARNING - mean reversion weakening")
            else:
                lines.append(f"  Status:    Stable")
        else:
            lines.append(f"  Current:   N/A")

    ax6.text(0.05, 0.95, '\n'.join(lines),
             transform=ax6.transAxes,
             fontsize=10,
             verticalalignment='top',
             fontfamily='monospace',
             color=COLORS['fg'])

    # 7. Trading signal + stats (right)
    ax7 = fig.add_subplot(gs[4:, 1])
    ax7.set_facecolor(COLORS['bg'])
    ax7.axis('off')

    current_z = zscore.iloc[-1]

    if current_z > 2.0:
        signal = "SHORT SPREAD"
        action = f"Sell {ticker2}, Buy {ticker1}"
        signal_color = COLORS['red']
    elif current_z < -2.0:
        signal = "LONG SPREAD"
        action = f"Buy {ticker2}, Sell {ticker1}"
        signal_color = COLORS['green']
    else:
        signal = "NEUTRAL"
        action = "No trade"
        signal_color = COLORS['gray']

    ax7.text(0.5, 0.85, signal,
             ha='center', va='center',
             transform=ax7.transAxes,
             fontsize=22, fontweight='bold',
             color=signal_color)

    ax7.text(0.5, 0.7, action,
             ha='center', va='center',
             transform=ax7.transAxes,
             fontsize=12,
             color=COLORS['fg'])

    ax7.text(0.5, 0.55, f"Z-Score: {current_z:.2f}",
             ha='center', va='center',
             transform=ax7.transAxes,
             fontsize=12,
             color=COLORS['fg'])

    # Agreement indicator
    agree_count = sum([ols_coint, tls_coint, joh_coint])
    if agree_count == 3:
        agree_text = "All 3 methods: COINTEGRATED"
        agree_color = COLORS['green']
    elif agree_count == 0:
        agree_text = "All 3 methods: NOT cointegrated"
        agree_color = COLORS['red']
    else:
        agree_text = f"{agree_count}/3 methods: cointegrated"
        agree_color = COLORS['yellow']

    ax7.text(0.5, 0.35, agree_text,
             ha='center', va='center',
             transform=ax7.transAxes,
             fontsize=11, fontweight='bold',
             color=agree_color)

    # Stats
    stats = [
        f"Observations: {len(df)}",
        f"Correlation: {np.corrcoef(p1, p2)[0,1]:.2%}",
        f"Spread Std: {spread.std():.4f}",
    ]
    if baseline_hl:
        stats.append(f"Half-Life: {baseline_hl:.1f} days")

    ax7.text(0.5, 0.12, '\n'.join(stats),
             ha='center', va='center',
             transform=ax7.transAxes,
             fontsize=10,
             fontfamily='monospace',
             color=COLORS['fg'])

    plt.suptitle('Pairs Trading Analysis',
                 fontsize=18, fontweight='bold',
                 color=COLORS['fg'], y=0.995)

    # Save
    output_dir = Path(__file__).resolve().parent.parent.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{ticker1}_{ticker2}_pairs_analysis.png"

    save_figure(fig, output_file, dpi=300)
    print(f"✓ Saved: {output_file}")

    plt.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Visualize pairs trading analysis')
    parser.add_argument('--ticker1', type=str, help='First ticker symbol')
    parser.add_argument('--ticker2', type=str, help='Second ticker symbol')
    args = parser.parse_args()

    try:
        plot_pairs_analysis(args.ticker1, args.ticker2)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

#!/usr/bin/env python3
"""
Plot volatility surfaces (both SVI and SABR)
Each model gets: 3D surface (top) + smile curves with market data (bottom)
"""

import argparse
import sys
import json
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure


def get_kanagawa_cmap():
    """Create a Kanagawa-themed colormap."""
    colors_list = [COLORS['blue'], COLORS['cyan'], COLORS['green'], COLORS['yellow'], COLORS['orange']]
    return LinearSegmentedColormap.from_list('kanagawa', colors_list)

setup_dark_mode()


def sabr_implied_vol_hagan(F, K, T, alpha, beta, rho, nu):
    """SABR implied vol using Hagan et al. (2002) approximation."""
    if T <= 0:
        return np.nan

    # ATM case
    if abs(F - K) < 1e-6:
        fk_mid = F ** (1 - beta)
        return alpha / fk_mid * (
            1 + T * (
                (1 - beta)**2 * alpha**2 / (24 * fk_mid**2)
                + 0.25 * rho * beta * nu * alpha / fk_mid
                + (2 - 3 * rho**2) * nu**2 / 24
            )
        )

    # General case
    fk_mid = (F * K) ** ((1 - beta) / 2)
    log_fk = np.log(F / K)
    z = (nu / alpha) * fk_mid * log_fk

    if abs(z) < 1e-6:
        chi_z = 1.0
    else:
        sqrt_term = np.sqrt(1 - 2 * rho * z + z**2)
        chi_z = z / np.log((sqrt_term + z - rho) / (1 - rho))

    factor1 = alpha / fk_mid
    correction = 1 + (1 - beta)**2 * log_fk**2 / 24 + (1 - beta)**4 * log_fk**4 / 1920
    factor2 = chi_z / correction

    fk_avg = (F + K) / 2
    fk_avg_factor = fk_avg ** (1 - beta)
    time_correction = 1 + T * (
        (1 - beta)**2 * alpha**2 / (24 * fk_avg_factor**2)
        + 0.25 * rho * beta * nu * alpha / fk_avg_factor
        + (2 - 3 * rho**2) * nu**2 / 24
    )

    return factor1 * factor2 * time_correction


def svi_total_variance(k, params):
    """SVI formula"""
    a, b, rho, m, sigma = params
    delta_k = k - m
    return a + b * (rho * delta_k + np.sqrt(delta_k**2 + sigma**2))


def _prepare_market_data(df_options, spot):
    """Filter and prepare market data for smile overlay."""
    if df_options.empty:
        return pd.DataFrame()
    df_mkt = df_options[
        (df_options['implied_volatility'] > 0.05) &
        (df_options['implied_volatility'] < 1.5) &
        (df_options['strike'] > 0.7 * spot) &
        (df_options['strike'] < 1.3 * spot)
    ].copy()
    df_mkt['log_m'] = np.log(df_mkt['strike'] / spot)
    return df_mkt


def _plot_3d_surface(fig, subplot_pos, moneyness, expiries, IV_pct, title, smile_colors, indices):
    """Plot 3D wireframe+surface panel."""
    ax3d = fig.add_subplot(*subplot_pos, projection='3d')
    ax3d.set_facecolor(COLORS['bg'])

    M_grid, T_grid = np.meshgrid(moneyness * 100, expiries)
    cmap = get_kanagawa_cmap()
    iv_valid = IV_pct[np.isfinite(IV_pct) & (IV_pct > 0)]
    vmin, vmax = np.percentile(iv_valid, 2), np.percentile(iv_valid, 98)

    surf = ax3d.plot_surface(M_grid, T_grid, IV_pct,
                              cmap=cmap, alpha=0.85, edgecolor='none',
                              rstride=1, cstride=2, vmin=vmin, vmax=vmax)

    ax3d.plot_wireframe(M_grid, T_grid, IV_pct,
                         color=COLORS['gray'], alpha=0.15, linewidth=0.3,
                         rstride=2, cstride=4)

    # Highlight smile expiries
    for ci, idx in enumerate(indices):
        ax3d.plot(moneyness * 100, [expiries[idx]] * len(moneyness), IV_pct[idx, :],
                  color=smile_colors[ci], linewidth=2, zorder=10)

    ax3d.set_xlabel('Log-Moneyness (%)', fontsize=10, labelpad=8)
    ax3d.set_ylabel('Expiry (years)', fontsize=10, labelpad=8)
    ax3d.set_zlabel('Implied Vol (%)', fontsize=10, labelpad=8)
    ax3d.set_title(title, fontsize=14, fontweight='bold')
    ax3d.view_init(elev=25, azim=-50)

    for pane in [ax3d.xaxis.pane, ax3d.yaxis.pane, ax3d.zaxis.pane]:
        pane.fill = False
        pane.set_edgecolor(COLORS['gray'])
        pane.set_alpha(0.1)
    ax3d.tick_params(labelsize=8)

    cb = fig.colorbar(surf, ax=ax3d, shrink=0.5, pad=0.08)
    cb.set_label('Implied Vol (%)', fontsize=10)

    return ax3d


def _plot_smile_panel(ax, moneyness, IV_pct, expiries, indices, params_list,
                       smile_colors, market_markers, df_mkt, title, model_type):
    """Plot 2D smile curves with market data overlay."""
    ax.set_facecolor(COLORS['bg'])

    for ci, idx in enumerate(indices):
        color = smile_colors[ci % len(smile_colors)]
        exp = expiries[idx]
        p = params_list[idx]

        # Build label with model params
        if model_type == 'SABR':
            label = f'T={exp:.2f}y (α={p["alpha"]:.2f}, ρ={p["rho"]:.2f}, ν={p["nu"]:.2f})'
        else:
            label = f'T={exp:.2f}y (a={p["a"]:.3f}, b={p["b"]:.3f}, ρ={p["rho"]:.2f})'

        # Fitted curve (solid)
        ax.plot(moneyness * 100, IV_pct[idx, :], color=color,
                linewidth=2, label=label)

        # Market points: dotted line with hollow markers
        if not df_mkt.empty:
            unique_exp = df_mkt['expiry'].unique()
            closest = unique_exp[np.argmin(np.abs(unique_exp - exp))]
            nearby = df_mkt[df_mkt['expiry'] == closest].sort_values('log_m')
            if not nearby.empty:
                ax.plot(nearby['log_m'] * 100, nearby['implied_volatility'] * 100,
                        color=color, linestyle=':', linewidth=0.8, alpha=0.5,
                        marker=market_markers[ci % len(market_markers)],
                        markersize=5, markerfacecolor='none', markeredgecolor=color,
                        markeredgewidth=1.2, label=f'Market T={exp:.2f}y', zorder=5)

    ax.axvline(x=0, color=COLORS['yellow'], linestyle='--', linewidth=1.2, alpha=0.7, label='ATM')
    ax.set_xlabel('Log-Moneyness (%)', fontsize=11)
    ax.set_ylabel('Implied Vol (%)', fontsize=11)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.15)


def plot_vol_surface_svi(surface_data, df_options, spot, output_file, ticker=''):
    """Plot SVI volatility surface: 3D surface + smile panel."""
    params_list = surface_data['params']

    moneyness = np.linspace(-0.3, 0.3, 60)
    expiries = np.array([p['expiry'] for p in params_list])

    IV = np.zeros((len(expiries), len(moneyness)))
    for i, p in enumerate(params_list):
        pv = (p['a'], p['b'], p['rho'], p['m'], p['sigma'])
        for j, k in enumerate(moneyness):
            w = svi_total_variance(k, pv)
            IV[i, j] = np.sqrt(max(0, w / expiries[i]))

    IV_pct = IV * 100

    n = len(expiries)
    indices = np.array([0, n - 1])
    smile_colors = [COLORS['cyan'], COLORS['red']]
    market_markers = ['o', 'D']

    df_mkt = _prepare_market_data(df_options, spot)

    fig = plt.figure(figsize=(14, 14))
    fig.patch.set_facecolor(COLORS['bg'])

    _plot_3d_surface(fig, (2, 1, 1), moneyness, expiries, IV_pct,
                      f'{ticker + " — " if ticker else ""}SVI Implied Volatility Surface', smile_colors, indices)

    ax_smile = fig.add_subplot(2, 1, 2)
    _plot_smile_panel(ax_smile, moneyness, IV_pct, expiries, indices, params_list,
                       smile_colors, market_markers, df_mkt,
                       'SVI Volatility Smile by Expiry', 'SVI')

    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    print(f"Saved SVI volatility surface to {output_file}")


def plot_vol_surface_sabr(surface_data, df_options, spot, output_file, ticker=''):
    """Plot SABR volatility surface: 3D surface + smile panel."""
    params_list = surface_data['params']

    moneyness = np.linspace(-0.3, 0.3, 60)
    expiries = np.array([p['expiry'] for p in params_list])

    IV = np.zeros((len(expiries), len(moneyness)))
    for i, p in enumerate(params_list):
        for j, k in enumerate(moneyness):
            K = spot * np.exp(k)
            iv = sabr_implied_vol_hagan(spot, K, expiries[i],
                                        p['alpha'], p['beta'], p['rho'], p['nu'])
            IV[i, j] = iv if np.isfinite(iv) and iv > 0 else np.nan

    IV_pct = IV * 100

    n = len(expiries)
    indices = np.array([0, n - 1])
    smile_colors = [COLORS['cyan'], COLORS['red']]
    market_markers = ['o', 'D']

    df_mkt = _prepare_market_data(df_options, spot)

    fig = plt.figure(figsize=(14, 14))
    fig.patch.set_facecolor(COLORS['bg'])

    _plot_3d_surface(fig, (2, 1, 1), moneyness, expiries, IV_pct,
                      f'{ticker + " — " if ticker else ""}SABR Implied Volatility Surface', smile_colors, indices)

    ax_smile = fig.add_subplot(2, 1, 2)
    _plot_smile_panel(ax_smile, moneyness, IV_pct, expiries, indices, params_list,
                       smile_colors, market_markers, df_mkt,
                       'SABR Volatility Smile by Expiry', 'SABR')

    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    print(f"Saved SABR volatility surface to {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Plot volatility surface')
    parser.add_argument('--ticker', required=True)
    parser.add_argument('--data-dir', default='pricing/options_hedging/data')
    parser.add_argument('--output-dir', default='pricing/options_hedging/output/plots')

    args = parser.parse_args()

    try:
        data_dir = Path(args.data_dir)
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load underlying
        underlying_file = data_dir / f"{args.ticker}_underlying.csv"
        df_underlying = pd.read_csv(underlying_file)
        spot = df_underlying['spot_price'].iloc[0]

        # Load option data
        options_file = data_dir / f"{args.ticker}_options.csv"
        df_options = pd.read_csv(options_file) if options_file.exists() else pd.DataFrame()

        # Plot both SVI and SABR surfaces
        svi_file = data_dir / f"{args.ticker}_vol_surface_svi.json"
        sabr_file = data_dir / f"{args.ticker}_vol_surface_sabr.json"

        # Also check legacy single-file format
        legacy_file = data_dir / f"{args.ticker}_vol_surface.json"

        ticker = args.ticker

        if svi_file.exists():
            with open(svi_file) as f:
                svi_data = json.load(f)
            plot_vol_surface_svi(svi_data, df_options, spot,
                                  output_dir / 'vol_surface_svi.png', ticker=ticker)
        elif legacy_file.exists():
            with open(legacy_file) as f:
                data = json.load(f)
            if data['type'] == 'SVI':
                plot_vol_surface_svi(data, df_options, spot,
                                      output_dir / 'vol_surface_svi.png', ticker=ticker)

        if sabr_file.exists():
            with open(sabr_file) as f:
                sabr_data = json.load(f)
            plot_vol_surface_sabr(sabr_data, df_options, spot,
                                   output_dir / 'vol_surface_sabr.png', ticker=ticker)
        elif legacy_file.exists():
            with open(legacy_file) as f:
                data = json.load(f)
            if data['type'] == 'SABR':
                plot_vol_surface_sabr(data, df_options, spot,
                                       output_dir / 'vol_surface_sabr.png', ticker=ticker)

        print("\n✓ Successfully generated volatility surface plots")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

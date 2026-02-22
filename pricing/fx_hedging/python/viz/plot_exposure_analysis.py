#!/usr/bin/env python3
"""
Visualize portfolio FX exposure and generate actionable hedge recommendations.

Shows both futures hedge and options (put protection) alternatives.

Usage:
    python plot_exposure_analysis.py
    python plot_exposure_analysis.py --output exposure.png --home-currency CHF
"""

import argparse
import sys
from pathlib import Path
import math
import pandas as pd
import numpy as np
from scipy.stats import norm
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

# Apply dark theme
setup_dark_mode()

# CME contract specs: currency -> (code, contract_size_in_foreign_ccy, initial_margin)
# Standard contracts listed first; micro variants used as fallback for small exposures
CME_CONTRACTS = {
    # FX futures (standard)
    'EUR': {'code': '6E', 'size': 125_000, 'margin': 2_500},
    'GBP': {'code': '6B', 'size': 62_500, 'margin': 2_500},
    'JPY': {'code': '6J', 'size': 12_500_000, 'margin': 2_000},
    'CHF': {'code': '6S', 'size': 125_000, 'margin': 2_000},
    'AUD': {'code': '6A', 'size': 100_000, 'margin': 1_800},
    'CAD': {'code': '6C', 'size': 100_000, 'margin': 1_800},
    # Crypto futures (standard)
    'BTC': {'code': 'BTC', 'size': 5, 'margin': 80_000},
    'ETH': {'code': 'ETH', 'size': 50, 'margin': 7_000},
    'SOL': {'code': 'SOL', 'size': 500, 'margin': 5_000},
}

# Micro contracts — used when standard is too large for the exposure
CME_MICRO_CONTRACTS = {
    'EUR': {'code': 'M6E', 'size': 12_500, 'margin': 250},
    'GBP': {'code': 'M6B', 'size': 6_250, 'margin': 250},
    'JPY': {'code': 'M6J', 'size': 1_250_000, 'margin': 200},
    'CHF': {'code': 'M6S', 'size': 12_500, 'margin': 200},
    'AUD': {'code': 'M6A', 'size': 10_000, 'margin': 180},
    'CAD': {'code': 'M6C', 'size': 10_000, 'margin': 180},
    'BTC': {'code': 'MBT', 'size': 0.1, 'margin': 1_200},
    'ETH': {'code': 'MET', 'size': 0.1, 'margin': 56},
    'SOL': {'code': 'MSOL', 'size': 5, 'margin': 45},
}


def load_exposure_data() -> pd.DataFrame:
    """Load exposure analysis from CSV."""
    exposure_file = Path(__file__).resolve().parent.parent.parent / "output" / "exposure_analysis.csv"
    if not exposure_file.exists():
        raise FileNotFoundError(
            f"Exposure file not found: {exposure_file}\n"
            f"Run: dune exec --root pricing/fx_hedging/ocaml fx_hedging -- -operation exposure"
        )
    df = pd.read_csv(exposure_file)
    print(f"Loaded exposure data for {len(df)} currencies from {exposure_file}")
    return df


def load_portfolio_breakdown() -> dict[str, list[dict]]:
    """Load portfolio CSV and return per-currency ticker breakdowns.

    Returns dict: currency -> [{ticker, value_usd}, ...] sorted by value descending.
    Small holdings (bottom 10% of total currency exposure) are bucketed into "Others".
    """
    portfolio_file = Path(__file__).resolve().parent.parent.parent / "data" / "portfolio.csv"
    if not portfolio_file.exists():
        return {}
    df = pd.read_csv(portfolio_file)
    if 'ticker' not in df.columns or 'currency' not in df.columns:
        return {}
    breakdown = {}
    for _, row in df.iterrows():
        ccy = row['currency']
        val = row['quantity'] * row['price_usd']
        if ccy not in breakdown:
            breakdown[ccy] = []
        breakdown[ccy].append({'ticker': row['ticker'], 'value_usd': val})
    # Sort descending, then bucket small tails into "Others"
    for ccy in breakdown:
        breakdown[ccy].sort(key=lambda x: x['value_usd'], reverse=True)
        total = sum(t['value_usd'] for t in breakdown[ccy])
        if total > 0 and len(breakdown[ccy]) > 2:
            threshold = total * 0.10
            main = []
            others_val = 0
            for t in breakdown[ccy]:
                if t['value_usd'] < threshold and main:
                    others_val += t['value_usd']
                else:
                    main.append(t)
            if others_val > 0:
                main.append({'ticker': 'Others', 'value_usd': others_val})
            breakdown[ccy] = main
    return breakdown


def _find_spot_file(data_dir: Path, currency: str) -> Path | None:
    """Find spot CSV for a currency, checking standard then micro contract codes."""
    for contracts in (CME_CONTRACTS, CME_MICRO_CONTRACTS):
        if currency in contracts:
            f = data_dir / f"{contracts[currency]['code'].lower()}_spot.csv"
            if f.exists():
                return f
    return None


def load_spot_rates() -> dict:
    """Load latest spot rates from fetched CSV files."""
    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    rates = {}
    for currency in CME_CONTRACTS:
        spot_file = _find_spot_file(data_dir, currency)
        if spot_file is not None:
            try:
                df = pd.read_csv(spot_file)
                if len(df) > 0:
                    rates[currency] = df['rate'].iloc[-1]
            except Exception:
                pass
    return rates


def load_historical_vols() -> dict:
    """Compute annualized volatility from historical spot data."""
    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    vols = {}
    for currency in CME_CONTRACTS:
        spot_file = _find_spot_file(data_dir, currency)
        if spot_file is not None:
            try:
                df = pd.read_csv(spot_file)
                if len(df) > 20:
                    returns = np.log(df['rate'] / df['rate'].shift(1)).dropna()
                    vols[currency] = returns.std() * np.sqrt(252)
            except Exception:
                pass
    return vols


def black76_put(F: float, K: float, T: float, sigma: float, r: float = 0.05) -> float:
    """Black-76 put option price on a futures contract.

    Args:
        F: Forward/futures price
        K: Strike price
        T: Time to expiry in years
        sigma: Implied volatility (annualized)
        r: Risk-free rate
    Returns:
        Put premium per unit of underlying
    """
    if T <= 0 or sigma <= 0 or F <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(F / K) + 0.5 * sigma**2 * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return np.exp(-r * T) * (K * norm.cdf(-d2) - F * norm.cdf(-d1))


def resolve_contract(ccy: str, home_currency: str) -> str | None:
    """Map exposure currency to the CME contract used to hedge it."""
    if ccy in CME_CONTRACTS:
        return ccy
    if ccy == 'USD' and home_currency in CME_CONTRACTS:
        return home_currency
    return None


def compute_hedge_plan(df: pd.DataFrame, spot_rates: dict,
                       vols: dict, home_currency: str = 'USD') -> list[dict]:
    """Compute hedge plan with both futures and options alternatives."""
    plan = []
    for _, row in df.iterrows():
        ccy = row['currency']
        exposure = row['net_exposure_usd']
        entry = {
            'currency': ccy,
            'exposure': exposure,
            'pct': row['pct_of_portfolio'],
        }

        contract_ccy = resolve_contract(ccy, home_currency)
        if contract_ccy is None or contract_ccy not in spot_rates:
            entry.update(code=CME_CONTRACTS.get(ccy, {}).get('code', '-'),
                         spot=spot_rates.get(ccy, 0),
                         contracts_exact=0, contracts=0,
                         hedged_usd=0, residual=abs(exposure),
                         margin=0, action='No data' if contract_ccy else 'No CME contract',
                         put_premium=0, put_cost=0, put_strike=0)
            plan.append(entry)
            continue

        spot = spot_rates[contract_ccy]
        abs_exp = abs(exposure)

        # --- Standard contracts first, then fill remainder with micros ---
        std_spec = CME_CONTRACTS[contract_ccy]
        std_notional = std_spec['size'] * spot
        n_std = int(abs_exp / std_notional)  # floor: never over-hedge with standards
        std_hedged = n_std * std_notional
        remainder = abs_exp - std_hedged

        n_micro = 0
        micro_spec = CME_MICRO_CONTRACTS.get(contract_ccy)
        micro_hedged = 0
        if micro_spec and remainder > 0:
            micro_notional = micro_spec['size'] * spot
            micro_exact = remainder / micro_notional
            if micro_spec['size'] < 1:
                # Crypto: 99% target to conserve margin on volatile assets
                n_micro = int(micro_exact * 0.99)
            else:
                # FX: pick floor or ceil — whichever gives closest hedge to exposure
                n_floor = int(micro_exact)
                n_ceil = math.ceil(micro_exact)
                dist_floor = abs(std_hedged + n_floor * micro_notional - abs_exp)
                dist_ceil = abs(std_hedged + n_ceil * micro_notional - abs_exp)
                n_micro = n_ceil if dist_ceil <= dist_floor else n_floor
            micro_hedged = n_micro * micro_notional

        hedged = std_hedged + micro_hedged
        margin = (n_std * std_spec['margin'] + n_micro * (micro_spec['margin'] if micro_spec else 0)) * 0.75
        residual = abs_exp - hedged

        # Build action string
        parts = []
        if n_std > 0:
            parts.append(f'{n_std} × {std_spec["code"]}')
        if n_micro > 0:
            parts.append(f'{n_micro} × {micro_spec["code"]}')
        action = 'Buy ' + ' + '.join(parts) if parts else f'Too small'

        # For contract lines on chart: use standard notional if any, else micro
        contract_notional = std_notional if n_std > 0 else (micro_spec['size'] * spot if micro_spec else 0)
        total_contracts = n_std + n_micro

        # Options pricing: 5% OTM put, 90 days, using historical vol
        # Mirror futures structure: N standard puts + M micro puts
        vol = vols.get(contract_ccy, 0.10)
        T = 90 / 365.0
        forward = spot * (1.005)
        strike = spot * 0.95
        put_per_unit = black76_put(forward, strike, T, vol)

        n_std_puts = n_std
        n_micro_puts = n_micro
        std_put_cost = n_std_puts * put_per_unit * std_spec['size']
        micro_put_cost = n_micro_puts * put_per_unit * micro_spec['size'] if micro_spec else 0
        put_total = std_put_cost + micro_put_cost
        opt_hedged = hedged  # options cover same notional as futures

        code_label = std_spec['code'] if n_std > 0 else (micro_spec['code'] if micro_spec else std_spec['code'])
        entry.update(code=code_label, spot=spot,
                     contracts_exact=abs_exp / std_notional, contracts=total_contracts,
                     n_std=n_std, n_micro=n_micro,
                     std_code=std_spec['code'],
                     micro_code=micro_spec['code'] if micro_spec else '',
                     contract_notional=contract_notional,
                     hedged_usd=hedged, residual=residual,
                     margin=margin, action=action,
                     n_std_puts=n_std_puts, n_micro_puts=n_micro_puts,
                     put_premium=put_per_unit, put_cost=put_total,
                     put_strike=strike,
                     opt_hedged=opt_hedged, vol=vol)
        plan.append(entry)

    return plan


def _hedge_color(coverage: float, base_color=None) -> tuple:
    """Return (blended_color, alpha, text_color) based on hedge coverage ratio.

    Uses actual darker/lighter colors by blending with background,
    rather than varying alpha transparency.
    """
    import matplotlib.colors as mcolors
    color = base_color or COLORS['green']
    rgb = mcolors.to_rgb(color)
    bg = mcolors.to_rgb(COLORS['bg'])
    if coverage > 1.03:
        # Over-hedged: full color intensity, dark text for contrast
        return rgb, 1.0, COLORS['bg']
    elif coverage >= 0.97:
        # Within threshold (97-103%): 60% color + 40% background
        blended = tuple(c * 0.6 + b * 0.4 for c, b in zip(rgb, bg))
        return blended, 1.0, COLORS['fg']
    else:
        # Under-hedged (<97%): 35% color + 65% background
        blended = tuple(c * 0.35 + b * 0.65 for c, b in zip(rgb, bg))
        return blended, 1.0, COLORS['fg']


def plot_coverage_chart(ax, plan: list[dict], portfolio_breakdown: dict = None,
                        home_currency: str = 'USD'):
    """Horizontal grouped bars: exposure, futures hedge, and options hedge per currency."""
    ax.set_facecolor(COLORS['bg'])

    currencies = [p['currency'] for p in plan]
    exposures = [abs(p['exposure']) for p in plan]
    hedged = [p['hedged_usd'] for p in plan]
    opt_hedged = [p.get('opt_hedged', 0) for p in plan]

    y = np.arange(len(currencies))
    bar_height = 0.25  # thinner bars to fit 3 per currency
    gap = 0.02

    exposure_color = COLORS['blue']

    # --- Exposure bars (top) ---
    exp_legend_added = False
    for i, p in enumerate(plan):
        bar_y = y[i] + bar_height + gap
        ccy = p['currency']
        tickers = portfolio_breakdown.get(ccy, []) if portfolio_breakdown else []
        if len(tickers) > 1:
            left = 0
            for j, t in enumerate(tickers):
                width = t['value_usd']
                ax.barh(bar_y, width, bar_height, left=left,
                        color=exposure_color, alpha=0.5, edgecolor=COLORS['fg'],
                        linewidth=0.5,
                        label='Exposure' if not exp_legend_added else None)
                exp_legend_added = True
                if width / exposures[i] > 0.06:
                    ax.text(left + width / 2, bar_y,
                            t['ticker'], ha='center', va='center',
                            fontsize=7, fontweight='bold', color=COLORS['fg'], alpha=0.9)
                left += width
        else:
            ax.barh(bar_y, exposures[i], bar_height,
                    color=exposure_color, alpha=0.5, edgecolor=COLORS['fg'],
                    linewidth=0.5,
                    label='Exposure' if not exp_legend_added else None)
            exp_legend_added = True

    # --- Futures hedge bars (middle) ---
    hdg_legend_added = False
    for i, p in enumerate(plan):
        bar_y = y[i]
        spot = p.get('spot', 0)
        n_std = p.get('n_std', 0)
        n_micro = p.get('n_micro', 0)
        contract_ccy = resolve_contract(p['currency'], home_currency)

        std_notional = CME_CONTRACTS.get(contract_ccy, {}).get('size', 0) * spot if contract_ccy else 0
        micro_notional = CME_MICRO_CONTRACTS.get(contract_ccy, {}).get('size', 0) * spot if contract_ccy else 0
        std_hedged = n_std * std_notional
        micro_hedged = n_micro * micro_notional
        total_hdg = std_hedged + micro_hedged
        coverage = (total_hdg / exposures[i]) if exposures[i] > 0 else 0
        h_color, h_alpha, h_text = _hedge_color(coverage)

        if n_std > 0 and n_micro > 0:
            ax.barh(bar_y, std_hedged, bar_height,
                    color=h_color, alpha=h_alpha, edgecolor=COLORS['fg'], linewidth=0.5,
                    label='Futures' if not hdg_legend_added else None)
            hdg_legend_added = True
            ax.barh(bar_y, micro_hedged, bar_height, left=std_hedged,
                    color=h_color, alpha=h_alpha, edgecolor=COLORS['fg'], linewidth=0.5)
            std_code = p.get('std_code', '')
            micro_code = p.get('micro_code', '')
            for seg_left, seg_width, seg_n, seg_code in [
                (0, std_hedged, n_std, std_code),
                (std_hedged, micro_hedged, n_micro, micro_code),
            ]:
                frac = seg_width / max(total_hdg, 1)
                if frac < 0.06 or seg_n == 0:
                    continue
                label = f'{seg_n}×{seg_code}' if frac > 0.25 else f'{seg_n}\n×\n{seg_code}'
                fs = 7 if frac > 0.25 else 6
                ax.text(seg_left + seg_width / 2, bar_y,
                        label, ha='center', va='center',
                        fontsize=fs, fontweight='bold', color=h_text,
                        linespacing=0.8)
        elif hedged[i] > 0:
            ax.barh(bar_y, hedged[i], bar_height,
                    color=h_color, alpha=h_alpha, edgecolor=COLORS['fg'], linewidth=0.5,
                    label='Futures' if not hdg_legend_added else None)
            hdg_legend_added = True
            micro_code = p.get('micro_code', '')
            if n_micro > 0 and micro_code:
                ax.text(hedged[i] / 2, bar_y,
                        f'{n_micro}×{micro_code}', ha='center', va='center',
                        fontsize=7, fontweight='bold', color=h_text)

    # --- Options hedge bars (bottom) ---
    opt_legend_added = False
    for i, p in enumerate(plan):
        bar_y = y[i] - bar_height - gap
        oh = opt_hedged[i]
        if oh <= 0:
            continue

        spot = p.get('spot', 0)
        n_sp = p.get('n_std_puts', 0)
        n_mp = p.get('n_micro_puts', 0)
        contract_ccy = resolve_contract(p['currency'], home_currency)

        std_notional = CME_CONTRACTS.get(contract_ccy, {}).get('size', 0) * spot if contract_ccy else 0
        micro_notional = CME_MICRO_CONTRACTS.get(contract_ccy, {}).get('size', 0) * spot if contract_ccy else 0
        std_opt = n_sp * std_notional
        micro_opt = n_mp * micro_notional
        coverage = (oh / exposures[i]) if exposures[i] > 0 else 0
        o_color, o_alpha, o_text = _hedge_color(coverage, COLORS['yellow'])

        if n_sp > 0 and n_mp > 0:
            ax.barh(bar_y, std_opt, bar_height,
                    color=o_color, alpha=o_alpha, edgecolor=COLORS['fg'], linewidth=0.5,
                    label='Options' if not opt_legend_added else None)
            opt_legend_added = True
            ax.barh(bar_y, micro_opt, bar_height, left=std_opt,
                    color=o_color, alpha=o_alpha, edgecolor=COLORS['fg'], linewidth=0.5)
            std_code = p.get('std_code', '')
            micro_code = p.get('micro_code', '')
            for seg_left, seg_width, seg_n, seg_code in [
                (0, std_opt, n_sp, std_code),
                (std_opt, micro_opt, n_mp, micro_code),
            ]:
                frac = seg_width / max(oh, 1)
                if frac < 0.06 or seg_n == 0:
                    continue
                label = f'{seg_n}×{seg_code}' if frac > 0.25 else f'{seg_n}\n×\n{seg_code}'
                fs = 7 if frac > 0.25 else 6
                ax.text(seg_left + seg_width / 2, bar_y,
                        label, ha='center', va='center',
                        fontsize=fs, fontweight='bold', color=o_text,
                        linespacing=0.8)
        elif oh > 0:
            ax.barh(bar_y, oh, bar_height,
                    color=o_color, alpha=o_alpha, edgecolor=COLORS['fg'], linewidth=0.5,
                    label='Options' if not opt_legend_added else None)
            opt_legend_added = True
            micro_code = p.get('micro_code', '')
            if n_mp > 0 and micro_code:
                ax.text(oh / 2, bar_y,
                        f'{n_mp}×{micro_code}', ha='center', va='center',
                        fontsize=7, fontweight='bold', color=o_text)

    ax.set_yticks(y)
    ax.set_yticklabels(currencies, fontsize=11, fontweight='bold')
    ax.set_xlabel('USD', fontsize=11, fontweight='bold', color=COLORS['fg'])
    ax.set_title('Exposure vs Hedge Coverage', fontsize=14, fontweight='bold', color=COLORS['fg'])
    ax.legend(loc='upper right', framealpha=0.9, fontsize=9)
    ax.grid(True, alpha=0.2, axis='x', linestyle='--', color=COLORS['gray'])
    ax.tick_params(colors=COLORS['fg'])

    # Right margin for labels
    all_vals = exposures + hedged + opt_hedged
    max_val = max(all_vals) if all_vals else 1
    ax.set_xlim(right=max_val * 1.35)

    # Annotate values on each bar group
    for i, p in enumerate(plan):
        exp = abs(p['exposure'])
        hdg = p['hedged_usd']
        oh = opt_hedged[i]
        f_cov = (hdg / exp * 100) if exp > 0 else 0
        o_cov = (oh / exp * 100) if exp > 0 else 0

        # Exposure label
        ax.text(exp + 1000, y[i] + bar_height + gap,
                f'{exp:,.0f}', ha='left', va='center',
                fontsize=8, color=COLORS['blue'])
        # Futures label
        if hdg > 0:
            over = ' OVER' if f_cov > 103 else ''
            ax.text(hdg + 1000, y[i],
                    f'{hdg:,.0f} ({f_cov:.1f}%{over})', ha='left', va='center',
                    fontsize=8, color=COLORS['green'])
        else:
            ax.text(1000, y[i],
                    'No hedge', ha='left', va='center',
                    fontsize=8, color=COLORS['orange'])
        # Options label
        if oh > 0:
            cost = p.get('put_cost', 0)
            ax.text(oh + 1000, y[i] - bar_height - gap,
                    f'{oh:,.0f} ({o_cov:.1f}%) \u2014 {cost:,.0f} USD premium',
                    ha='left', va='center', fontsize=8, color=COLORS['yellow'])


def style_table(table, rows, ncols):
    """Apply dark theme styling to a matplotlib table."""
    for i in range(len(rows)):
        for j in range(ncols):
            table[(i, j)].set_facecolor(COLORS['bg'])
            table[(i, j)].set_text_props(color=COLORS['fg'])
            table[(i, j)].set_edgecolor(COLORS['gray'])
    # Header
    for j in range(ncols):
        table[(0, j)].set_facecolor(COLORS['gray'])
        table[(0, j)].set_text_props(weight='bold', color=COLORS['fg'])
        table[(0, j)].set_edgecolor(COLORS['fg'])
    # Totals (last row)
    for j in range(ncols):
        table[(len(rows) - 1, j)].set_facecolor(COLORS['gray'])
        table[(len(rows) - 1, j)].set_text_props(weight='bold', color=COLORS['fg'])
        table[(len(rows) - 1, j)].set_edgecolor(COLORS['fg'])


def plot_action_table(ax, plan: list[dict]):
    """Futures hedge action plan table."""
    ax.axis('off')
    ax.set_facecolor(COLORS['bg'])

    header = ['Currency', 'Exposure', 'Futures Action', 'Margin', 'Coverage', 'Status']
    rows = [header]

    total_exposure = 0
    total_effectively_hedged = 0
    total_margin = 0

    for p in plan:
        exp = abs(p['exposure'])
        hdg = p['hedged_usd']
        total_exposure += exp
        total_effectively_hedged += min(hdg, exp)
        total_margin += p['margin']
        coverage = (hdg / exp * 100) if exp > 0 else 0

        if coverage > 103:
            status = 'Over-hedged'
        elif coverage >= 97:
            status = 'Within threshold'
        elif coverage > 0:
            status = 'Under-hedged'
        else:
            status = '-'

        rows.append([
            f"{p['currency']} ({p['code']})" if p.get('code', '-') != '-' else p['currency'],
            f"${exp:,.0f}",
            p['action'],
            f"${p['margin']:,.0f}" if p['margin'] > 0 else '-',
            f"{coverage:.1f}%",
            status,
        ])

    eff_coverage = (total_effectively_hedged / total_exposure * 100) if total_exposure > 0 else 0
    rows.append(['', '', '', '', '', ''])
    rows.append([
        'TOTAL', f'${total_exposure:,.0f}', '',
        f'${total_margin:,.0f}', f'{eff_coverage:.1f}%', '',
    ])

    ncols = 6
    table = ax.table(cellText=rows, cellLoc='left', loc='center',
                     colWidths=[0.15, 0.13, 0.30, 0.12, 0.12, 0.18])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.8)

    style_table(table, rows, ncols)

    # Color-code action column only
    for i in range(1, len(rows) - 2):
        action = rows[i][2]
        if action.startswith('Buy'):
            table[(i, 2)].set_text_props(weight='bold', color=COLORS['green'])
        elif action.startswith('Too small'):
            table[(i, 2)].set_text_props(color=COLORS['orange'])
        else:
            table[(i, 2)].set_text_props(color=COLORS['red'])

    ax.set_title('Futures Hedge', fontsize=13, fontweight='bold', pad=5, color=COLORS['fg'])


def plot_options_table(ax, plan: list[dict]):
    """Options (put protection) alternative table."""
    ax.axis('off')
    ax.set_facecolor(COLORS['bg'])

    header = ['Currency', 'Vol', 'Put Strike', 'Put Action', 'Cost', 'Status']
    rows = [header]

    total_cost = 0

    for p in plan:
        vol = p.get('vol', 0)
        put_cost = p.get('put_cost', 0)
        put_premium = p.get('put_premium', 0)
        put_strike = p.get('put_strike', 0)
        n_sp = p.get('n_std_puts', 0)
        n_mp = p.get('n_micro_puts', 0)
        exp = abs(p['exposure'])
        oh = p.get('opt_hedged', 0)
        coverage = (oh / exp * 100) if exp > 0 else 0
        total_cost += put_cost

        if coverage > 103:
            status = 'Over-hedged'
        elif coverage >= 97:
            status = 'Within threshold'
        elif coverage > 0:
            status = 'Under-hedged'
        else:
            status = '-'

        if (n_sp > 0 or n_mp > 0) and put_premium > 0:
            parts = []
            if n_sp > 0:
                parts.append(f'{n_sp} × {p.get("std_code", "")}')
            if n_mp > 0:
                parts.append(f'{n_mp} × {p.get("micro_code", "")}')
            action = 'Buy ' + ' + '.join(parts) + ' put'
            rows.append([
                p['currency'],
                f"{vol * 100:.1f}%",
                f"{put_strike:.4f}" if put_strike < 100 else f"{put_strike:,.0f}",
                action,
                f"${put_cost:,.0f}",
                status,
            ])
        else:
            rows.append([
                p['currency'],
                f"{vol * 100:.1f}%" if vol > 0 else '-',
                '-', '-', '-', status,
            ])

    rows.append(['', '', '', '', '', ''])
    rows.append([
        'TOTAL', '', '', '',
        f'${total_cost:,.0f}', '',
    ])

    ncols = 6
    table = ax.table(cellText=rows, cellLoc='left', loc='center',
                     colWidths=[0.12, 0.08, 0.14, 0.34, 0.12, 0.18])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.8)

    style_table(table, rows, ncols)

    # Color put action column only
    for i in range(1, len(rows) - 2):
        action = rows[i][3]
        if action.startswith('Buy'):
            table[(i, 3)].set_text_props(weight='bold', color=COLORS['yellow'])

    ax.set_title('Options Alternative (5% OTM Put, 90d)', fontsize=13,
                 fontweight='bold', pad=5, color=COLORS['fg'])


def main():
    parser = argparse.ArgumentParser(
        description="Visualize portfolio FX exposure and hedge recommendations")
    parser.add_argument("--output", type=str, default=None,
                       help="Output file path (default: show plot)")
    parser.add_argument("--home-currency", type=str, default="USD",
                       help="Home currency (default: USD)")
    args = parser.parse_args()

    try:
        df = load_exposure_data()
        spot_rates = load_spot_rates()
        vols = load_historical_vols()

        if spot_rates:
            print(f"Loaded spot rates for: {', '.join(spot_rates.keys())}")
        else:
            print("No spot rate data found — run fetch first")

        if vols:
            print(f"Historical vols: {', '.join(f'{k}={v:.1%}' for k, v in vols.items())}")

        plan = compute_hedge_plan(df, spot_rates, vols, args.home_currency)
        # Sort so USD (largest) is last → displayed on top in barh
        plan.sort(key=lambda p: abs(p['exposure']))
        portfolio_breakdown = load_portfolio_breakdown()

        # Three-panel layout: chart, futures table, options table
        fig = plt.figure(figsize=(16, 14))
        fig.patch.set_facecolor(COLORS['bg'])
        gs = gridspec.GridSpec(3, 1, figure=fig, hspace=0.35,
                               height_ratios=[1, 0.8, 0.8])

        ax_chart = fig.add_subplot(gs[0])
        ax_futures = fig.add_subplot(gs[1])
        ax_options = fig.add_subplot(gs[2])

        plot_coverage_chart(ax_chart, plan, portfolio_breakdown, args.home_currency)
        plot_action_table(ax_futures, plan)
        plot_options_table(ax_options, plan)

        total_value = df['net_exposure_usd'].abs().sum()
        fig.suptitle(f'FX Hedge Recommendation (Portfolio: ${total_value:,.0f})',
                     fontsize=16, fontweight='bold', y=0.995, color=COLORS['fg'])

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
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

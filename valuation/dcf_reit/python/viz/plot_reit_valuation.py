#!/usr/bin/env python3
"""
Visualize REIT valuation analysis.

Creates two figures per ticker:
1. Valuation Overview: Price vs Fair Value, Methods, Multiple vs Sector, Dividends
2. Fundamentals: Quality Radar, FFO/AFFO Waterfall, NAV Sensitivity, Cost of Capital
"""

import argparse
import sys
from pathlib import Path
import json
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure


def load_valuation(filepath: Path) -> dict:
    """Load valuation results from JSON."""
    with open(filepath) as f:
        return json.load(f)


def print_summary(data: dict):
    """Print valuation summary and investment thesis to console."""
    ticker = data['ticker']
    price = data['price']
    fair_value = data['fair_value']
    upside = data['upside_potential'] * 100
    signal = data['signal']
    reit_type = data.get('reit_type', 'equity')
    is_mreit = reit_type == 'mortgage'
    quality = data['quality']

    income = data.get('income_metrics', {})
    income_yield = income.get('dividend_yield', 0) * 100
    income_coverage = income.get('coverage_ratio', 0)
    income_status = income.get('coverage_status', '-')
    income_score = income.get('income_score', 0)
    income_grade = income.get('income_grade', '-')
    income_rec = income.get('income_recommendation', '-')

    label = 'mREIT' if is_mreit else 'REIT'
    print(f"\n{'='*40}")
    print(f"  {ticker} {label} VALUATION SUMMARY")
    print(f"{'='*40}")
    print(f"  Price:        ${price:.2f}")
    print(f"  Fair Value:   ${fair_value:.2f}")
    print(f"  Upside:       {upside:+.1f}%")
    print(f"  Signal:       {signal}")
    print(f"  Quality:      {quality['overall_quality']:.2f}")
    print()
    print(f"  INCOME VIEW")
    print(f"  Yield:        {income_yield:.2f}%")
    print(f"  Coverage:     {income_coverage:.2f}x ({income_status})")
    print(f"  Score:        {income_score:.0f}/100 ({income_grade})")
    print(f"  Rec:          {income_rec}")

    if is_mreit and 'mreit_metrics' in data:
        mreit = data['mreit_metrics']
        print()
        print(f"  mREIT METRICS")
        print(f"  P/Book:       {mreit['price_to_book']:.2f}x")
        print(f"  DE Payout:    {mreit['de_payout_ratio']*100:.1f}%")
        print(f"  Leverage:     {mreit['leverage_ratio']:.1f}x")
    else:
        ffo = data['ffo_metrics']
        nav = data['nav']
        print()
        print(f"  FFO/NAV")
        print(f"  AFFO/Share:   ${ffo['affo_per_share']:.2f}")
        print(f"  AFFO Payout:  {ffo['affo_payout_ratio']*100:.1f}%")
        print(f"  NAV P/D:      {nav['premium_discount']*100:+.1f}%")

    # Investment thesis
    strengths = []
    weaknesses = []

    if income_coverage >= 1.2:
        strengths.append(f"Well-covered dividend ({income_coverage:.2f}x)")
    elif income_coverage < 0.9:
        weaknesses.append(f"Dividend coverage risk ({income_coverage:.2f}x)")

    if income_score >= 70:
        strengths.append(f"Strong income score: {income_score:.0f}")
    elif income_score < 40:
        weaknesses.append(f"Weak income score: {income_score:.0f}")

    if is_mreit and 'mreit_metrics' in data:
        mreit = data['mreit_metrics']
        if quality['overall_quality'] >= 0.7:
            strengths.append("Strong mREIT fundamentals")
        if mreit['price_to_book'] < 0.9:
            strengths.append(f"Trading at {mreit['price_to_book']:.0%} of book")
        if upside > 15:
            strengths.append(f"{upside:.0f}% upside potential")
        if mreit['net_interest_margin'] > 0.025:
            strengths.append(f"Strong NIM: {mreit['net_interest_margin']*100:.1f}%")
        if quality['balance_sheet_score'] < 0.5:
            weaknesses.append("Elevated leverage")
        if mreit['de_payout_ratio'] > 1.0:
            weaknesses.append("Dividend exceeds DE")
        if mreit['price_to_book'] > 1.05:
            weaknesses.append(f"Premium to book: {(mreit['price_to_book']-1)*100:.0f}%")
        if upside < -10:
            weaknesses.append(f"Overvalued by {abs(upside):.0f}%")
    else:
        ffo = data['ffo_metrics']
        nav = data['nav']
        if quality['overall_quality'] >= 0.7:
            strengths.append("High quality portfolio")
        if nav['premium_discount'] < -0.1:
            strengths.append(f"Trading {abs(nav['premium_discount']*100):.0f}% below NAV")
        if upside > 15:
            strengths.append(f"{upside:.0f}% upside potential")
        if quality['balance_sheet_score'] < 0.5:
            weaknesses.append("Elevated leverage")
        if ffo['affo_payout_ratio'] > 1.0:
            weaknesses.append("Dividend exceeds AFFO")
        if nav['premium_discount'] > 0.15:
            weaknesses.append(f"Premium to NAV: {nav['premium_discount']*100:.0f}%")
        if upside < -10:
            weaknesses.append(f"Overvalued by {abs(upside):.0f}%")

    print()
    print(f"  INVESTMENT THESIS")
    print(f"  Value:  {signal}")
    print(f"  Income: {income_rec}")
    if strengths:
        print(f"  Strengths:")
        for s in strengths[:4]:
            print(f"    + {s}")
    if weaknesses:
        print(f"  Weaknesses:")
        for w in weaknesses[:4]:
            print(f"    - {w}")
    print(f"{'='*40}\n")


def _bar_label(ax, bar, label, max_val, fontsize=10):
    """Place label inside top of bar, or above if bar is too short."""
    val = bar.get_height()
    cx = bar.get_x() + bar.get_width() / 2
    if val < max_val * 0.15:
        ax.text(cx, val + max_val * 0.02, label, ha='center', va='bottom',
                fontsize=fontsize, fontweight='bold')
    else:
        ax.text(cx, val - max_val * 0.02, label, ha='center', va='top',
                fontsize=fontsize, fontweight='bold', color=COLORS['bg'])


def plot_valuation_overview(data: dict, output_file: Path):
    """Figure 1: Valuation Overview (2x2 grid)."""
    setup_dark_mode()

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.subplots_adjust(hspace=0.4, wspace=0.35)

    ticker = data['ticker']
    price = data['price']
    fair_value = data['fair_value']
    upside = data['upside_potential'] * 100
    signal = data['signal']
    reit_type = data.get('reit_type', 'equity')
    is_mreit = reit_type == 'mortgage'
    reit_label = 'mREIT' if is_mreit else 'REIT'
    valuations = data['valuations']

    # --- Plot 1: Price vs Fair Value (top left) ---
    ax = axes[0, 0]
    bar_labels = ['Price', 'Fair Value']
    bar_values = [price, fair_value]
    bar_colors = [COLORS['yellow'], COLORS['green'] if fair_value > price else COLORS['red']]

    bars = ax.bar(bar_labels, bar_values, color=bar_colors, alpha=0.8,
                  edgecolor=COLORS['fg'], width=0.6)
    for bar, val in zip(bars, bar_values):
        _bar_label(ax, bar, f'${val:.2f}', max(bar_values))

    ax.margins(x=0.2)
    ax.set_ylabel('$/Share')
    ax.set_title(f'Price vs Fair Value — {signal} ({upside:+.1f}%)',
                 fontsize=11, fontweight='bold')
    ax.grid(True, alpha=0.2, axis='y')

    # --- Plot 2: Valuation Methods (top right) ---
    ax = axes[0, 1]

    if is_mreit and 'mreit_valuations' in data:
        mreit_vals = data['mreit_valuations']
        methods = ['P/BV', 'P/DE', 'DDM']
        values = [
            mreit_vals['p_bv']['implied_value'],
            mreit_vals['p_de']['implied_value'],
            valuations['ddm']['intrinsic_value']
        ]
        colors_bar = [COLORS['blue'], COLORS['cyan'], COLORS['magenta']]
    else:
        methods = ['P/FFO', 'P/AFFO', 'NAV', 'DDM']
        values = [
            valuations['p_ffo']['implied_value'],
            valuations['p_affo']['implied_value'],
            valuations['nav']['implied_value'],
            valuations['ddm']['intrinsic_value']
        ]
        colors_bar = [COLORS['blue'], COLORS['cyan'], COLORS['green'], COLORS['magenta']]

    bars = ax.barh(methods, values, color=colors_bar, alpha=0.8, edgecolor=COLORS['fg'])
    ax.axvline(price, color=COLORS['yellow'], linestyle='--', linewidth=2,
               label=f'Price ${price:.2f}')
    ax.axvline(fair_value, color=COLORS['green'], linestyle=':', linewidth=2,
               label=f'Fair ${fair_value:.2f}')

    max_val = max(values)
    for bar, val in zip(bars, values):
        ax.text(val - max_val * 0.02, bar.get_y() + bar.get_height()/2,
                f'${val:.2f}', va='center', ha='right', fontsize=9, fontweight='bold',
                color=COLORS['bg'])

    ax.set_xlabel('Value per Share ($)')
    ax.set_title('Valuation Methods', fontsize=11, fontweight='bold')
    ax.legend(loc='best', fontsize=8)
    ax.grid(True, alpha=0.2, axis='x')

    # --- Plot 3: Multiple vs Sector (bottom left) ---
    ax = axes[1, 0]

    if is_mreit and 'mreit_valuations' in data:
        mreit_vals = data['mreit_valuations']
        p_val = mreit_vals['p_bv']['p_bv']
        sector_avg = mreit_vals['p_bv']['sector_avg']
        label_curr = 'Current P/BV'
        label_fmt = '{:.2f}x'
        title_label = 'P/BV'
    else:
        p_val = valuations['p_ffo']['p_ffo']
        sector_avg = valuations['p_ffo']['sector_avg']
        label_curr = 'Current P/FFO'
        label_fmt = '{:.1f}x'
        title_label = 'P/FFO'

    cats = [label_curr, 'Sector Avg']
    vals = [p_val, sector_avg]
    cols = [COLORS['cyan'] if p_val <= sector_avg else COLORS['red'], COLORS['gray']]

    bars = ax.bar(cats, vals, color=cols, alpha=0.8, edgecolor=COLORS['fg'], width=0.6)
    for bar, val in zip(bars, vals):
        _bar_label(ax, bar, label_fmt.format(val), max(vals))

    ax.margins(x=0.2)
    premium_disc = (p_val / sector_avg - 1) * 100 if sector_avg > 0 else 0
    ax.set_title(f'{title_label} Multiple ({premium_disc:+.1f}% vs Sector)',
                 fontsize=11, fontweight='bold')
    ax.set_ylabel('Multiple (x)')
    ax.grid(True, alpha=0.2, axis='y')

    # --- Plot 4: Dividend Analysis (bottom right) ---
    ax = axes[1, 1]

    div_yield = valuations['ddm']['dividend_yield'] * 100

    if is_mreit and 'mreit_metrics' in data:
        mreit = data['mreit_metrics']
        de_ps = mreit['de_per_share']
        de_yield = (de_ps / price * 100) if price > 0 else 0
        payout = mreit['de_payout_ratio'] * 100
        metrics = ['Div Yield', 'DE Yield', 'DE Payout']
        metric_values = [div_yield, de_yield, payout]
    else:
        ffo = data['ffo_metrics']
        affo_ps = ffo['affo_per_share']
        affo_yield = (affo_ps / price * 100) if price > 0 else 0
        payout = ffo['affo_payout_ratio'] * 100
        metrics = ['Div Yield', 'AFFO Yield', 'Payout Ratio']
        metric_values = [div_yield, affo_yield, payout]

    payout_color = COLORS['green'] if payout < 85 else COLORS['yellow'] if payout < 100 else COLORS['red']
    metric_colors = [COLORS['cyan'], COLORS['green'], payout_color]

    bars = ax.bar(metrics, metric_values, color=metric_colors, alpha=0.8,
                  edgecolor=COLORS['fg'], width=0.6)
    for bar, val in zip(bars, metric_values):
        _bar_label(ax, bar, f'{val:.1f}%', max(metric_values))

    ax.margins(x=0.15)
    ax.axhline(100, color=COLORS['red'], linestyle='--', alpha=0.5, label='100% Payout')
    ax.set_ylabel('Percentage (%)')
    ax.set_title('Dividend Analysis', fontsize=11, fontweight='bold')
    ax.legend(loc='best', fontsize=8)
    ax.grid(True, alpha=0.2, axis='y')

    fig.suptitle(f'{ticker} {reit_label} — Valuation Overview',
                 fontsize=14, fontweight='bold', color=COLORS['fg'], y=0.98)

    save_figure(fig, output_file, dpi=300)
    plt.close()
    print(f"Saved: {output_file}")


def plot_fundamentals(data: dict, output_file: Path):
    """Figure 2: Fundamentals (2x2 grid)."""
    setup_dark_mode()

    fig = plt.figure(figsize=(12, 8))
    gs = fig.add_gridspec(2, 2, hspace=0.4, wspace=0.35)

    ticker = data['ticker']
    price = data['price']
    reit_type = data.get('reit_type', 'equity')
    is_mreit = reit_type == 'mortgage'
    reit_label = 'mREIT' if is_mreit else 'REIT'
    quality = data['quality']

    # --- Plot 1: Quality Radar (top left) ---
    ax = fig.add_subplot(gs[0, 0], polar=True)

    if is_mreit:
        categories = ['Balance Sheet', 'NIM Quality', 'Div Safety']
        values_q = [
            quality['balance_sheet_score'],
            quality['growth_score'],
            quality['dividend_safety_score']
        ]
    else:
        categories = ['Occupancy', 'Lease Quality', 'Balance Sheet', 'Growth', 'Div Safety']
        values_q = [
            quality['occupancy_score'],
            quality['lease_quality_score'],
            quality['balance_sheet_score'],
            quality['growth_score'],
            quality['dividend_safety_score']
        ]

    # Clamp to 0
    values_q = [max(0, v) for v in values_q]

    angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
    values_q += values_q[:1]
    angles += angles[:1]

    ax.plot(angles, values_q, 'o-', linewidth=2, color=COLORS['cyan'])
    ax.fill(angles, values_q, alpha=0.25, color=COLORS['cyan'])
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=8)
    ax.set_ylim(0, 1)
    ax.set_title(f"Quality: {quality['overall_quality']:.2f}",
                 fontsize=11, fontweight='bold', y=1.1)

    # --- Plot 2: FFO/NII Waterfall (top right) ---
    ax = fig.add_subplot(gs[0, 1])

    if is_mreit and 'mreit_metrics' in data:
        mreit = data['mreit_metrics']
        nii_ps = mreit['nii_per_share']
        de_ps = mreit['de_per_share']
        int_income_ps = nii_ps * 1.4
        int_expense_ps = int_income_ps - nii_ps

        steps = ['Int Income', '-Int Expense', '=NII', '=DE']
        step_values = [int_income_ps, nii_ps, nii_ps, de_ps]
        colors_wf = [COLORS['green'], COLORS['cyan'], COLORS['cyan'], COLORS['magenta']]
        title = 'NII → DE Breakdown'
    else:
        ni = data['ffo_metrics']['ffo_per_share'] * 0.6
        dep = data['ffo_metrics']['ffo_per_share'] * 0.45
        gains = data['ffo_metrics']['ffo_per_share'] * 0.05
        ffo_ps = data['ffo_metrics']['ffo_per_share']
        maint = data['ffo_metrics']['affo_per_share'] - ffo_ps if ffo_ps > data['ffo_metrics']['affo_per_share'] else 0
        affo_ps = data['ffo_metrics']['affo_per_share']

        steps = ['Net Income', '+D&A', '-Gains', '=FFO', '-Maint', '=AFFO']
        step_values = [ni, ni + dep, ni + dep - gains, ffo_ps, ffo_ps + maint, affo_ps]
        colors_wf = [COLORS['blue'], COLORS['green'], COLORS['red'],
                     COLORS['cyan'], COLORS['orange'], COLORS['magenta']]
        title = 'FFO → AFFO Breakdown'

    wf_bars = ax.bar(steps, step_values, color=colors_wf, alpha=0.8, edgecolor=COLORS['fg'])
    for bar, val in zip(wf_bars, step_values):
        _bar_label(ax, bar, f'${val:.2f}', max(step_values), fontsize=9)

    ax.margins(x=0.08)
    ax.set_ylabel('Per Share ($)')
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.tick_params(axis='x', rotation=30)
    ax.grid(True, alpha=0.2, axis='y')

    # --- Plot 3: NAV / P/BV Sensitivity (bottom left) ---
    ax = fig.add_subplot(gs[1, 0])

    if is_mreit and 'mreit_metrics' in data:
        mreit = data['mreit_metrics']
        bvps = mreit['book_value_per_share']
        current_pbv = mreit['price_to_book']

        pbv_multiples = np.array([0.6, 0.7, 0.8, 0.85, 0.9, 1.0, 1.1])
        implied_prices = bvps * pbv_multiples

        ax.plot(pbv_multiples, implied_prices, 'o-', color=COLORS['green'],
                linewidth=2, markersize=6, label='Implied Price')
        ax.axhline(price, color=COLORS['yellow'], linestyle='--',
                   label=f'Price ${price:.2f}')
        ax.axvline(current_pbv, color=COLORS['cyan'], linestyle=':',
                   label=f'P/BV {current_pbv:.2f}x')
        ax.fill_between(pbv_multiples, implied_prices, price,
                        where=(implied_prices > price), alpha=0.2, color=COLORS['green'])
        ax.fill_between(pbv_multiples, implied_prices, price,
                        where=(implied_prices <= price), alpha=0.2, color=COLORS['red'])

        ax.set_xlabel('Price/Book Multiple')
        ax.set_ylabel('Implied Price ($)')
        ax.set_title(f'P/BV Sensitivity (BV=${bvps:.2f})', fontsize=11, fontweight='bold')
    else:
        nav = data['nav']
        base_cap = 0.055
        cap_rates = np.array([0.04, 0.045, 0.05, 0.055, 0.06, 0.065, 0.07])
        base_nav = nav['nav_per_share']
        nav_values = base_nav * (base_cap / cap_rates)

        ax.plot(cap_rates * 100, nav_values, 'o-', color=COLORS['green'],
                linewidth=2, markersize=6, label='NAV/Share')
        ax.axhline(price, color=COLORS['yellow'], linestyle='--',
                   label=f'Price ${price:.2f}')
        ax.axhline(base_nav, color=COLORS['cyan'], linestyle=':',
                   label=f'Base NAV ${base_nav:.2f}')
        ax.fill_between(cap_rates * 100, nav_values, price,
                        where=(nav_values > price), alpha=0.2, color=COLORS['green'])
        ax.fill_between(cap_rates * 100, nav_values, price,
                        where=(nav_values <= price), alpha=0.2, color=COLORS['red'])

        ax.set_xlabel('Cap Rate (%)')
        ax.set_ylabel('NAV per Share ($)')
        ax.set_title('NAV Sensitivity to Cap Rate', fontsize=11, fontweight='bold')

    ax.legend(loc='best', fontsize=8)
    ax.grid(True, alpha=0.2)

    # --- Plot 4: Cost of Capital (bottom right) ---
    ax = fig.add_subplot(gs[1, 1])

    coc = data['cost_of_capital']
    coc_labels = ['Cost of Equity', 'Cost of Debt', 'WACC']
    coc_values = [coc['cost_of_equity'] * 100, coc['cost_of_debt'] * 100, coc['wacc'] * 100]
    coc_colors = [COLORS['cyan'], COLORS['blue'], COLORS['magenta']]

    bars = ax.bar(coc_labels, coc_values, color=coc_colors, alpha=0.8,
                  edgecolor=COLORS['fg'], width=0.6)
    for bar, val in zip(bars, coc_values):
        _bar_label(ax, bar, f'{val:.2f}%', max(coc_values))

    ax.margins(x=0.15)
    ax.text(0.5, 0.92, f'β = {coc["reit_beta"]:.2f}',
            ha='center', fontsize=10, color=COLORS['yellow'],
            transform=ax.transAxes)

    ax.set_ylabel('Rate (%)')
    ax.set_title('Cost of Capital', fontsize=11, fontweight='bold')
    ax.grid(True, alpha=0.2, axis='y')

    fig.suptitle(f'{ticker} {reit_label} — Fundamentals',
                 fontsize=14, fontweight='bold', color=COLORS['fg'], y=0.98)

    save_figure(fig, output_file, dpi=300)
    plt.close()
    print(f"Saved: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Visualize REIT valuation')
    parser.add_argument('-i', '--input', type=str, required=True,
                        help='Input JSON valuation file')
    parser.add_argument('-o', '--output-dir', type=str, default='valuation/dcf_reit/output/plots',
                        help='Output directory for plots')

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = load_valuation(input_path)
    ticker = data['ticker']
    reit_type = data.get('reit_type', 'equity')
    prefix = f"{ticker}_mreit" if reit_type == 'mortgage' else f"{ticker}_reit"

    # Print summary to console
    print_summary(data)

    # Figure 1: Valuation Overview
    plot_valuation_overview(data, output_dir / f"{prefix}_valuation.png")

    # Figure 2: Fundamentals
    plot_fundamentals(data, output_dir / f"{prefix}_fundamentals.png")


if __name__ == '__main__':
    main()

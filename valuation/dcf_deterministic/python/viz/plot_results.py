#!/usr/bin/env python3
"""
Deterministic DCF Visualization Tool

Generates visualizations from deterministic DCF valuation results:
1. Waterfall chart - Breakdown of valuation components
2. Sensitivity analysis - Impact of key assumptions
3. FCFE vs FCFF comparison - Bar chart comparing both methods
4. Cost of capital breakdown - Visual breakdown of WACC, CE, CB
"""

import argparse
import sys
import re
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import save_figure
from lib.python.retry import retry_with_backoff

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


def parse_log_file(log_path):
    """Extract valuation data from DCF or Bank log file."""
    with open(log_path, 'r') as f:
        content = f.read()

    data = {}

    # Check if this is a bank, insurance, or O&G valuation
    is_bank = 'Bank Valuation:' in content
    is_insurance = 'Insurance Valuation:' in content
    is_oil_gas = 'Oil & Gas E&P Valuation:' in content

    # Extract ticker (handle DCF, Bank, Insurance, and O&G formats)
    if is_bank:
        match = re.search(r'Bank Valuation: (\w+)', content)
    elif is_insurance:
        match = re.search(r'Insurance Valuation: (\w+)', content)
    elif is_oil_gas:
        match = re.search(r'Oil & Gas E&P Valuation: (\w+)', content)
    else:
        match = re.search(r'DCF Valuation: (\w+)', content)
    data['ticker'] = match.group(1) if match else 'Unknown'
    data['is_bank'] = is_bank
    data['is_insurance'] = is_insurance
    data['is_oil_gas'] = is_oil_gas

    # Extract market price (note: format is "Current Price: $...")
    match = re.search(r'Current Price: \$([0-9.]+)', content)
    data['price'] = float(match.group(1)) if match else 0.0

    if is_bank:
        # Bank valuation: use Fair Value per Share for both FCFE and FCFF
        match = re.search(r'Fair Value per Share: \$([0-9.-]+)', content)
        fair_value = float(match.group(1)) if match else 0.0
        data['fcfe_ivps'] = fair_value
        data['fcff_ivps'] = fair_value

        # Extract bank-specific metrics
        match = re.search(r'ROE: ([0-9.-]+)%', content)
        data['roe'] = float(match.group(1)) if match else 0.0

        match = re.search(r'Price/Book: ([0-9.]+)x', content)
        data['price_to_book'] = float(match.group(1)) if match else 0.0

        # Banks don't have WACC/CB in the same sense
        data['wacc'] = 0.0
        data['cb'] = 0.0
        data['beta'] = 1.0  # Default bank beta
    elif is_insurance:
        # Insurance valuation: use Fair Value per Share for both FCFE and FCFF
        match = re.search(r'Fair Value per Share: \$([0-9.-]+)', content)
        fair_value = float(match.group(1)) if match else 0.0
        data['fcfe_ivps'] = fair_value
        data['fcff_ivps'] = fair_value

        # Extract insurance-specific metrics
        match = re.search(r'Combined Ratio: ([0-9.]+)%', content)
        data['combined_ratio'] = float(match.group(1)) if match else 0.0

        match = re.search(r'Underwriting Margin: ([0-9.-]+)%', content)
        data['underwriting_margin'] = float(match.group(1)) if match else 0.0

        match = re.search(r'ROE: ([0-9.-]+)%', content)
        data['roe'] = float(match.group(1)) if match else 0.0

        match = re.search(r'Investment Yield: ([0-9.]+)%', content)
        data['investment_yield'] = float(match.group(1)) if match else 0.0

        match = re.search(r'Float/Equity: ([0-9.]+)x', content)
        data['float_to_equity'] = float(match.group(1)) if match else 0.0

        match = re.search(r'Price/Book: ([0-9.]+)x', content)
        data['price_to_book'] = float(match.group(1)) if match else 0.0

        # Insurance doesn't have WACC/CB in the same sense
        data['wacc'] = 0.0
        data['cb'] = 0.0
        data['beta'] = 1.0  # Default insurance beta
    elif is_oil_gas:
        # O&G valuation: use Fair Value per Share for both FCFE and FCFF
        match = re.search(r'Fair Value per Share: \$([0-9.-]+)', content)
        fair_value = float(match.group(1)) if match else 0.0
        data['fcfe_ivps'] = fair_value
        data['fcff_ivps'] = fair_value

        # Extract O&G-specific metrics
        match = re.search(r'Reserve Life: ([0-9.]+) years', content)
        data['reserve_life'] = float(match.group(1)) if match else 0.0

        match = re.search(r'EV/EBITDAX: ([0-9.]+)x', content)
        data['ev_to_ebitdax'] = float(match.group(1)) if match else 0.0

        match = re.search(r'Debt/EBITDAX: ([0-9.]+)x', content)
        data['debt_to_ebitdax'] = float(match.group(1)) if match else 0.0

        match = re.search(r'Netback: \$([0-9.]+)/BOE', content)
        data['netback'] = float(match.group(1)) if match else 0.0

        match = re.search(r'Recycle Ratio: ([0-9.]+)x', content)
        data['recycle_ratio'] = float(match.group(1)) if match else 0.0

        match = re.search(r'Market-Implied Oil Price: \$([0-9.]+)/bbl', content)
        data['implied_oil_price'] = float(match.group(1)) if match else None

        # O&G doesn't have WACC/CB in the same sense
        data['wacc'] = 0.0
        data['cb'] = 0.0
        data['beta'] = 1.0  # Default O&G beta
    else:
        # Standard DCF valuation
        # Extract FCFE values (from "FCFE Method:" section)
        match = re.search(r'FCFE Method:.*?Intrinsic Value per Share: \$([0-9.-]+)', content, re.DOTALL)
        if match:
            data['fcfe_ivps'] = float(match.group(1))
        else:
            data['fcfe_ivps'] = 0.0

        # Extract FCFF values (from "FCFF Method:" section)
        match = re.search(r'FCFF Method:.*?Intrinsic Value per Share: \$([0-9.-]+)', content, re.DOTALL)
        if match:
            data['fcff_ivps'] = float(match.group(1))
        else:
            data['fcff_ivps'] = 0.0

        match = re.search(r'WACC: ([0-9.]+)%', content)
        data['wacc'] = float(match.group(1)) if match else 0.0

        match = re.search(r'Cost of Borrowing: ([0-9.]+)%', content)
        data['cb'] = float(match.group(1)) if match else 0.0

        match = re.search(r'Leveraged Beta: ([0-9.]+)', content)
        data['beta'] = float(match.group(1)) if match else 0.0

    # Extract cost of equity (common to both)
    match = re.search(r'Cost of Equity: ([0-9.]+)%', content)
    data['ce'] = float(match.group(1)) if match else 0.0

    # Extract signal
    match = re.search(r'Investment Signal: (\w+)', content)
    data['signal'] = match.group(1) if match else 'Unknown'

    return data


def _generate_sensitivity_plot(args):
    """Wrapper function for parallel sensitivity plot generation."""
    data, output_file, csv_dir, dark_mode = args
    # Set up the appropriate theme for this process
    if dark_mode:
        setup_dark_mode()
    else:
        setup_light_mode()
    return plot_sensitivity(data, output_file, csv_dir, dark_mode)


def linear_extrapolate(x, x1, x2, y1, y2):
    """Manual linear extrapolation (np.interp doesn't extrapolate)."""
    slope = (y2 - y1) / (x2 - x1)
    return y2 + slope * (x - x2)

def get_company_name(ticker):
    """Fetch company name from yfinance."""
    try:
        stock = yf.Ticker(ticker)
        info = retry_with_backoff(lambda: stock.info)
        company_name = info.get('shortName', ticker)
        return company_name
    except Exception:
        # If fetching fails, just return the ticker
        return ticker

def plot_sensitivity(data, output_file, csv_dir, dark_mode=False):
    """Generate sensitivity analysis from CSV files."""
    ticker = data['ticker']
    price = data['price']
    fcfe_base = data['fcfe_ivps']
    fcff_base = data['fcff_ivps']

    # Get company name
    company_name = get_company_name(ticker)

    # Set colors based on mode - using more contrastive colors
    if dark_mode:
        price_color = KANAGAWA_DRAGON['red']
        fcfe_color = KANAGAWA_DRAGON['cyan']
        fcff_color = KANAGAWA_DRAGON['yellow']
        edge_color = KANAGAWA_DRAGON['fg']
        text_color = KANAGAWA_DRAGON['fg']
    else:
        price_color = KANAGAWA_LOTUS['red']
        fcfe_color = KANAGAWA_LOTUS['cyan']
        fcff_color = KANAGAWA_LOTUS['yellow']
        edge_color = KANAGAWA_LOTUS['fg']
        text_color = KANAGAWA_LOTUS['fg']

    # Load sensitivity CSV files
    csv_dir = Path(csv_dir)
    growth_file = csv_dir / f"sensitivity_growth_{ticker}.csv"
    discount_file = csv_dir / f"sensitivity_discount_{ticker}.csv"
    terminal_file = csv_dir / f"sensitivity_terminal_{ticker}.csv"

    # Check if CSV files exist
    if not all([growth_file.exists(), discount_file.exists(), terminal_file.exists()]):
        print(f"Warning: Sensitivity CSV files not found for {ticker}, skipping", file=sys.stderr)
        return

    # Read CSV files
    df_growth = pd.read_csv(growth_file)
    df_discount = pd.read_csv(discount_file)
    df_terminal = pd.read_csv(terminal_file)

    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))

    # 1. Growth rate sensitivity
    # Plot market price first (so it appears at top of legend)
    ax1.axhline(y=price, color=price_color, linestyle='--', linewidth=2.0, label='Market Price')
    # Plot base data
    ax1.plot(df_growth['growth_rate_pct'], df_growth['fcff_ivps'], 'o-', label='FCFF', color=fcff_color, linewidth=2.0, markersize=6)
    ax1.plot(df_growth['growth_rate_pct'], df_growth['fcfe_ivps'], 'o-', label='FCFE', color=fcfe_color, linewidth=2.0, markersize=6)

    # Find implied growth rate - check if extrapolation is needed
    fcfe_min = df_growth['fcfe_ivps'].min()
    fcfe_max = df_growth['fcfe_ivps'].max()
    fcff_min = df_growth['fcff_ivps'].min()
    fcff_max = df_growth['fcff_ivps'].max()
    growth_min = df_growth['growth_rate_pct'].min()
    growth_max = df_growth['growth_rate_pct'].max()

    # Check if FCFE/FCFF are increasing or decreasing with growth
    fcfe_increasing = df_growth['fcfe_ivps'].iloc[-1] > df_growth['fcfe_ivps'].iloc[0]
    fcff_increasing = df_growth['fcff_ivps'].iloc[-1] > df_growth['fcff_ivps'].iloc[0]

    # Calculate implied growth for FCFF (plot FCFF first)
    if fcff_increasing:
        extrapolate_left_ff = (price < fcff_min)
        extrapolate_right_ff = (price > fcff_max)
    else:
        extrapolate_left_ff = (price > fcff_max)
        extrapolate_right_ff = (price < fcff_min)

    if extrapolate_left_ff:
        x1, x2 = df_growth['fcff_ivps'].values[:2]
        y1, y2 = df_growth['growth_rate_pct'].values[:2]
        fcff_growth_implied = linear_extrapolate(price, x1, x2, y1, y2)
        growth_ext = np.linspace(fcff_growth_implied - 0.5, y1, 10)
        fcff_ext = linear_extrapolate(growth_ext, y1, y2, x1, x2)
        ax1.plot(growth_ext, fcff_ext, '--', color=fcff_color, linewidth=1.8, alpha=0.8, label='FCFF Extrapolation')
    elif extrapolate_right_ff:
        x1, x2 = df_growth['fcff_ivps'].values[-2:]
        y1, y2 = df_growth['growth_rate_pct'].values[-2:]
        fcff_growth_implied = linear_extrapolate(price, x1, x2, y1, y2)
        growth_ext = np.linspace(y2, fcff_growth_implied + 0.5, 10)
        fcff_ext = linear_extrapolate(growth_ext, y1, y2, x1, x2)
        ax1.plot(growth_ext, fcff_ext, '--', color=fcff_color, linewidth=1.8, alpha=0.8, label='FCFF Extrapolation')
    else:
        if fcff_increasing:
            fcff_growth_implied = np.interp(price, df_growth['fcff_ivps'], df_growth['growth_rate_pct'])
        else:
            fcff_growth_implied = np.interp(price, df_growth['fcff_ivps'][::-1], df_growth['growth_rate_pct'][::-1])

    # Calculate implied growth for FCFE
    if fcfe_increasing:
        extrapolate_left = (price < fcfe_min)
        extrapolate_right = (price > fcfe_max)
    else:
        extrapolate_left = (price > fcfe_max)
        extrapolate_right = (price < fcfe_min)

    if extrapolate_left:
        x1, x2 = df_growth['fcfe_ivps'].values[:2]
        y1, y2 = df_growth['growth_rate_pct'].values[:2]
        fcfe_growth_implied = linear_extrapolate(price, x1, x2, y1, y2)
        growth_ext = np.linspace(fcfe_growth_implied - 0.5, y1, 10)
        fcfe_ext = linear_extrapolate(growth_ext, y1, y2, x1, x2)
        ax1.plot(growth_ext, fcfe_ext, '--', color=fcfe_color, linewidth=1.8, alpha=0.8, label='FCFE Extrapolation')
    elif extrapolate_right:
        x1, x2 = df_growth['fcfe_ivps'].values[-2:]
        y1, y2 = df_growth['growth_rate_pct'].values[-2:]
        fcfe_growth_implied = linear_extrapolate(price, x1, x2, y1, y2)
        growth_ext = np.linspace(y2, fcfe_growth_implied + 0.5, 10)
        fcfe_ext = linear_extrapolate(growth_ext, y1, y2, x1, x2)
        ax1.plot(growth_ext, fcfe_ext, '--', color=fcfe_color, linewidth=1.8, alpha=0.8, label='FCFE Extrapolation')
    else:
        if fcfe_increasing:
            fcfe_growth_implied = np.interp(price, df_growth['fcfe_ivps'], df_growth['growth_rate_pct'])
        else:
            fcfe_growth_implied = np.interp(price, df_growth['fcfe_ivps'][::-1], df_growth['growth_rate_pct'][::-1])

    # Plot implied values for both FCFF and FCFE (FCFF first)
    ax1.plot(fcff_growth_implied, price, 'o', color=fcff_color, markersize=10, zorder=5,
             label=f'FCFF Implied: {fcff_growth_implied:.1f}%')

    ax1.plot(fcfe_growth_implied, price, 'o', color=fcfe_color, markersize=10, zorder=5,
             label=f'FCFE Implied: {fcfe_growth_implied:.1f}%')

    # Extend x-axis to show both implied values
    min_implied = min(fcfe_growth_implied, fcff_growth_implied)
    max_implied = max(fcfe_growth_implied, fcff_growth_implied)

    if min_implied < growth_min or max_implied > growth_max:
        x_min = min(growth_min, min_implied - 0.5)
        x_max = max(growth_max, max_implied + 0.5)
        ax1.set_xlim(x_min, x_max)

    ax1.set_xlabel('Growth Rate (%)', fontsize=11, fontweight='bold')
    ax1.set_ylabel('Intrinsic Value ($)', fontsize=11, fontweight='bold')
    ax1.set_title('Sensitivity to Growth Rate', fontsize=12, fontweight='bold')

    # Legend is created automatically from the plot labels
    ax1.legend(fontsize=9, loc='best')
    ax1.grid(True, alpha=0.3, linewidth=0.6)

    # 2. Discount rate sensitivity
    # Plot market price first (so it appears at top of legend)
    ax2.axhline(y=price, color=price_color, linestyle='--', linewidth=2.0, label='Market Price')
    # Plot base data
    ax2.plot(df_discount['discount_rate_pct'], df_discount['fcff_ivps'], 'o-', label='FCFF', color=fcff_color, linewidth=2.0, markersize=6)
    ax2.plot(df_discount['discount_rate_pct'], df_discount['fcfe_ivps'], 'o-', label='FCFE', color=fcfe_color, linewidth=2.0, markersize=6)

    # Find implied discount rate - check if extrapolation is needed
    fcfe_disc_min = df_discount['fcfe_ivps'].min()
    fcfe_disc_max = df_discount['fcfe_ivps'].max()
    fcff_disc_min = df_discount['fcff_ivps'].min()
    fcff_disc_max = df_discount['fcff_ivps'].max()
    disc_min = df_discount['discount_rate_pct'].min()
    disc_max = df_discount['discount_rate_pct'].max()

    # Check if FCFE/FCFF are increasing or decreasing with discount rate
    fcfe_disc_increasing = df_discount['fcfe_ivps'].iloc[-1] > df_discount['fcfe_ivps'].iloc[0]
    fcff_disc_increasing = df_discount['fcff_ivps'].iloc[-1] > df_discount['fcff_ivps'].iloc[0]

    # Calculate implied discount rate for FCFF (plot FCFF first)
    if fcff_disc_increasing:
        extrapolate_disc_left_ff = (price < fcff_disc_min)
        extrapolate_disc_right_ff = (price > fcff_disc_max)
    else:
        extrapolate_disc_left_ff = (price > fcff_disc_max)
        extrapolate_disc_right_ff = (price < fcff_disc_min)

    if extrapolate_disc_left_ff:
        x1, x2 = df_discount['fcff_ivps'].values[:2]
        y1, y2 = df_discount['discount_rate_pct'].values[:2]
        fcff_disc_implied = linear_extrapolate(price, x1, x2, y1, y2)
        disc_ext = np.linspace(fcff_disc_implied - 0.5, y1, 10)
        fcff_ext = linear_extrapolate(disc_ext, y1, y2, x1, x2)
        ax2.plot(disc_ext, fcff_ext, '--', color=fcff_color, linewidth=1.8, alpha=0.8, label='FCFF Extrapolation')
    elif extrapolate_disc_right_ff:
        x1, x2 = df_discount['fcff_ivps'].values[-2:]
        y1, y2 = df_discount['discount_rate_pct'].values[-2:]
        fcff_disc_implied = linear_extrapolate(price, x1, x2, y1, y2)
        disc_ext = np.linspace(y2, fcff_disc_implied + 0.5, 10)
        fcff_ext = linear_extrapolate(disc_ext, y1, y2, x1, x2)
        ax2.plot(disc_ext, fcff_ext, '--', color=fcff_color, linewidth=1.8, alpha=0.8, label='FCFF Extrapolation')
    else:
        if fcff_disc_increasing:
            fcff_disc_implied = np.interp(price, df_discount['fcff_ivps'], df_discount['discount_rate_pct'])
        else:
            fcff_disc_implied = np.interp(price, df_discount['fcff_ivps'][::-1], df_discount['discount_rate_pct'][::-1])

    # Calculate implied discount rate for FCFE
    if fcfe_disc_increasing:
        extrapolate_disc_left = (price < fcfe_disc_min)
        extrapolate_disc_right = (price > fcfe_disc_max)
    else:
        extrapolate_disc_left = (price > fcfe_disc_max)
        extrapolate_disc_right = (price < fcfe_disc_min)

    if extrapolate_disc_left:
        x1, x2 = df_discount['fcfe_ivps'].values[:2]
        y1, y2 = df_discount['discount_rate_pct'].values[:2]
        fcfe_disc_implied = linear_extrapolate(price, x1, x2, y1, y2)
        disc_ext = np.linspace(fcfe_disc_implied - 0.5, y1, 10)
        fcfe_ext = linear_extrapolate(disc_ext, y1, y2, x1, x2)
        ax2.plot(disc_ext, fcfe_ext, '--', color=fcfe_color, linewidth=1.8, alpha=0.8, label='FCFE Extrapolation')
    elif extrapolate_disc_right:
        x1, x2 = df_discount['fcfe_ivps'].values[-2:]
        y1, y2 = df_discount['discount_rate_pct'].values[-2:]
        fcfe_disc_implied = linear_extrapolate(price, x1, x2, y1, y2)
        disc_ext = np.linspace(y2, fcfe_disc_implied + 0.5, 10)
        fcfe_ext = linear_extrapolate(disc_ext, y1, y2, x1, x2)
        ax2.plot(disc_ext, fcfe_ext, '--', color=fcfe_color, linewidth=1.8, alpha=0.8, label='FCFE Extrapolation')
    else:
        if fcfe_disc_increasing:
            fcfe_disc_implied = np.interp(price, df_discount['fcfe_ivps'], df_discount['discount_rate_pct'])
        else:
            fcfe_disc_implied = np.interp(price, df_discount['fcfe_ivps'][::-1], df_discount['discount_rate_pct'][::-1])

    # Plot implied values for both FCFF and FCFE (FCFF first)
    ax2.plot(fcff_disc_implied, price, 'o', color=fcff_color, markersize=10, zorder=5,
             label=f'FCFF Implied: {fcff_disc_implied:.1f}%')

    ax2.plot(fcfe_disc_implied, price, 'o', color=fcfe_color, markersize=10, zorder=5,
             label=f'FCFE Implied: {fcfe_disc_implied:.1f}%')

    # Extend x-axis to show both implied values
    min_disc_implied = min(fcfe_disc_implied, fcff_disc_implied)
    max_disc_implied = max(fcfe_disc_implied, fcff_disc_implied)

    if min_disc_implied < disc_min or max_disc_implied > disc_max:
        x_min = min(disc_min, min_disc_implied - 0.5)
        x_max = max(disc_max, max_disc_implied + 0.5)
        ax2.set_xlim(x_min, x_max)

    ax2.set_xlabel('Rate (%)', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Intrinsic Value ($)', fontsize=11, fontweight='bold')
    ax2.set_title('Sensitivity to Discount Rate', fontsize=12, fontweight='bold')

    # Legend is created automatically from the plot labels
    ax2.legend(fontsize=9, loc='best')
    ax2.grid(True, alpha=0.3, linewidth=0.6)

    # 3. Terminal growth sensitivity
    # Plot market price first (so it appears at top of legend)
    ax3.axhline(y=price, color=price_color, linestyle='--', linewidth=2.0, label='Market Price')
    # Plot base data
    ax3.plot(df_terminal['terminal_growth_pct'], df_terminal['fcff_ivps'], 'o-', label='FCFF', color=fcff_color, linewidth=2.0, markersize=6)
    ax3.plot(df_terminal['terminal_growth_pct'], df_terminal['fcfe_ivps'], 'o-', label='FCFE', color=fcfe_color, linewidth=2.0, markersize=6)

    # Find implied terminal growth - check if extrapolation is needed
    fcfe_term_min = df_terminal['fcfe_ivps'].min()
    fcfe_term_max = df_terminal['fcfe_ivps'].max()
    fcff_term_min = df_terminal['fcff_ivps'].min()
    fcff_term_max = df_terminal['fcff_ivps'].max()
    term_min = df_terminal['terminal_growth_pct'].min()
    term_max = df_terminal['terminal_growth_pct'].max()

    # Check if FCFE/FCFF are increasing or decreasing with terminal growth
    fcfe_term_increasing = df_terminal['fcfe_ivps'].iloc[-1] > df_terminal['fcfe_ivps'].iloc[0]
    fcff_term_increasing = df_terminal['fcff_ivps'].iloc[-1] > df_terminal['fcff_ivps'].iloc[0]

    # Calculate implied terminal growth for FCFF (plot FCFF first)
    if fcff_term_increasing:
        extrapolate_term_left_ff = (price < fcff_term_min)
        extrapolate_term_right_ff = (price > fcff_term_max)
    else:
        extrapolate_term_left_ff = (price > fcff_term_max)
        extrapolate_term_right_ff = (price < fcff_term_min)

    if extrapolate_term_left_ff:
        x1, x2 = df_terminal['fcff_ivps'].values[:2]
        y1, y2 = df_terminal['terminal_growth_pct'].values[:2]
        fcff_term_implied = linear_extrapolate(price, x1, x2, y1, y2)
        term_ext = np.linspace(fcff_term_implied - 0.25, y1, 10)
        fcff_ext = linear_extrapolate(term_ext, y1, y2, x1, x2)
        ax3.plot(term_ext, fcff_ext, '--', color=fcff_color, linewidth=1.8, alpha=0.8, label='FCFF Extrapolation')
    elif extrapolate_term_right_ff:
        x1, x2 = df_terminal['fcff_ivps'].values[-2:]
        y1, y2 = df_terminal['terminal_growth_pct'].values[-2:]
        fcff_term_implied = linear_extrapolate(price, x1, x2, y1, y2)
        term_ext = np.linspace(y2, fcff_term_implied + 0.25, 10)
        fcff_ext = linear_extrapolate(term_ext, y1, y2, x1, x2)
        ax3.plot(term_ext, fcff_ext, '--', color=fcff_color, linewidth=1.8, alpha=0.8, label='FCFF Extrapolation')
    else:
        if fcff_term_increasing:
            fcff_term_implied = np.interp(price, df_terminal['fcff_ivps'], df_terminal['terminal_growth_pct'])
        else:
            fcff_term_implied = np.interp(price, df_terminal['fcff_ivps'][::-1], df_terminal['terminal_growth_pct'][::-1])

    # Calculate implied terminal growth for FCFE
    if fcfe_term_increasing:
        extrapolate_term_left = (price < fcfe_term_min)
        extrapolate_term_right = (price > fcfe_term_max)
    else:
        extrapolate_term_left = (price > fcfe_term_max)
        extrapolate_term_right = (price < fcfe_term_min)

    if extrapolate_term_left:
        x1, x2 = df_terminal['fcfe_ivps'].values[:2]
        y1, y2 = df_terminal['terminal_growth_pct'].values[:2]
        fcfe_term_implied = linear_extrapolate(price, x1, x2, y1, y2)
        term_ext = np.linspace(fcfe_term_implied - 0.25, y1, 10)
        fcfe_ext = linear_extrapolate(term_ext, y1, y2, x1, x2)
        ax3.plot(term_ext, fcfe_ext, '--', color=fcfe_color, linewidth=1.8, alpha=0.8, label='FCFE Extrapolation')
    elif extrapolate_term_right:
        x1, x2 = df_terminal['fcfe_ivps'].values[-2:]
        y1, y2 = df_terminal['terminal_growth_pct'].values[-2:]
        fcfe_term_implied = linear_extrapolate(price, x1, x2, y1, y2)
        term_ext = np.linspace(y2, fcfe_term_implied + 0.25, 10)
        fcfe_ext = linear_extrapolate(term_ext, y1, y2, x1, x2)
        ax3.plot(term_ext, fcfe_ext, '--', color=fcfe_color, linewidth=1.8, alpha=0.8, label='FCFE Extrapolation')
    else:
        if fcfe_term_increasing:
            fcfe_term_implied = np.interp(price, df_terminal['fcfe_ivps'], df_terminal['terminal_growth_pct'])
        else:
            fcfe_term_implied = np.interp(price, df_terminal['fcfe_ivps'][::-1], df_terminal['terminal_growth_pct'][::-1])

    # Plot implied values for both FCFF and FCFE (FCFF first)
    ax3.plot(fcff_term_implied, price, 'o', color=fcff_color, markersize=10, zorder=5,
             label=f'FCFF Implied: {fcff_term_implied:.1f}%')

    ax3.plot(fcfe_term_implied, price, 'o', color=fcfe_color, markersize=10, zorder=5,
             label=f'FCFE Implied: {fcfe_term_implied:.1f}%')

    # Extend x-axis to show both implied values
    min_term_implied = min(fcfe_term_implied, fcff_term_implied)
    max_term_implied = max(fcfe_term_implied, fcff_term_implied)

    if min_term_implied < term_min or max_term_implied > term_max:
        x_min = min(term_min, min_term_implied - 0.25)
        x_max = max(term_max, max_term_implied + 0.25)
        ax3.set_xlim(x_min, x_max)

    ax3.set_xlabel('Terminal Growth Rate (%)', fontsize=11, fontweight='bold')
    ax3.set_ylabel('Intrinsic Value ($)', fontsize=11, fontweight='bold')
    ax3.set_title('Sensitivity to Terminal Growth', fontsize=12, fontweight='bold')

    # Simplified legend (auto-generated from plot labels)
    ax3.legend(fontsize=9, loc='best')
    ax3.grid(True, alpha=0.3, linewidth=0.6)

    # 4. Tornado diagram (based on real data ranges) - Both FCFE and FCFF
    vars = ['Growth\n Rate', 'Discount\nRate', 'Terminal\nGrowth']
    fcfe_low = [df_growth['fcfe_ivps'].min(), df_discount['fcfe_ivps'].min(), df_terminal['fcfe_ivps'].min()]
    fcfe_high = [df_growth['fcfe_ivps'].max(), df_discount['fcfe_ivps'].max(), df_terminal['fcfe_ivps'].max()]
    fcff_low = [df_growth['fcff_ivps'].min(), df_discount['fcff_ivps'].min(), df_terminal['fcff_ivps'].min()]
    fcff_high = [df_growth['fcff_ivps'].max(), df_discount['fcff_ivps'].max(), df_terminal['fcff_ivps'].max()]

    # Get parameter ranges for annotations
    growth_range = [df_growth['growth_rate_pct'].min(), df_growth['growth_rate_pct'].max()]
    discount_range = [df_discount['discount_rate_pct'].min(), df_discount['discount_rate_pct'].max()]
    terminal_range = [df_terminal['terminal_growth_pct'].min(), df_terminal['terminal_growth_pct'].max()]
    param_ranges = [growth_range, discount_range, terminal_range]

    y_pos = np.arange(len(vars))
    bar_height = 0.35
    offset = 0.2

    # Plot FCFF bars (top position for each parameter)
    for i, (low_val, high_val) in enumerate(zip(fcff_low, fcff_high)):
        change_low = low_val - fcff_base
        change_high = high_val - fcff_base

        # Single bar showing full range from change_low to change_high
        bar_width = change_high - change_low
        ax4.barh(i + offset, bar_width, left=change_low, height=bar_height,
                color=fcff_color, alpha=0.7)

    # Plot FCFE bars (bottom position for each parameter)
    for i, (low_val, high_val) in enumerate(zip(fcfe_low, fcfe_high)):
        change_low = low_val - fcfe_base
        change_high = high_val - fcfe_base

        # Single bar showing full range from change_low to change_high
        bar_width = change_high - change_low
        ax4.barh(i - offset, bar_width, left=change_low, height=bar_height,
                color=fcfe_color, alpha=0.7)

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=fcff_color, alpha=0.7, label='FCFF'),
        Patch(facecolor=fcfe_color, alpha=0.7, label='FCFE'),
    ]

    ax4.set_yticks(y_pos)
    ax4.set_yticklabels(vars, fontsize=10)
    ax4.set_xlabel('Change in IVPS ($)', fontsize=11, fontweight='bold')
    ax4.set_title('Tornado Diagram (FCFF & FCFE)', fontsize=12, fontweight='bold')
    ax4.axvline(x=0, color=edge_color, linewidth=1.5)
    ax4.legend(handles=legend_elements, fontsize=9, loc='best')
    ax4.grid(axis='x', alpha=0.3, linewidth=0.6)

    fig.suptitle(f'{company_name} ({ticker}) - Sensitivity Analysis', fontsize=16, fontweight='bold', y=0.995)
    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    plt.close()


def _plot_specialized_sensitivity(data, output_file, csv_dir, dark_mode, model_type,
                                   file_prefixes, param_headers, param_labels,
                                   param_units, title_suffix):
    """Generic specialized sensitivity plot: 3 line panels + tornado.

    Parameters
    ----------
    file_prefixes : list of 3 str  – CSV file prefixes (e.g. 'sensitivity_bank_roe')
    param_headers : list of 3 str  – column name in CSV (e.g. 'roe_pct')
    param_labels  : list of 3 str  – axis labels (e.g. 'ROE (%)')
    param_units   : list of 3 str  – unit for tornado annotation (e.g. '%')
    title_suffix  : str            – e.g. 'Bank Sensitivity Analysis'
    """
    ticker = data['ticker']
    price = data['price']

    company_name = get_company_name(ticker)

    colors = KANAGAWA_DRAGON if dark_mode else KANAGAWA_LOTUS
    price_color = colors['red']
    fv_color = colors['cyan']
    edge_color = colors['fg']

    csv_dir = Path(csv_dir)

    # Load 3 CSV files
    dfs = []
    for prefix in file_prefixes:
        f = csv_dir / f"{prefix}_{ticker}.csv"
        if not f.exists():
            print(f"Warning: {f} not found for {ticker}, skipping", file=sys.stderr)
            return
        dfs.append(pd.read_csv(f))

    base_fv = data.get('fcfe_ivps', data.get('fair_value', price))

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    ((ax1, ax2), (ax3, ax4)) = axes

    # Plot 3 sensitivity curves
    for idx, (ax, df, header, label) in enumerate(zip(
            [ax1, ax2, ax3], dfs, param_headers, param_labels)):
        ax.axhline(y=price, color=price_color, linestyle='--', linewidth=2.0, label='Market Price')
        ax.plot(df[header], df['fair_value'], 'o-', color=fv_color, linewidth=2.0, markersize=6, label='Fair Value')

        # Find implied parameter where fair_value crosses market price
        fv_vals = df['fair_value'].values
        param_vals = df[header].values
        fv_min, fv_max = fv_vals.min(), fv_vals.max()
        increasing = fv_vals[-1] > fv_vals[0]

        # Determine if extrapolation is needed
        price_in_range = fv_min <= price <= fv_max
        if increasing:
            need_extrap_left = price < fv_min
            need_extrap_right = price > fv_max
        else:
            need_extrap_left = price > fv_max
            need_extrap_right = price < fv_min

        implied = None
        param_range = abs(param_vals[-1] - param_vals[0])
        try:
            if price_in_range:
                # Interpolate within range
                if increasing:
                    implied = np.interp(price, fv_vals, param_vals)
                else:
                    implied = np.interp(price, fv_vals[::-1], param_vals[::-1])
                ax.plot(implied, price, 'o', color=fv_color, markersize=10, zorder=5,
                        label=f'Implied: {implied:.1f}{param_units[idx]}')
            elif need_extrap_left:
                # Extrapolate using first two data points
                x1, x2 = fv_vals[0], fv_vals[1]
                y1, y2 = param_vals[0], param_vals[1]
                candidate = linear_extrapolate(price, x1, x2, y1, y2)
                # Cap: only extrapolate up to 0.75x the original parameter range
                if param_range > 0 and abs(candidate - param_vals[0]) <= 0.75 * param_range:
                    implied = candidate
                    param_step = abs(param_vals[1] - param_vals[0]) if len(param_vals) > 1 else 1.0
                    ext_params = np.linspace(implied - param_step * 0.5, y1, 10)
                    ext_fv = linear_extrapolate(ext_params, y1, y2, x1, x2)
                    ax.plot(ext_params, ext_fv, '--', color=fv_color, linewidth=1.5, alpha=0.7)
                    ax.plot(implied, price, 'o', color=fv_color, markersize=10, zorder=5,
                            label=f'Implied: {implied:.1f}{param_units[idx]}')
            elif need_extrap_right:
                # Extrapolate using last two data points
                x1, x2 = fv_vals[-2], fv_vals[-1]
                y1, y2 = param_vals[-2], param_vals[-1]
                candidate = linear_extrapolate(price, x1, x2, y1, y2)
                # Cap: only extrapolate up to 0.75x the original parameter range
                if param_range > 0 and abs(candidate - param_vals[-1]) <= 0.75 * param_range:
                    implied = candidate
                    param_step = abs(param_vals[-1] - param_vals[-2]) if len(param_vals) > 1 else 1.0
                    ext_params = np.linspace(y2, implied + param_step * 0.5, 10)
                    ext_fv = linear_extrapolate(ext_params, y1, y2, x1, x2)
                    ax.plot(ext_params, ext_fv, '--', color=fv_color, linewidth=1.5, alpha=0.7)
                    ax.plot(implied, price, 'o', color=fv_color, markersize=10, zorder=5,
                            label=f'Implied: {implied:.1f}{param_units[idx]}')

            # Extend axes to show the implied point
            if implied is not None:
                x_min, x_max = ax.get_xlim()
                margin = (x_max - x_min) * 0.05
                if implied < x_min:
                    ax.set_xlim(left=implied - margin)
                elif implied > x_max:
                    ax.set_xlim(right=implied + margin)
        except Exception:
            pass

        ax.set_xlabel(label, fontsize=11, fontweight='bold')
        ax.set_ylabel('Fair Value ($)', fontsize=11, fontweight='bold')
        ax.set_title(f'Sensitivity to {label}', fontsize=12, fontweight='bold')
        ax.legend(fontsize=9, loc='best')
        ax.grid(True, alpha=0.3, linewidth=0.6)

    # Tornado diagram
    tornado_labels = [l.replace(' (%)', '\n(%)').replace(' (', '\n(') for l in param_labels]
    fv_low = [df['fair_value'].min() for df in dfs]
    fv_high = [df['fair_value'].max() for df in dfs]

    y_pos = np.arange(len(tornado_labels))

    for i, (low_val, high_val) in enumerate(zip(fv_low, fv_high)):
        change_low = low_val - base_fv
        change_high = high_val - base_fv
        bar_width = change_high - change_low
        ax4.barh(i, bar_width, left=change_low, height=0.5, color=fv_color, alpha=0.7)

    ax4.set_yticks(y_pos)
    ax4.set_yticklabels(tornado_labels, fontsize=10)
    ax4.set_xlabel('Change in Fair Value ($)', fontsize=11, fontweight='bold')
    ax4.set_title('Tornado Diagram', fontsize=12, fontweight='bold')
    ax4.axvline(x=0, color=edge_color, linewidth=1.5)
    ax4.grid(axis='x', alpha=0.3, linewidth=0.6)

    fig.suptitle(f'{company_name} ({ticker}) - {title_suffix}', fontsize=16, fontweight='bold', y=0.995)
    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    plt.close()


def plot_bank_sensitivity(data, output_file, csv_dir, dark_mode=False):
    """Bank sensitivity: ROE, Cost of Equity, Growth."""
    _plot_specialized_sensitivity(
        data, output_file, csv_dir, dark_mode, 'bank',
        file_prefixes=['sensitivity_bank_roe', 'sensitivity_bank_coe', 'sensitivity_bank_growth'],
        param_headers=['roe_pct', 'cost_of_equity_pct', 'growth_rate_pct'],
        param_labels=['ROE (%)', 'Cost of Equity (%)', 'Sustainable Growth (%)'],
        param_units=['%', '%', '%'],
        title_suffix='Bank Sensitivity Analysis',
    )


def plot_insurance_sensitivity(data, output_file, csv_dir, dark_mode=False):
    """Insurance sensitivity: Combined Ratio, Investment Yield, Cost of Equity."""
    _plot_specialized_sensitivity(
        data, output_file, csv_dir, dark_mode, 'insurance',
        file_prefixes=['sensitivity_insurance_cr', 'sensitivity_insurance_yield', 'sensitivity_insurance_coe'],
        param_headers=['combined_ratio_pct', 'investment_yield_pct', 'cost_of_equity_pct'],
        param_labels=['Combined Ratio (%)', 'Investment Yield (%)', 'Cost of Equity (%)'],
        param_units=['%', '%', '%'],
        title_suffix='Insurance Sensitivity Analysis',
    )


def plot_oil_gas_sensitivity(data, output_file, csv_dir, dark_mode=False):
    """Oil & Gas sensitivity: Oil Price, Lifting Cost, Discount Rate."""
    _plot_specialized_sensitivity(
        data, output_file, csv_dir, dark_mode, 'oil_gas',
        file_prefixes=['sensitivity_oilgas_price', 'sensitivity_oilgas_lifting', 'sensitivity_oilgas_discount'],
        param_headers=['oil_price_usd', 'lifting_cost_usd', 'discount_rate_pct'],
        param_labels=['Oil Price ($/bbl)', 'Lifting Cost ($/BOE)', 'Discount Rate (%)'],
        param_units=['', '', '%'],
        title_suffix='Oil & Gas Sensitivity Analysis',
    )


def _generate_specialized_sensitivity_plot(args):
    """Wrapper for parallel specialized sensitivity plot generation."""
    data, output_file, csv_dir, dark_mode, plot_func = args
    if dark_mode:
        setup_dark_mode()
    else:
        setup_light_mode()
    return plot_func(data, output_file, csv_dir, dark_mode)


def plot_comparison_consolidated(all_data, output_file, dark_mode=False):
    """Generate consolidated comparison chart showing surplus/discount for all tickers (FCFF top, FCFE bottom, vertically stacked with shared x-axis)."""
    n_tickers = len(all_data)

    # Set colors based on mode
    if dark_mode:
        green_color = KANAGAWA_DRAGON['green']
        red_color = KANAGAWA_DRAGON['red']
        edge_color = KANAGAWA_DRAGON['fg']
        text_color = KANAGAWA_DRAGON['fg']
    else:
        green_color = KANAGAWA_LOTUS['green']
        red_color = KANAGAWA_LOTUS['red']
        edge_color = KANAGAWA_LOTUS['fg']
        text_color = KANAGAWA_LOTUS['fg']

    # Sort tickers independently by surplus (most undervalued at top)
    sorted_data_fcff = sorted(all_data, key=lambda x: (x['fcff_ivps'] - x['price']) / x['price'] if x['price'] > 0 else 0, reverse=False)
    sorted_data_fcfe = sorted(all_data, key=lambda x: (x['fcfe_ivps'] - x['price']) / x['price'] if x['price'] > 0 else 0, reverse=False)

    # Create vertically stacked subplots with shared x-axis
    fig, (ax_fcff, ax_fcfe) = plt.subplots(2, 1, figsize=(14, max(12, n_tickers * 1.0)), sharex=True)

    # FCFF Comparison (top)
    tickers_fcff = []
    surplus_pct_fcff = []

    for data in sorted_data_fcff:
        ticker = data['ticker']
        price = data['price']
        ivps = data['fcff_ivps']

        if price > 0:
            pct = ((ivps - price) / price) * 100
        else:
            pct = 0

        tickers_fcff.append(ticker)
        surplus_pct_fcff.append(pct)

    y_pos_fcff = np.arange(len(tickers_fcff))

    # Plot with color based on sign
    bars_fcff = ax_fcff.barh(y_pos_fcff, surplus_pct_fcff, height=0.6, edgecolor=edge_color, linewidth=1)

    # Color bars based on positive/negative
    for i, pct in enumerate(surplus_pct_fcff):
        if pct >= 0:
            bars_fcff[i].set_color(green_color)
        else:
            bars_fcff[i].set_color(red_color)

    # Add value labels - inside bar if long enough, outside if too short
    for i, pct in enumerate(surplus_pct_fcff):
        label = f'{pct:+.1f}%'

        # Threshold for placing label inside (in percentage points)
        threshold = 5

        if abs(pct) > threshold:
            # Bar is long enough - place label inside
            x_pos = pct / 2
            ha = 'center'
            color = 'white'
        else:
            # Bar is too short - place label outside
            x_pos = pct + (2 if pct > 0 else -2)
            ha = 'left' if pct > 0 else 'right'
            color = 'black'

        ax_fcff.text(x_pos, i, label, va='center', ha=ha, fontsize=9,
                    fontweight='bold', color=color)

    # Formatting for FCFF
    ax_fcff.axvline(x=0, color=edge_color, linestyle='-', linewidth=2)
    ax_fcff.set_yticks(y_pos_fcff)
    ax_fcff.set_yticklabels(tickers_fcff, fontsize=10)
    ax_fcff.set_title('FCFF Valuation Comparison', fontsize=13, fontweight='bold', pad=15)
    ax_fcff.grid(axis='x', alpha=0.3, linestyle='--')
    ax_fcff.set_xscale('symlog', linthresh=1.0)

    # Add shaded regions
    xlim_fcff = ax_fcff.get_xlim()
    ax_fcff.axvspan(0, xlim_fcff[1], alpha=0.05, color='green', zorder=0)
    ax_fcff.axvspan(xlim_fcff[0], 0, alpha=0.05, color='red', zorder=0)

    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=green_color, edgecolor=edge_color, label='Undervalued'),
        Patch(facecolor=red_color, edgecolor=edge_color, label='Overvalued'),
    ]
    ax_fcff.legend(handles=legend_elements, loc='lower right', fontsize=9, framealpha=0.9)

    # FCFE Comparison (bottom)
    tickers_fcfe = []
    surplus_pct_fcfe = []

    for data in sorted_data_fcfe:
        ticker = data['ticker']
        price = data['price']
        ivps = data['fcfe_ivps']

        if price > 0:
            pct = ((ivps - price) / price) * 100
        else:
            pct = 0

        tickers_fcfe.append(ticker)
        surplus_pct_fcfe.append(pct)

    y_pos_fcfe = np.arange(len(tickers_fcfe))

    # Plot with color based on sign
    bars_fcfe = ax_fcfe.barh(y_pos_fcfe, surplus_pct_fcfe, height=0.6, edgecolor=edge_color, linewidth=1)

    # Color bars based on positive/negative
    for i, pct in enumerate(surplus_pct_fcfe):
        if pct >= 0:
            bars_fcfe[i].set_color(green_color)
        else:
            bars_fcfe[i].set_color(red_color)

    # Add value labels - inside bar if long enough, outside if too short
    for i, pct in enumerate(surplus_pct_fcfe):
        label = f'{pct:+.1f}%'

        # Threshold for placing label inside (in percentage points)
        threshold = 5

        if abs(pct) > threshold:
            # Bar is long enough - place label inside
            x_pos = pct / 2
            ha = 'center'
            color = 'white'
        else:
            # Bar is too short - place label outside
            x_pos = pct + (2 if pct > 0 else -2)
            ha = 'left' if pct > 0 else 'right'
            color = 'black'

        ax_fcfe.text(x_pos, i, label, va='center', ha=ha, fontsize=9,
                    fontweight='bold', color=color)

    # Formatting for FCFE
    ax_fcfe.axvline(x=0, color=edge_color, linestyle='-', linewidth=2)
    ax_fcfe.set_yticks(y_pos_fcfe)
    ax_fcfe.set_yticklabels(tickers_fcfe, fontsize=10)
    ax_fcfe.set_xlabel('Surplus / Discount (%, log scale)', fontsize=12, fontweight='bold')
    ax_fcfe.set_title('FCFE Valuation Comparison', fontsize=13, fontweight='bold', pad=15)
    ax_fcfe.grid(axis='x', alpha=0.3, linestyle='--')
    ax_fcfe.set_xscale('symlog', linthresh=1.0)

    # Add shaded regions
    xlim_fcfe = ax_fcfe.get_xlim()
    ax_fcfe.axvspan(0, xlim_fcfe[1], alpha=0.05, color='green', zorder=0)
    ax_fcfe.axvspan(xlim_fcfe[0], 0, alpha=0.05, color='red', zorder=0)

    # Add legend
    ax_fcfe.legend(handles=legend_elements, loc='lower right', fontsize=9, framealpha=0.9)

    # Overall title
    fig.suptitle('DCF Valuation Comparison - All Tickers', fontsize=16, fontweight='bold', y=0.98)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    save_figure(fig, output_file, dpi=300)
    plt.close()


def plot_bank_comparison(bank_data, output_file, dark_mode=False):
    """Generate bank-specific comparison chart showing Excess Return Model metrics."""
    if not bank_data:
        print("No bank data to plot")
        return

    n_banks = len(bank_data)

    # Set colors based on mode
    if dark_mode:
        green_color = KANAGAWA_DRAGON['green']
        red_color = KANAGAWA_DRAGON['red']
        blue_color = KANAGAWA_DRAGON['blue']
        yellow_color = KANAGAWA_DRAGON['yellow']
        edge_color = KANAGAWA_DRAGON['fg']
        text_color = KANAGAWA_DRAGON['fg']
        bg_color = KANAGAWA_DRAGON['bg']
    else:
        green_color = KANAGAWA_LOTUS['green']
        red_color = KANAGAWA_LOTUS['red']
        blue_color = KANAGAWA_LOTUS['blue']
        yellow_color = KANAGAWA_LOTUS['yellow']
        edge_color = KANAGAWA_LOTUS['fg']
        text_color = KANAGAWA_LOTUS['fg']
        bg_color = KANAGAWA_LOTUS['bg']

    # Create 2x2 subplot layout
    fig, axes = plt.subplots(2, 2, figsize=(14, max(10, n_banks * 2.5)))
    ax_mos, ax_roe, ax_pbv, ax_summary = axes.flatten()

    # Sort by margin of safety (most undervalued first)
    sorted_data = sorted(bank_data, key=lambda x: (x['fcfe_ivps'] - x['price']) / x['price'] if x['price'] > 0 else 0, reverse=False)

    tickers = [d['ticker'] for d in sorted_data]
    y_pos = np.arange(len(tickers))

    # 1. Margin of Safety (Fair Value vs Price)
    margins = []
    for data in sorted_data:
        price = data['price']
        fair_value = data['fcfe_ivps']
        margin = ((fair_value - price) / price * 100) if price > 0 else 0
        margins.append(margin)

    bars_mos = ax_mos.barh(y_pos, margins, height=0.6, edgecolor=edge_color, linewidth=1)
    for i, margin in enumerate(margins):
        bars_mos[i].set_color(green_color if margin >= 0 else red_color)
        label = f'{margin:+.1f}%'
        if abs(margin) > 5:
            x_pos = margin * 0.9 if margin >= 0 else margin * 0.9
            ha = 'right' if margin >= 0 else 'left'
            color = 'white'
        else:
            x_pos = margin + (2 if margin >= 0 else -2)
            ha = 'left' if margin >= 0 else 'right'
            color = text_color
        ax_mos.text(x_pos, i, label, va='center', ha=ha, fontsize=10, fontweight='bold', color=color)

    ax_mos.axvline(x=0, color=edge_color, linestyle='-', linewidth=2)
    ax_mos.set_yticks(y_pos)
    ax_mos.set_yticklabels(tickers, fontsize=11)
    ax_mos.set_xlabel('Margin of Safety (%)', fontsize=11, fontweight='bold')
    ax_mos.set_title('Fair Value vs Market Price', fontsize=12, fontweight='bold')
    ax_mos.grid(axis='x', alpha=0.3, linestyle='--')

    # 2. ROE vs Cost of Equity (Value Creation Spread)
    roe_spreads = []
    for data in sorted_data:
        roe = data.get('roe', 0)
        ce = data.get('ce', 0)
        spread = roe - ce
        roe_spreads.append(spread)

    bars_roe = ax_roe.barh(y_pos, roe_spreads, height=0.6, edgecolor=edge_color, linewidth=1)
    for i, spread in enumerate(roe_spreads):
        bars_roe[i].set_color(green_color if spread >= 0 else red_color)
        label = f'{spread:+.1f}%'
        if abs(spread) > 1:
            x_pos = spread * 0.9 if spread >= 0 else spread * 0.9
            ha = 'right' if spread >= 0 else 'left'
            color = 'white'
        else:
            x_pos = spread + (0.5 if spread >= 0 else -0.5)
            ha = 'left' if spread >= 0 else 'right'
            color = text_color
        ax_roe.text(x_pos, i, label, va='center', ha=ha, fontsize=10, fontweight='bold', color=color)

    ax_roe.axvline(x=0, color=edge_color, linestyle='-', linewidth=2)
    ax_roe.set_yticks(y_pos)
    ax_roe.set_yticklabels(tickers, fontsize=11)
    ax_roe.set_xlabel('ROE - Cost of Equity (%)', fontsize=11, fontweight='bold')
    ax_roe.set_title('Value Creation Spread (ROE − CoE)', fontsize=12, fontweight='bold')
    ax_roe.grid(axis='x', alpha=0.3, linestyle='--')

    # 3. Price-to-Book Ratio
    pbv_ratios = [d.get('price_to_book', 0) for d in sorted_data]
    bars_pbv = ax_pbv.barh(y_pos, pbv_ratios, height=0.6, color=blue_color, edgecolor=edge_color, linewidth=1)

    # Add reference line at P/BV = 1.0
    ax_pbv.axvline(x=1.0, color=yellow_color, linestyle='--', linewidth=2, label='Book Value')

    for i, pbv in enumerate(pbv_ratios):
        label = f'{pbv:.2f}x'
        if pbv > 0.5:
            ax_pbv.text(pbv * 0.9, i, label, va='center', ha='right', fontsize=10, fontweight='bold', color='white')
        else:
            ax_pbv.text(pbv + 0.05, i, label, va='center', ha='left', fontsize=10, fontweight='bold', color=text_color)

    ax_pbv.set_yticks(y_pos)
    ax_pbv.set_yticklabels(tickers, fontsize=11)
    ax_pbv.set_xlabel('Price / Book Value', fontsize=11, fontweight='bold')
    ax_pbv.set_title('Price-to-Book Ratio', fontsize=12, fontweight='bold')
    ax_pbv.grid(axis='x', alpha=0.3, linestyle='--')
    ax_pbv.legend(loc='lower right', fontsize=9)

    # 4. Summary Table
    ax_summary.axis('off')

    # Create summary table data
    table_data = []
    headers = ['Ticker', 'Price', 'Fair Value', 'MoS', 'ROE', 'CoE', 'P/BV']

    for data in sorted_data:
        price = data['price']
        fair_value = data['fcfe_ivps']
        margin = ((fair_value - price) / price * 100) if price > 0 else 0
        roe = data.get('roe', 0)
        ce = data.get('ce', 0)
        pbv = data.get('price_to_book', 0)

        row = [
            data['ticker'],
            f'${price:.2f}',
            f'${fair_value:.2f}',
            f'{margin:+.1f}%',
            f'{roe:.1f}%',
            f'{ce:.1f}%',
            f'{pbv:.2f}x'
        ]
        table_data.append(row)

    table = ax_summary.table(
        cellText=table_data,
        colLabels=headers,
        cellLoc='center',
        loc='center',
        colColours=[blue_color] * len(headers)
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.8)

    # Style all cells with dark background
    for row_idx in range(len(sorted_data) + 1):
        for col_idx in range(len(headers)):
            cell = table[(row_idx, col_idx)]
            if row_idx == 0:
                cell.set_text_props(fontweight='bold', color='white')
            else:
                cell.set_facecolor(bg_color)
                cell.set_text_props(color=text_color)
                cell.set_edgecolor(edge_color)

    # Color margin of safety cells
    for row_idx, data in enumerate(sorted_data):
        price = data['price']
        fair_value = data['fcfe_ivps']
        margin = ((fair_value - price) / price * 100) if price > 0 else 0
        cell = table[(row_idx + 1, 3)]
        if margin >= 0:
            cell.set_facecolor(green_color)
            cell.set_text_props(color='white', fontweight='bold')
        else:
            cell.set_facecolor(red_color)
            cell.set_text_props(color='white', fontweight='bold')

    ax_summary.set_title('Bank Valuation Summary', fontsize=12, fontweight='bold', pad=20)

    # Overall title
    fig.suptitle('Bank Valuation Comparison - Excess Return Model', fontsize=16, fontweight='bold', y=0.98)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    save_figure(fig, output_file, dpi=300)
    plt.close()


def plot_insurance_comparison(insurance_data, output_file, dark_mode=False):
    """Generate insurance-specific comparison chart showing Float-Based Model metrics."""
    if not insurance_data:
        print("No insurance data to plot")
        return

    n_insurers = len(insurance_data)

    # Set colors based on mode
    if dark_mode:
        green_color = KANAGAWA_DRAGON['green']
        red_color = KANAGAWA_DRAGON['red']
        blue_color = KANAGAWA_DRAGON['blue']
        yellow_color = KANAGAWA_DRAGON['yellow']
        cyan_color = KANAGAWA_DRAGON['cyan']
        edge_color = KANAGAWA_DRAGON['fg']
        text_color = KANAGAWA_DRAGON['fg']
        bg_color = KANAGAWA_DRAGON['bg']
    else:
        green_color = KANAGAWA_LOTUS['green']
        red_color = KANAGAWA_LOTUS['red']
        blue_color = KANAGAWA_LOTUS['blue']
        yellow_color = KANAGAWA_LOTUS['yellow']
        cyan_color = KANAGAWA_LOTUS['cyan']
        edge_color = KANAGAWA_LOTUS['fg']
        text_color = KANAGAWA_LOTUS['fg']
        bg_color = KANAGAWA_LOTUS['bg']

    # Create 2x2 subplot layout
    fig, axes = plt.subplots(2, 2, figsize=(14, max(10, n_insurers * 2.5)))
    ax_mos, ax_cr, ax_pbv, ax_summary = axes.flatten()

    # Sort by margin of safety (most undervalued first)
    sorted_data = sorted(insurance_data, key=lambda x: (x['fcfe_ivps'] - x['price']) / x['price'] if x['price'] > 0 else 0, reverse=False)

    tickers = [d['ticker'] for d in sorted_data]
    y_pos = np.arange(len(tickers))

    # 1. Margin of Safety (Fair Value vs Price)
    margins = []
    for data in sorted_data:
        price = data['price']
        fair_value = data['fcfe_ivps']
        margin = ((fair_value - price) / price * 100) if price > 0 else 0
        margins.append(margin)

    bars_mos = ax_mos.barh(y_pos, margins, height=0.6, edgecolor=edge_color, linewidth=1)
    for i, margin in enumerate(margins):
        bars_mos[i].set_color(green_color if margin >= 0 else red_color)
        label = f'{margin:+.1f}%'
        if abs(margin) > 5:
            x_pos = margin * 0.9
            ha = 'right' if margin >= 0 else 'left'
            color = 'white'
        else:
            x_pos = margin + (2 if margin >= 0 else -2)
            ha = 'left' if margin >= 0 else 'right'
            color = text_color
        ax_mos.text(x_pos, i, label, va='center', ha=ha, fontsize=10, fontweight='bold', color=color)

    ax_mos.axvline(x=0, color=edge_color, linestyle='-', linewidth=2)
    ax_mos.set_yticks(y_pos)
    ax_mos.set_yticklabels(tickers, fontsize=11)
    ax_mos.set_xlabel('Margin of Safety (%)', fontsize=11, fontweight='bold')
    ax_mos.set_title('Fair Value vs Market Price', fontsize=12, fontweight='bold')
    ax_mos.grid(axis='x', alpha=0.3, linestyle='--')

    # 2. Combined Ratio (Underwriting Profitability)
    combined_ratios = [d.get('combined_ratio', 0) for d in sorted_data]
    bars_cr = ax_cr.barh(y_pos, combined_ratios, height=0.6, edgecolor=edge_color, linewidth=1)

    # Color by profitability (< 100% is profitable)
    for i, cr in enumerate(combined_ratios):
        bars_cr[i].set_color(green_color if cr < 100 else red_color)
        label = f'{cr:.1f}%'
        if cr > 20:
            ax_cr.text(cr * 0.9, i, label, va='center', ha='right', fontsize=10, fontweight='bold', color='white')
        else:
            ax_cr.text(cr + 1, i, label, va='center', ha='left', fontsize=10, fontweight='bold', color=text_color)

    # Add reference line at 100% (break-even)
    ax_cr.axvline(x=100, color=yellow_color, linestyle='--', linewidth=2, label='Break-even (100%)')

    ax_cr.set_yticks(y_pos)
    ax_cr.set_yticklabels(tickers, fontsize=11)
    ax_cr.set_xlabel('Combined Ratio (%)', fontsize=11, fontweight='bold')
    ax_cr.set_title('Underwriting Profitability', fontsize=12, fontweight='bold')
    ax_cr.grid(axis='x', alpha=0.3, linestyle='--')
    ax_cr.legend(loc='lower right', fontsize=9)

    # 3. Price-to-Book Ratio
    pbv_ratios = [d.get('price_to_book', 0) for d in sorted_data]
    bars_pbv = ax_pbv.barh(y_pos, pbv_ratios, height=0.6, color=blue_color, edgecolor=edge_color, linewidth=1)

    # Add reference line at P/BV = 1.0
    ax_pbv.axvline(x=1.0, color=yellow_color, linestyle='--', linewidth=2, label='Book Value')

    for i, pbv in enumerate(pbv_ratios):
        label = f'{pbv:.2f}x'
        if pbv > 0.5:
            ax_pbv.text(pbv * 0.9, i, label, va='center', ha='right', fontsize=10, fontweight='bold', color='white')
        else:
            ax_pbv.text(pbv + 0.05, i, label, va='center', ha='left', fontsize=10, fontweight='bold', color=text_color)

    ax_pbv.set_yticks(y_pos)
    ax_pbv.set_yticklabels(tickers, fontsize=11)
    ax_pbv.set_xlabel('Price / Book Value', fontsize=11, fontweight='bold')
    ax_pbv.set_title('Price-to-Book Ratio', fontsize=12, fontweight='bold')
    ax_pbv.grid(axis='x', alpha=0.3, linestyle='--')
    ax_pbv.legend(loc='lower right', fontsize=9)

    # 4. Summary Table
    ax_summary.axis('off')

    # Create summary table data
    table_data = []
    headers = ['Ticker', 'Price', 'Fair Value', 'MoS', 'CR', 'ROE', 'P/BV']

    for data in sorted_data:
        price = data['price']
        fair_value = data['fcfe_ivps']
        margin = ((fair_value - price) / price * 100) if price > 0 else 0
        cr = data.get('combined_ratio', 0)
        roe = data.get('roe', 0)
        pbv = data.get('price_to_book', 0)

        row = [
            data['ticker'],
            f'${price:.2f}',
            f'${fair_value:.2f}',
            f'{margin:+.1f}%',
            f'{cr:.1f}%',
            f'{roe:.1f}%',
            f'{pbv:.2f}x'
        ]
        table_data.append(row)

    table = ax_summary.table(
        cellText=table_data,
        colLabels=headers,
        cellLoc='center',
        loc='center',
        colColours=[cyan_color] * len(headers)
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.8)

    # Style all cells with dark background
    for row_idx in range(len(sorted_data) + 1):
        for col_idx in range(len(headers)):
            cell = table[(row_idx, col_idx)]
            if row_idx == 0:
                cell.set_text_props(fontweight='bold', color='white')
            else:
                cell.set_facecolor(bg_color)
                cell.set_text_props(color=text_color)
                cell.set_edgecolor(edge_color)

    # Color margin of safety cells
    for row_idx, data in enumerate(sorted_data):
        price = data['price']
        fair_value = data['fcfe_ivps']
        margin = ((fair_value - price) / price * 100) if price > 0 else 0
        cell = table[(row_idx + 1, 3)]
        if margin >= 0:
            cell.set_facecolor(green_color)
            cell.set_text_props(color='white', fontweight='bold')
        else:
            cell.set_facecolor(red_color)
            cell.set_text_props(color='white', fontweight='bold')

    # Color combined ratio cells
    for row_idx, data in enumerate(sorted_data):
        cr = data.get('combined_ratio', 0)
        cell = table[(row_idx + 1, 4)]
        if cr < 100:
            cell.set_facecolor(green_color)
            cell.set_text_props(color='white', fontweight='bold')
        else:
            cell.set_facecolor(red_color)
            cell.set_text_props(color='white', fontweight='bold')

    ax_summary.set_title('Insurance Valuation Summary', fontsize=12, fontweight='bold', pad=20)

    # Overall title
    fig.suptitle('Insurance Valuation Comparison - Float-Based Model', fontsize=16, fontweight='bold', y=0.98)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    save_figure(fig, output_file, dpi=300)
    plt.close()


def plot_oil_gas_comparison(og_data, output_file, dark_mode=False):
    """Generate O&G E&P-specific comparison chart showing NAV Model metrics."""
    if not og_data:
        print("No O&G data to plot")
        return

    n_companies = len(og_data)

    # Set colors based on mode
    if dark_mode:
        green_color = KANAGAWA_DRAGON['green']
        red_color = KANAGAWA_DRAGON['red']
        blue_color = KANAGAWA_DRAGON['blue']
        yellow_color = KANAGAWA_DRAGON['yellow']
        cyan_color = KANAGAWA_DRAGON['cyan']
        edge_color = KANAGAWA_DRAGON['fg']
        text_color = KANAGAWA_DRAGON['fg']
        bg_color = KANAGAWA_DRAGON['bg']
    else:
        green_color = KANAGAWA_LOTUS['green']
        red_color = KANAGAWA_LOTUS['red']
        blue_color = KANAGAWA_LOTUS['blue']
        yellow_color = KANAGAWA_LOTUS['yellow']
        cyan_color = KANAGAWA_LOTUS['cyan']
        edge_color = KANAGAWA_LOTUS['fg']
        text_color = KANAGAWA_LOTUS['fg']
        bg_color = KANAGAWA_LOTUS['bg']

    # Create 2x2 subplot layout
    fig, axes = plt.subplots(2, 2, figsize=(14, max(10, n_companies * 2.5)))
    ax_mos, ax_leverage, ax_netback, ax_summary = axes.flatten()

    # Sort by margin of safety (most undervalued first)
    sorted_data = sorted(og_data, key=lambda x: (x['fcfe_ivps'] - x['price']) / x['price'] if x['price'] > 0 else 0, reverse=False)

    tickers = [d['ticker'] for d in sorted_data]
    y_pos = np.arange(len(tickers))

    # 1. Margin of Safety (NAV vs Price)
    margins = []
    for data in sorted_data:
        price = data['price']
        fair_value = data['fcfe_ivps']
        margin = ((fair_value - price) / price * 100) if price > 0 else 0
        margins.append(margin)

    bars_mos = ax_mos.barh(y_pos, margins, height=0.6, edgecolor=edge_color, linewidth=1)
    for i, margin in enumerate(margins):
        bars_mos[i].set_color(green_color if margin >= 0 else red_color)
        label = f'{margin:+.1f}%'
        if abs(margin) > 5:
            x_pos = margin * 0.9
            ha = 'right' if margin >= 0 else 'left'
            color = 'white'
        else:
            x_pos = margin + (2 if margin >= 0 else -2)
            ha = 'left' if margin >= 0 else 'right'
            color = text_color
        ax_mos.text(x_pos, i, label, va='center', ha=ha, fontsize=10, fontweight='bold', color=color)

    ax_mos.axvline(x=0, color=edge_color, linestyle='-', linewidth=2)
    ax_mos.set_yticks(y_pos)
    ax_mos.set_yticklabels(tickers, fontsize=11)
    ax_mos.set_xlabel('Margin of Safety (%)', fontsize=11, fontweight='bold')
    ax_mos.set_title('NAV vs Market Price', fontsize=12, fontweight='bold')
    ax_mos.grid(axis='x', alpha=0.3, linestyle='--')

    # 2. Debt/EBITDAX (Leverage)
    leverage = [d.get('debt_to_ebitdax', 0) for d in sorted_data]
    bars_lev = ax_leverage.barh(y_pos, leverage, height=0.6, edgecolor=edge_color, linewidth=1)

    # Color by leverage level (< 2x is healthy, > 3x is concerning)
    for i, lev in enumerate(leverage):
        if lev < 2.0:
            bars_lev[i].set_color(green_color)
        elif lev < 3.0:
            bars_lev[i].set_color(yellow_color)
        else:
            bars_lev[i].set_color(red_color)
        label = f'{lev:.1f}x'
        if lev > 0.5:
            ax_leverage.text(lev * 0.9, i, label, va='center', ha='right', fontsize=10, fontweight='bold', color='white')
        else:
            ax_leverage.text(lev + 0.1, i, label, va='center', ha='left', fontsize=10, fontweight='bold', color=text_color)

    # Add reference lines
    ax_leverage.axvline(x=2.0, color=yellow_color, linestyle='--', linewidth=2, label='2.0x (Moderate)')
    ax_leverage.axvline(x=3.0, color=red_color, linestyle='--', linewidth=2, label='3.0x (High)')

    ax_leverage.set_yticks(y_pos)
    ax_leverage.set_yticklabels(tickers, fontsize=11)
    ax_leverage.set_xlabel('Debt / EBITDAX', fontsize=11, fontweight='bold')
    ax_leverage.set_title('Leverage (Debt/EBITDAX)', fontsize=12, fontweight='bold')
    ax_leverage.grid(axis='x', alpha=0.3, linestyle='--')
    ax_leverage.legend(loc='lower right', fontsize=9)

    # 3. Netback ($/BOE profitability)
    netbacks = [d.get('netback', 0) for d in sorted_data]
    bars_nb = ax_netback.barh(y_pos, netbacks, height=0.6, color=cyan_color, edgecolor=edge_color, linewidth=1)

    for i, nb in enumerate(netbacks):
        bars_nb[i].set_color(green_color if nb > 0 else red_color)
        label = f'${nb:.2f}'
        if abs(nb) > 5:
            x_pos = nb * 0.9
            ha = 'right' if nb >= 0 else 'left'
            ax_netback.text(x_pos, i, label, va='center', ha=ha, fontsize=10, fontweight='bold', color='white')
        else:
            ax_netback.text(nb + 1, i, label, va='center', ha='left', fontsize=10, fontweight='bold', color=text_color)

    ax_netback.axvline(x=0, color=edge_color, linestyle='-', linewidth=2)
    ax_netback.set_yticks(y_pos)
    ax_netback.set_yticklabels(tickers, fontsize=11)
    ax_netback.set_xlabel('Netback ($/BOE)', fontsize=11, fontweight='bold')
    ax_netback.set_title('Operating Profitability', fontsize=12, fontweight='bold')
    ax_netback.grid(axis='x', alpha=0.3, linestyle='--')

    # 4. Summary Table
    ax_summary.axis('off')

    # Create summary table data
    table_data = []
    headers = ['Ticker', 'Price', 'NAV', 'MoS', 'D/EBITDAX', 'Netback', 'Reserves']

    for data in sorted_data:
        price = data['price']
        fair_value = data['fcfe_ivps']
        margin = ((fair_value - price) / price * 100) if price > 0 else 0
        leverage = data.get('debt_to_ebitdax', 0)
        netback = data.get('netback', 0)
        reserve_life = data.get('reserve_life', 0)

        row = [
            data['ticker'],
            f'${price:.2f}',
            f'${fair_value:.2f}',
            f'{margin:+.1f}%',
            f'{leverage:.1f}x',
            f'${netback:.2f}',
            f'{reserve_life:.1f}y'
        ]
        table_data.append(row)

    table = ax_summary.table(
        cellText=table_data,
        colLabels=headers,
        cellLoc='center',
        loc='center',
        colColours=[blue_color] * len(headers)
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.8)

    # Style all cells with dark background
    for row_idx in range(len(sorted_data) + 1):
        for col_idx in range(len(headers)):
            cell = table[(row_idx, col_idx)]
            if row_idx == 0:
                cell.set_text_props(fontweight='bold', color='white')
            else:
                cell.set_facecolor(bg_color)
                cell.set_text_props(color=text_color)
                cell.set_edgecolor(edge_color)

    # Color margin of safety cells
    for row_idx, data in enumerate(sorted_data):
        price = data['price']
        fair_value = data['fcfe_ivps']
        margin = ((fair_value - price) / price * 100) if price > 0 else 0
        cell = table[(row_idx + 1, 3)]
        if margin >= 0:
            cell.set_facecolor(green_color)
            cell.set_text_props(color='white', fontweight='bold')
        else:
            cell.set_facecolor(red_color)
            cell.set_text_props(color='white', fontweight='bold')

    # Color leverage cells
    for row_idx, data in enumerate(sorted_data):
        lev = data.get('debt_to_ebitdax', 0)
        cell = table[(row_idx + 1, 4)]
        if lev < 2.0:
            cell.set_facecolor(green_color)
            cell.set_text_props(color='white', fontweight='bold')
        elif lev >= 3.0:
            cell.set_facecolor(red_color)
            cell.set_text_props(color='white', fontweight='bold')

    ax_summary.set_title('O&G E&P Valuation Summary', fontsize=12, fontweight='bold', pad=20)

    # Overall title
    fig.suptitle('Oil & Gas E&P Valuation Comparison - NAV Model', fontsize=16, fontweight='bold', y=0.98)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    save_figure(fig, output_file, dpi=300)
    plt.close()


def plot_cost_of_capital(data, output_file):
    """Generate cost of capital breakdown visualization."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    ticker = data['ticker']
    ce = data['ce']
    wacc = data['wacc']
    cb = data['cb']
    beta = data['beta']

    # Assuming typical market components (would need to extract from log for exact values)
    rfr = 4.0  # Approximate
    erp = 6.0  # Approximate
    beta_contrib = beta * erp

    # 1. Cost of Equity breakdown (waterfall style with connectors)
    categories = ['Risk-Free\nRate', 'Beta ×\nERP', 'Cost of\nEquity']
    values = [rfr, beta_contrib, 0]
    cumulative = [rfr, rfr + beta_contrib, ce]
    colors = ['#4472C4', '#70AD47', '#FFC000']

    for i, (cat, val, cum) in enumerate(zip(categories, values, cumulative)):
        if val != 0:
            ax1.bar(i, val, bottom=cum - val, color=colors[i], edgecolor='black', linewidth=1.5, width=0.6)
        else:
            ax1.bar(i, cum, color=colors[i], edgecolor='black', linewidth=1.5, width=0.6)

        # Position labels with sufficient offset to avoid overlap
        label_offset = max(ce * 0.04, 0.5)  # Minimum 0.5% offset
        ax1.text(i, cum + label_offset, f'{cum:.2f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')

    # Add connector lines for waterfall effect
    for i in range(len(categories) - 1):
        ax1.plot([i + 0.3, i + 0.7], [cumulative[i], cumulative[i]],
                color='gray', linestyle='--', linewidth=1, alpha=0.6)

    ax1.set_xticks(range(len(categories)))
    ax1.set_xticklabels(categories, fontsize=11)
    ax1.set_ylabel('Rate (%)', fontsize=12, fontweight='bold')
    ax1.set_title('Cost of Equity Breakdown', fontsize=13, fontweight='bold')
    ax1.grid(axis='y', alpha=0.3)
    ax1.set_ylim(0, ce * 1.35)  # Increased to accommodate labels above bars

    # 2. WACC composition pie chart
    # Assuming 80/20 equity/debt split (would need to extract from actual calculation)
    equity_weight = 0.8
    debt_weight = 0.2

    equity_contribution = ce * equity_weight
    debt_contribution = cb * debt_weight * 0.79  # After-tax (assuming 21% tax)

    labels = [f'Equity\n{equity_contribution:.2f}%', f'Debt\n(after-tax)\n{debt_contribution:.2f}%']
    sizes = [equity_contribution, debt_contribution]
    colors_pie = ['#70AD47', '#4472C4']

    wedges, texts, autotexts = ax2.pie(sizes, labels=labels, colors=colors_pie,
                                        autopct='%1.0f%%', startangle=90,
                                        textprops={'fontsize': 9},
                                        pctdistance=0.75,  # Position percentage labels closer to center
                                        labeldistance=1.15,  # Position slice labels further out
                                        wedgeprops={'edgecolor': 'black', 'linewidth': 1.5})

    # Make percentage text bold
    for autotext in autotexts:
        autotext.set_fontweight('bold')
        autotext.set_fontsize(10)

    # Ensure equal aspect ratio so pie is circular
    ax2.axis('equal')
    ax2.set_title(f'WACC Composition = {wacc:.2f}%', fontsize=13, fontweight='bold', pad=15)

    # Add legend with details (positioned below plot to avoid overlap)
    legend_text = [f'Cost of Equity: {ce:.2f}%', f'Cost of Borrowing: {cb:.2f}%', f'Leveraged Beta: {beta:.2f}']
    ax2.legend(legend_text, loc='upper center', bbox_to_anchor=(0.5, -0.05), fontsize=9, framealpha=0.9, ncol=3)

    fig.suptitle(f'{ticker} - Cost of Capital Breakdown', fontsize=15, fontweight='bold')
    plt.tight_layout()
    save_figure(fig, output_file, dpi=300)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Generate DCF deterministic visualizations (both light and dark modes)")
    parser.add_argument("--log-dir", default="valuation/dcf_deterministic/log", help="Directory with log files")
    parser.add_argument("--viz-dir", default="valuation/dcf_deterministic/output", help="Directory to save visualizations")
    parser.add_argument("--csv-dir", default="valuation/dcf_deterministic/output/sensitivity/data", help="Directory with sensitivity CSV files")
    parser.add_argument("--valuation-only", action="store_true", help="Generate only valuation plots in both Kanagawa Lotus (light) and Dragon (dark) themes")
    parser.add_argument("--sensitivity-only", action="store_true", help="Generate only sensitivity plots in both Kanagawa Lotus (light) and Dragon (dark) themes")
    args = parser.parse_args()

    log_dir = Path(args.log_dir)
    viz_dir = Path(args.viz_dir)
    csv_dir = Path(args.csv_dir)

    # Default: generate both types if neither flag is specified
    generate_valuation = args.valuation_only or (not args.valuation_only and not args.sensitivity_only)
    generate_sensitivity = args.sensitivity_only or (not args.valuation_only and not args.sensitivity_only)

    viz_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Find log files
        log_files = list(log_dir.glob("dcf_*.log"))
        if not log_files:
            print("Error: No log files found", file=sys.stderr)
            print("Run deterministic DCF valuation first.", file=sys.stderr)
            sys.exit(1)

        # Group by ticker and get most recent log for each
        ticker_logs = {}
        for log_file in log_files:
            # Extract ticker from filename: dcf_TICKER_timestamp.log
            ticker = log_file.stem.split('_')[1]
            if ticker not in ticker_logs or log_file.stat().st_mtime > ticker_logs[ticker].stat().st_mtime:
                ticker_logs[ticker] = log_file

        # Load data for all tickers
        all_data = []
        for ticker, log_file in sorted(ticker_logs.items()):
            print(f"Loading data from: {log_file}")
            data = parse_log_file(log_file)
            all_data.append(data)

        print(f"\nLoaded data for {len(all_data)} tickers")

        # Separate banks, insurers, O&G, and standard companies
        bank_data = [d for d in all_data if d.get('is_bank', False)]
        insurance_data = [d for d in all_data if d.get('is_insurance', False)]
        oil_gas_data = [d for d in all_data if d.get('is_oil_gas', False)]
        non_specialized_data = [d for d in all_data if not d.get('is_bank', False) and not d.get('is_insurance', False) and not d.get('is_oil_gas', False)]

        print(f"  - Banks: {len(bank_data)} ({', '.join(d['ticker'] for d in bank_data) or 'none'})")
        print(f"  - Insurance: {len(insurance_data)} ({', '.join(d['ticker'] for d in insurance_data) or 'none'})")
        print(f"  - O&G E&P: {len(oil_gas_data)} ({', '.join(d['ticker'] for d in oil_gas_data) or 'none'})")
        print(f"  - Standard: {len(non_specialized_data)} ({', '.join(d['ticker'] for d in non_specialized_data) or 'none'})")

        # Generate valuation plots if requested (dark mode only)
        if generate_valuation:
            print("\nGenerating valuation plots...")
            val_dir = viz_dir / "valuation"
            val_dir.mkdir(parents=True, exist_ok=True)

            # Dark mode (Kanagawa Dragon)
            setup_dark_mode()

            # Generate standard DCF comparison (only if there are non-specialized companies)
            if non_specialized_data:
                plot_comparison_consolidated(non_specialized_data, val_dir / "dcf_comparison_all.png", dark_mode=True)
                print("  - DCF comparison chart: valuation/dcf_comparison_all.png")

            # Generate bank comparison (only if there are banks)
            if bank_data:
                plot_bank_comparison(bank_data, val_dir / "bank_comparison_all.png", dark_mode=True)
                print("  - Bank comparison chart: valuation/bank_comparison_all.png")

            # Generate insurance comparison (only if there are insurers)
            if insurance_data:
                plot_insurance_comparison(insurance_data, val_dir / "insurance_comparison_all.png", dark_mode=True)
                print("  - Insurance comparison chart: valuation/insurance_comparison_all.png")

            # Generate O&G E&P comparison (only if there are O&G companies)
            if oil_gas_data:
                plot_oil_gas_comparison(oil_gas_data, val_dir / "oil_gas_comparison_all.png", dark_mode=True)
                print("  - O&G E&P comparison chart: valuation/oil_gas_comparison_all.png")

        # Generate sensitivity plots if requested (dark mode only)
        if generate_sensitivity:
            print(f"\nGenerating {len(all_data)} sensitivity plots in parallel...")
            print(f"Reading sensitivity data from: {csv_dir}")
            sens_dir = viz_dir / "sensitivity" / "plots"
            sens_dir.mkdir(parents=True, exist_ok=True)

            # Prepare arguments: route specialized tickers to their plot functions
            sensitivity_tasks = []
            specialized_tasks = []
            for data in all_data:
                ticker = data['ticker']
                if data.get('is_bank', False):
                    specialized_tasks.append(
                        (data, sens_dir / f"dcf_sensitivity_{ticker}.png", str(csv_dir), True, plot_bank_sensitivity))
                elif data.get('is_insurance', False):
                    specialized_tasks.append(
                        (data, sens_dir / f"dcf_sensitivity_{ticker}.png", str(csv_dir), True, plot_insurance_sensitivity))
                elif data.get('is_oil_gas', False):
                    specialized_tasks.append(
                        (data, sens_dir / f"dcf_sensitivity_{ticker}.png", str(csv_dir), True, plot_oil_gas_sensitivity))
                else:
                    sensitivity_tasks.append(
                        (data, sens_dir / f"dcf_sensitivity_{ticker}.png", str(csv_dir), True))

            # Determine number of workers (max CPUs - 2 to avoid overstraining system)
            total_plots = len(sensitivity_tasks) + len(specialized_tasks)
            num_workers = min(max(1, multiprocessing.cpu_count() - 2), total_plots)
            print(f"Using {num_workers} parallel workers...")

            # Generate plots in parallel
            completed = 0
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                future_to_info = {}
                # Standard sensitivity tasks
                for task in sensitivity_tasks:
                    future_to_info[executor.submit(_generate_sensitivity_plot, task)] = task[0]['ticker']
                # Specialized sensitivity tasks
                for task in specialized_tasks:
                    future_to_info[executor.submit(_generate_specialized_sensitivity_plot, task)] = task[0]['ticker']

                # Process completed tasks as they finish
                for future in as_completed(future_to_info):
                    ticker = future_to_info[future]
                    try:
                        future.result()
                        completed += 1
                        print(f"  [{completed}/{total_plots}] {ticker} completed")
                    except Exception as e:
                        print(f"  [ERROR] {ticker} failed: {e}", file=sys.stderr)

        print(f"\nAll visualizations saved to: {viz_dir}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

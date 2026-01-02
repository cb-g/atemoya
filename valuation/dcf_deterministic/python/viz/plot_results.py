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

try:
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError:
    print("Error: Required packages not installed.", file=sys.stderr)
    print("Run: pip install matplotlib numpy pandas yfinance", file=sys.stderr)
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


def parse_log_file(log_path):
    """Extract valuation data from DCF log file."""
    with open(log_path, 'r') as f:
        content = f.read()

    data = {}

    # Extract ticker
    match = re.search(r'DCF Valuation: (\w+)', content)
    data['ticker'] = match.group(1) if match else 'Unknown'

    # Extract market price (note: format is "Current Price: $...")
    match = re.search(r'Current Price: \$([0-9.]+)', content)
    data['price'] = float(match.group(1)) if match else 0.0

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

    # Extract cost of capital
    match = re.search(r'Cost of Equity: ([0-9.]+)%', content)
    data['ce'] = float(match.group(1)) if match else 0.0

    match = re.search(r'WACC: ([0-9.]+)%', content)
    data['wacc'] = float(match.group(1)) if match else 0.0

    match = re.search(r'Cost of Borrowing: ([0-9.]+)%', content)
    data['cb'] = float(match.group(1)) if match else 0.0

    match = re.search(r'Leveraged Beta: ([0-9.]+)', content)
    data['beta'] = float(match.group(1)) if match else 0.0

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
        company_name = stock.info.get('shortName', ticker)
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
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Sensitivity analysis saved: {output_file}")


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
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Consolidated comparison chart saved: {output_file}")


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
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Cost of capital breakdown saved: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Generate DCF deterministic visualizations (both light and dark modes)")
    parser.add_argument("--log-dir", default="../log", help="Directory with log files")
    parser.add_argument("--viz-dir", default="../output", help="Directory to save visualizations")
    parser.add_argument("--csv-dir", default="../output/sensitivity/data", help="Directory with sensitivity CSV files")
    parser.add_argument("--valuation-only", action="store_true", help="Generate only valuation plots in both Kanagawa Lotus (light) and Dragon (dark) themes")
    parser.add_argument("--sensitivity-only", action="store_true", help="Generate only sensitivity plots in both Kanagawa Lotus (light) and Dragon (dark) themes")
    args = parser.parse_args()

    log_dir = Path(args.log_dir)
    viz_dir = Path(args.viz_dir)
    csv_dir = Path(args.csv_dir)

    # Default: generate both types if neither flag is specified
    generate_valuation = args.valuation_only or (not args.valuation_only and not args.sensitivity_only)
    generate_sensitivity = args.sensitivity_only or (not args.valuation_only and not args.sensitivity_only)

    # Clear old PNG files before generating new visualizations
    if viz_dir.exists():
        import glob
        old_pngs = glob.glob(str(viz_dir / "*.png"))
        for png_file in old_pngs:
            Path(png_file).unlink()
        if old_pngs:
            print(f"Cleared {len(old_pngs)} old PNG file(s) from: {viz_dir}")

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

        # Generate valuation plots if requested (dark mode only)
        if generate_valuation:
            print("\nGenerating valuation plots...")

            # Dark mode (Kanagawa Dragon)
            setup_dark_mode()
            plot_comparison_consolidated(all_data, viz_dir / "dcf_comparison_all.png", dark_mode=True)
            print("  - Valuation comparison chart: dcf_comparison_all.png")

        # Generate sensitivity plots if requested (dark mode only)
        if generate_sensitivity:
            print(f"\nGenerating {len(all_data)} sensitivity plots in parallel...")
            print(f"Reading sensitivity data from: {csv_dir}")

            # Prepare arguments for parallel processing - dark mode only
            sensitivity_tasks = [
                (data, viz_dir / f"dcf_sensitivity_{data['ticker']}.png", str(csv_dir), True)
                for data in all_data
            ]

            # Determine number of workers (max CPUs - 2 to avoid overstraining system)
            num_workers = min(max(1, multiprocessing.cpu_count() - 2), len(all_data))
            print(f"Using {num_workers} parallel workers...")

            # Generate plots in parallel
            completed = 0
            total_plots = len(sensitivity_tasks)
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                # Submit all tasks
                future_to_info = {
                    executor.submit(_generate_sensitivity_plot, task): task[0]['ticker']
                    for task in sensitivity_tasks
                }

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

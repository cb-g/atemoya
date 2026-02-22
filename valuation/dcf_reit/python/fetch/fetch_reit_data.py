#!/usr/bin/env python3
"""
Fetch REIT financial data from Yahoo Finance and other sources.

Creates JSON files for each REIT with:
- Market data (price, shares, dividend)
- Financial data (FFO components, balance sheet)
- Property-level metrics where available
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf
import pandas as pd
import numpy as np

from lib.python.retry import retry_with_backoff


# REIT sector classification based on GICS
REIT_SECTORS = {
    # Industrial
    'PLD': 'industrial', 'DRE': 'industrial', 'REXR': 'industrial',
    'STAG': 'industrial', 'EGP': 'industrial', 'FR': 'industrial',

    # Retail
    'O': 'retail', 'NNN': 'retail', 'SPG': 'retail', 'REG': 'retail',
    'KIM': 'retail', 'FRT': 'retail', 'BRX': 'retail', 'SITC': 'retail',

    # Residential
    'EQR': 'residential', 'AVB': 'residential', 'UDR': 'residential',
    'ESS': 'residential', 'MAA': 'residential', 'CPT': 'residential',
    'INVH': 'residential', 'AMH': 'residential',

    # Manufactured Housing / Land Lease
    'ELS': 'residential', 'SUI': 'residential',

    # Office
    'BXP': 'office', 'VNO': 'office', 'SLG': 'office', 'KRC': 'office',
    'HIW': 'office', 'DEI': 'office', 'CUZ': 'office',

    # Healthcare
    'WELL': 'healthcare', 'VTR': 'healthcare', 'OHI': 'healthcare',
    'HR': 'healthcare', 'DOC': 'healthcare', 'SBRA': 'healthcare',

    # Data Center
    'EQIX': 'datacenter', 'DLR': 'datacenter',

    # Cell Towers / Infrastructure
    'AMT': 'specialty', 'CCI': 'specialty', 'SBAC': 'specialty',

    # Self Storage
    'PSA': 'selfstorage', 'EXR': 'selfstorage', 'CUBE': 'selfstorage',
    'LSI': 'selfstorage', 'NSA': 'selfstorage',

    # Hotel
    'HST': 'hotel', 'RHP': 'hotel', 'PK': 'hotel', 'SHO': 'hotel',

    # Gaming / Specialty
    'GLPI': 'specialty', 'VICI': 'specialty',

    # Mortgage REITs (mREITs) - invest in mortgages/MBS, not physical properties
    'RITM': 'mortgage', 'NLY': 'mortgage', 'AGNC': 'mortgage',
    'STWD': 'mortgage', 'BXMT': 'mortgage', 'ABR': 'mortgage',
    'TWO': 'mortgage', 'MFA': 'mortgage', 'NRZ': 'mortgage',
    'NYMT': 'mortgage', 'PMT': 'mortgage', 'GPMT': 'mortgage',
    'ARI': 'mortgage', 'LADR': 'mortgage', 'RC': 'mortgage',
    'KREF': 'mortgage', 'TRTX': 'mortgage', 'ACRE': 'mortgage',
}


def get_sector(ticker: str) -> str:
    """Get REIT sector from ticker."""
    return REIT_SECTORS.get(ticker.upper(), 'diversified')


def fetch_reit_data(ticker: str) -> dict:
    """Fetch comprehensive REIT data from Yahoo Finance."""
    stock = yf.Ticker(ticker)
    info = retry_with_backoff(lambda: stock.info)

    # Basic market data
    price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
    shares = info.get('sharesOutstanding', 0)
    market_cap = info.get('marketCap', shares * price if shares and price else 0)

    # Dividend data
    # Note: yfinance returns dividendYield as percentage (e.g., 5.54 for 5.54%)
    # We normalize to decimal (0.0554) for consistency
    div_rate = info.get('dividendRate', 0) or 0
    div_yield_raw = info.get('dividendYield', 0) or 0
    div_yield = div_yield_raw / 100.0 if div_yield_raw > 1 else div_yield_raw

    # Get financials
    try:
        income_stmt = retry_with_backoff(lambda: stock.income_stmt)
        balance_sheet = retry_with_backoff(lambda: stock.balance_sheet)
        cash_flow = retry_with_backoff(lambda: stock.cash_flow)
    except Exception:
        income_stmt = pd.DataFrame()
        balance_sheet = pd.DataFrame()
        cash_flow = pd.DataFrame()

    # Extract latest annual figures
    def get_latest(df, keys, default=0):
        for key in keys if isinstance(keys, list) else [keys]:
            if key in df.index and len(df.columns) > 0:
                val = df.loc[key].iloc[0]
                if pd.notna(val):
                    return float(val)
        return default

    # Income statement items
    revenue = get_latest(income_stmt, ['Total Revenue', 'Revenue'])
    net_income = get_latest(income_stmt, ['Net Income', 'Net Income Common Stockholders'])

    # Depreciation (from cash flow statement)
    depreciation = get_latest(cash_flow, ['Depreciation And Amortization', 'Depreciation'])

    # Try to split D&A
    amortization = depreciation * 0.05  # Estimate amortization as 5% of D&A
    depreciation = depreciation * 0.95

    # CapEx
    capex = abs(get_latest(cash_flow, ['Capital Expenditure', 'Capital Expenditures']))

    # Estimate maintenance vs development capex
    maintenance_capex = capex * 0.15  # Typically 10-20% of total
    development_capex = capex * 0.85

    # Balance sheet
    total_debt = get_latest(balance_sheet, ['Total Debt', 'Long Term Debt'])
    cash = get_latest(balance_sheet, ['Cash And Cash Equivalents', 'Cash'])
    total_assets = get_latest(balance_sheet, ['Total Assets'])
    total_equity = get_latest(balance_sheet, ['Stockholders Equity', 'Total Stockholders Equity'])

    # Get stock compensation
    stock_comp = get_latest(cash_flow, ['Stock Based Compensation'])

    # Occupancy and lease data (estimates based on sector)
    sector = get_sector(ticker)

    # Check if this is a mortgage REIT
    is_mreit = sector == 'mortgage'

    # mREIT-specific data
    interest_income = 0.0
    interest_expense = 0.0
    net_interest_income = 0.0
    earning_assets = 0.0
    distributable_earnings = 0.0
    book_value_per_share = 0.0

    if is_mreit:
        # For mREITs, fetch interest income/expense
        interest_income = get_latest(income_stmt, ['Interest Income', 'Interest Income Non Operating', 'Total Interest Income'])
        interest_expense = get_latest(income_stmt, ['Interest Expense', 'Interest Expense Non Operating', 'Total Interest Expense'])

        # If not in income statement, try to estimate from financials
        if interest_income == 0:
            # For mREITs, revenue is often primarily interest income
            interest_income = revenue * 0.85  # Estimate
        if interest_expense == 0:
            # Estimate from debt * average cost of debt (~5-6%)
            interest_expense = total_debt * 0.055

        net_interest_income = interest_income - interest_expense

        # Earning assets = total assets - cash - non-earning assets
        earning_assets = total_assets - cash if total_assets > 0 else 0

        # Book value per share
        book_value_per_share = info.get('bookValue', 0) or 0
        if book_value_per_share == 0 and shares > 0 and total_equity > 0:
            book_value_per_share = total_equity / shares

        # Distributable earnings (mREIT equivalent of AFFO)
        # Estimate as net income + depreciation (mREITs have minimal depreciation)
        distributable_earnings = net_income + depreciation + amortization

        # For mREITs, NOI doesn't apply - set to 0
        noi = 0.0
        occupancy_rate = 0.0
        same_store_growth = 0.0
        walt = 0.0
        lease_exp = 0.0
    else:
        # Equity REIT - estimate NOI from EBITDA or revenue
        ebitda = get_latest(income_stmt, ['EBITDA', 'Operating Income'])
        noi = ebitda * 0.85 if ebitda > 0 else revenue * 0.45

        occupancy_defaults = {
            'industrial': 0.97, 'retail': 0.95, 'residential': 0.96,
            'office': 0.88, 'healthcare': 0.92, 'datacenter': 0.91,
            'selfstorage': 0.94, 'hotel': 0.72, 'specialty': 0.95,
            'diversified': 0.93
        }
        walt_defaults = {
            'industrial': 5.5, 'retail': 8.0, 'residential': 1.0,
            'office': 6.0, 'healthcare': 10.0, 'datacenter': 4.0,
            'selfstorage': 0.5, 'hotel': 0.1, 'specialty': 12.0,
            'diversified': 6.0
        }
        occupancy_rate = occupancy_defaults.get(sector, 0.93)
        same_store_growth = 0.025
        walt = walt_defaults.get(sector, 5.0)
        lease_exp = 0.10

    # Build market data
    market_data = {
        'ticker': ticker.upper(),
        'price': round(price, 2),
        'shares_outstanding': int(shares),
        'market_cap': round(market_cap, 0),
        'dividend_yield': round(div_yield, 4),
        'dividend_per_share': round(div_rate, 2),
        'currency': 'USD',
        'sector': sector
    }

    # Add reit_type for mREITs
    if is_mreit:
        market_data['reit_type'] = 'mortgage'

    # Build financial data
    financial_data = {
        'revenue': round(revenue, 0),
        'net_income': round(net_income, 0),
        'depreciation': round(depreciation, 0),
        'amortization': round(amortization, 0),
        'gains_on_sales': 0,
        'impairments': 0,
        'straight_line_rent_adj': round(revenue * 0.01, 0) if not is_mreit else 0,
        'stock_compensation': round(stock_comp, 0),
        'maintenance_capex': round(maintenance_capex, 0) if not is_mreit else 0,
        'development_capex': round(development_capex, 0) if not is_mreit else 0,
        'total_debt': round(total_debt, 0),
        'cash': round(cash, 0),
        'total_assets': round(total_assets, 0),
        'total_equity': round(total_equity, 0),
    }

    if is_mreit:
        # mREIT-specific fields
        financial_data.update({
            'book_value_per_share': round(book_value_per_share, 2),
            'noi': 0.0,
            'occupancy_rate': 0.0,
            'same_store_noi_growth': 0.0,
            'weighted_avg_lease_term': 0.0,
            'lease_expiration_1yr': 0.0,
            'interest_income': round(interest_income, 0),
            'interest_expense': round(interest_expense, 0),
            'net_interest_income': round(net_interest_income, 0),
            'earning_assets': round(earning_assets, 0),
            'distributable_earnings': round(distributable_earnings, 0),
        })
    else:
        # Equity REIT fields
        financial_data.update({
            'noi': round(noi, 0),
            'occupancy_rate': occupancy_rate,
            'same_store_noi_growth': same_store_growth,
            'weighted_avg_lease_term': walt,
            'lease_expiration_1yr': lease_exp,
        })

    data = {
        'market': market_data,
        'financial': financial_data
    }

    return data


def save_reit_data(ticker: str, data: dict, output_dir: Path):
    """Save REIT data to JSON file."""
    output_file = output_dir / f"{ticker.upper()}.json"
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Saved: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Fetch REIT financial data')
    parser.add_argument('-t', '--tickers', nargs='+', required=True,
                        help='REIT ticker symbols')
    parser.add_argument('-o', '--output-dir', type=str, default='data',
                        help='Output directory')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for ticker in args.tickers:
        print(f"\nFetching data for {ticker}...")
        try:
            data = fetch_reit_data(ticker)
            save_reit_data(ticker, data, output_dir)
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")

    print("\nDone!")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Fetch financial data for DCF valuation using yfinance.
Outputs market_data and financial_data JSON files.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    print("Error: yfinance not installed. Run: pip install yfinance", file=sys.stderr)
    sys.exit(1)


def fetch_market_data(ticker_obj, ticker_symbol):
    """Extract market data from yfinance ticker."""
    info = ticker_obj.info

    # Extract basic market data
    market_data = {
        "ticker": ticker_symbol,
        "price": info.get("currentPrice", info.get("regularMarketPrice", 0.0)),
        "mve": info.get("marketCap", 0.0),
        "mvb": info.get("totalDebt", 0.0),
        "shares_outstanding": info.get("sharesOutstanding", 0.0),
        "currency": info.get("currency", "USD"),
        "country": info.get("country", "USA"),
        "industry": info.get("industry", "Unknown"),
    }

    return market_data


def fetch_financial_data(ticker_obj):
    """Extract financial statement data from yfinance ticker."""

    # Get financial statements
    income_stmt = ticker_obj.income_stmt
    balance_sheet = ticker_obj.balance_sheet
    cash_flow = ticker_obj.cash_flow
    info = ticker_obj.info

    # Use most recent annual data (column 0)
    if income_stmt.empty or balance_sheet.empty or cash_flow.empty:
        raise ValueError("Financial data not available for this ticker")

    # Helper to safely get value with fallback
    def get_value(df, keys, default=0.0):
        """Try multiple keys in order, return first match or default."""
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            if key in df.index:
                val = df.loc[key].iloc[0] if not df.loc[key].empty else default
                return float(val) if val == val else default  # Check for NaN
        return default

    # Extract EBIT (with multiple fallback strategies)
    ebit_keys = ["EBIT", "Operating Income", "Operating Income Loss"]
    ebit = get_value(income_stmt, ebit_keys)

    # If EBIT not found, reconstruct: EBIT = EBT + Interest Expense
    if ebit == 0.0:
        ebt = get_value(income_stmt, ["Pretax Income", "Income Before Tax"])
        interest_exp = get_value(income_stmt, ["Interest Expense"])
        if ebt != 0.0:
            ebit = ebt + abs(interest_exp)  # Interest expense is usually negative

    # Check if this is a bank (financial services)
    is_bank = "bank" in info.get("industry", "").lower() or \
              "financial" in info.get("industry", "").lower()

    # For banks, use PPNR proxy if available
    if is_bank and ebit == 0.0:
        net_interest_income = get_value(income_stmt, ["Interest Income", "Net Interest Income"])
        non_interest_income = get_value(income_stmt, ["Non Interest Income"])
        non_interest_expense = get_value(income_stmt, ["Non Interest Expense"])
        provision = get_value(income_stmt, ["Provision For Loan Losses"])
        ebit = net_interest_income + non_interest_income - non_interest_expense - provision

    # Extract other income statement items
    net_income = get_value(income_stmt, ["Net Income", "Net Income Common Stockholders"])
    interest_expense = abs(get_value(income_stmt, ["Interest Expense"]))  # Make positive
    taxes = abs(get_value(income_stmt, ["Tax Provision"]))  # Make positive

    # Extract cash flow statement items
    capex = abs(get_value(cash_flow, ["Capital Expenditure", "Capital Expenditures"]))  # Make positive
    depreciation = abs(get_value(cash_flow, [
        "Depreciation And Amortization",
        "Depreciation",
        "Reconciled Depreciation"
    ]))

    # Calculate change in working capital
    # ΔWC = Δ(Current Assets - Current Liabilities)
    current_assets = get_value(balance_sheet, ["Current Assets"])
    current_liabilities = get_value(balance_sheet, ["Current Liabilities"])

    # Get prior year balance sheet (column 1 if available)
    if balance_sheet.shape[1] >= 2:
        current_assets_prior = get_value(balance_sheet.iloc[:, [1]], ["Current Assets"])
        current_liabilities_prior = get_value(balance_sheet.iloc[:, [1]], ["Current Liabilities"])
        delta_wc = (current_assets - current_liabilities) - \
                   (current_assets_prior - current_liabilities_prior)
    else:
        # No prior year data, use 0
        delta_wc = 0.0

    # Extract balance sheet items
    book_value_equity = get_value(balance_sheet, [
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
        "Common Stock Equity"
    ])

    total_debt = get_value(balance_sheet, ["Total Debt"])
    invested_capital = book_value_equity + total_debt

    financial_data = {
        "ebit": ebit,
        "net_income": net_income,
        "interest_expense": interest_expense,
        "taxes": taxes,
        "capex": capex,
        "depreciation": depreciation,
        "delta_wc": delta_wc,
        "book_value_equity": book_value_equity,
        "invested_capital": invested_capital,
        "is_bank": is_bank,
    }

    return financial_data


def main():
    parser = argparse.ArgumentParser(description="Fetch financial data for DCF valuation")
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g., AAPL)")
    parser.add_argument("--output", default="/tmp", help="Output directory for JSON files")
    args = parser.parse_args()

    ticker_symbol = args.ticker.upper()
    output_dir = Path(args.output)

    print(f"Fetching data for {ticker_symbol}...")

    try:
        # Fetch ticker data
        ticker = yf.Ticker(ticker_symbol)

        # Extract data
        market_data = fetch_market_data(ticker, ticker_symbol)
        financial_data = fetch_financial_data(ticker)

        # Validate critical fields
        if market_data["shares_outstanding"] == 0.0:
            raise ValueError("Shares outstanding is zero or not available")
        if market_data["price"] == 0.0:
            raise ValueError("Current price is zero or not available")

        # Write JSON files
        market_data_file = output_dir / f"dcf_market_data_{ticker_symbol}.json"
        financial_data_file = output_dir / f"dcf_financial_data_{ticker_symbol}.json"

        with open(market_data_file, "w") as f:
            json.dump(market_data, f, indent=2)
        print(f"Market data written to: {market_data_file}")

        with open(financial_data_file, "w") as f:
            json.dump(financial_data, f, indent=2)
        print(f"Financial data written to: {financial_data_file}")

        print("Data fetch successful!")

    except Exception as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

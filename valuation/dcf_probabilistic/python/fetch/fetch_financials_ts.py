#!/usr/bin/env python3
"""
Fetch 4-year time series financial data for probabilistic DCF valuation using yfinance.
Outputs market_data and time_series JSON files.
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

    market_data = {
        "ticker": ticker_symbol,
        "price": info.get("currentPrice", info.get("regularMarketPrice", 0.0)),
        "mve": info.get("marketCap", 0.0),
        "mvb": info.get("totalDebt", 0.0),
        "shares_outstanding": info.get("sharesOutstanding", 0.0),
        "currency": info.get("currency", "USD"),
        "country": info.get("country", "USA"),
        "sector": info.get("sector", "Unknown"),
        "industry": info.get("industry", "Unknown"),
    }

    return market_data


def extract_time_series(ticker_obj):
    """Extract 4-year time series from financial statements."""

    income_stmt = ticker_obj.income_stmt
    balance_sheet = ticker_obj.balance_sheet
    cash_flow = ticker_obj.cash_flow

    if income_stmt.empty or balance_sheet.empty or cash_flow.empty:
        raise ValueError("Financial data not available")

    # Helper to safely extract series with fallbacks
    def get_series(df, keys, default=0.0):
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            if key in df.index:
                series = df.loc[key].fillna(default).tolist()
                # Return up to 4 most recent years
                return series[:4]
        return [default] * 4

    # Income statement time series
    ebit = get_series(income_stmt, ["EBIT", "Operating Income", "Operating Income Loss"])
    net_income = get_series(income_stmt, ["Net Income", "Net Income Common Stockholders"])

    # Cash flow statement time series
    capex = [abs(x) for x in get_series(cash_flow, ["Capital Expenditure", "Capital Expenditures"])]
    depreciation = [abs(x) for x in get_series(cash_flow, [
        "Depreciation And Amortization",
        "Depreciation",
        "Reconciled Depreciation"
    ])]
    dividend_payout = [abs(x) for x in get_series(cash_flow, [
        "Cash Dividends Paid",
        "Common Stock Dividend Paid"
    ])]

    # Balance sheet time series
    current_assets = get_series(balance_sheet, ["Current Assets"])
    current_liabilities = get_series(balance_sheet, ["Current Liabilities"])
    book_value_equity = get_series(balance_sheet, [
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
        "Common Stock Equity"
    ])

    total_debt = get_series(balance_sheet, ["Total Debt"])

    # Calculate invested capital for each period
    invested_capital = [bve + td for bve, td in zip(book_value_equity, total_debt)]

    time_series = {
        "ebit": ebit,
        "net_income": net_income,
        "capex": capex,
        "depreciation": depreciation,
        "current_assets": current_assets,
        "current_liabilities": current_liabilities,
        "book_value_equity": book_value_equity,
        "dividend_payout": dividend_payout,
        "invested_capital": invested_capital,
    }

    return time_series


def main():
    parser = argparse.ArgumentParser(description="Fetch 4-year time series for probabilistic DCF")
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g., AAPL)")
    parser.add_argument("--output", default="/tmp", help="Output directory for JSON files")
    args = parser.parse_args()

    ticker_symbol = args.ticker.upper()
    output_dir = Path(args.output)

    print(f"Fetching 4-year time series for {ticker_symbol}...")

    try:
        ticker = yf.Ticker(ticker_symbol)

        # Extract data
        market_data = fetch_market_data(ticker, ticker_symbol)
        time_series = extract_time_series(ticker)

        # Validate
        if market_data["shares_outstanding"] == 0.0:
            raise ValueError("Shares outstanding is zero or not available")
        if market_data["price"] == 0.0:
            raise ValueError("Current price is zero or not available")

        # Wrap time series in required format
        output_data = {
            "time_series": time_series
        }

        # Write JSON files
        market_data_file = output_dir / f"dcf_prob_market_data_{ticker_symbol}.json"
        time_series_file = output_dir / f"dcf_prob_time_series_{ticker_symbol}.json"

        with open(market_data_file, "w") as f:
            json.dump(market_data, f, indent=2)
        print(f"Market data written to: {market_data_file}")

        with open(time_series_file, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"Time series written to: {time_series_file}")

        print("Data fetch successful!")

    except Exception as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

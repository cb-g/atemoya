#!/usr/bin/env python3
"""
Fetch GARP/PEG analysis data.

Uses yfinance for fundamental data (analyst estimates, financials).
Note: IBKR doesn't provide fundamental data, so yfinance is required here.
Outputs garp_data JSON file with P/E ratios, growth estimates, and quality metrics.
"""

import argparse
import json
import sys
import time
import random
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf

from lib.python.retry import retry_with_backoff


def fetch_garp_data(ticker_obj, ticker_symbol):
    """Extract GARP/PEG analysis data from yfinance ticker."""
    info = ticker_obj.info

    # Basic market data
    price = info.get("currentPrice", info.get("regularMarketPrice", 0.0))
    market_cap = info.get("marketCap", 0.0)
    shares_outstanding = info.get("sharesOutstanding", 0.0)

    # EPS data
    eps_trailing = info.get("trailingEps", 0.0)
    eps_forward = info.get("forwardEps", 0.0)

    # P/E ratios
    pe_trailing = info.get("trailingPE", 0.0)
    pe_forward = info.get("forwardPE", 0.0)

    # Growth estimates
    # earningsGrowth is typically quarterly YoY
    # earningsQuarterlyGrowth is another option
    earnings_growth = info.get("earningsGrowth", 0.0)  # As decimal (0.15 = 15%)
    earnings_quarterly_growth = info.get("earningsQuarterlyGrowth", 0.0)
    revenue_growth = info.get("revenueGrowth", 0.0)

    # PEG ratio (yfinance provides this but we'll calculate our own too)
    peg_ratio_yf = info.get("pegRatio", 0.0)

    # Calculate EPS growth from trailing to forward
    # This gives us a 1-year forward growth estimate
    if eps_trailing > 0 and eps_forward > 0:
        eps_growth_1y = (eps_forward - eps_trailing) / eps_trailing
    elif eps_trailing < 0 and eps_forward > eps_trailing:
        # Improving from loss
        eps_growth_1y = 0.0  # Can't calculate meaningful growth
    else:
        eps_growth_1y = 0.0

    # Get analyst estimates for longer-term growth
    # yfinance provides 5-year growth estimate in some cases
    growth_estimate_5y = info.get("earningsGrowth", 0.0)  # Often the 5-year estimate

    # Quality metrics for GARP scoring
    # Free cash flow
    free_cash_flow = info.get("freeCashflow", 0.0)
    operating_cash_flow = info.get("operatingCashflow", 0.0)

    # Profitability
    net_income = info.get("netIncomeToCommon", 0.0)
    total_revenue = info.get("totalRevenue", 0.0)

    # Balance sheet
    total_debt = info.get("totalDebt", 0.0)
    total_cash = info.get("totalCash", 0.0)
    book_value_ps = info.get("bookValue", 0.0)  # Per-share book value from yfinance

    # Derive total equity from book value per share
    total_equity = book_value_ps * shares_outstanding if book_value_ps and shares_outstanding else 0.0

    # Returns
    roe = info.get("returnOnEquity", 0.0)  # As decimal
    roa = info.get("returnOnAssets", 0.0)

    # Dividend (for PEGY ratio)
    dividend_yield = info.get("dividendYield", 0.0)  # As decimal
    dividend_rate = info.get("dividendRate", 0.0)

    # Calculate derived metrics
    # Debt to Equity ratio (yfinance provides as percentage, e.g. 39.16 = 39.16%)
    debt_to_equity_raw = info.get("debtToEquity", 0.0)
    debt_to_equity = (debt_to_equity_raw / 100.0) if debt_to_equity_raw else 0.0

    # FCF conversion (FCF / Net Income)
    fcf_conversion = free_cash_flow / net_income if net_income > 0 else 0.0

    # FCF per share
    fcf_per_share = free_cash_flow / shares_outstanding if shares_outstanding > 0 else 0.0

    # Net cash per share
    net_cash = total_cash - total_debt
    net_cash_per_share = net_cash / shares_outstanding if shares_outstanding > 0 else 0.0

    # Sector and industry for context
    sector = info.get("sector", "Unknown")
    industry = info.get("industry", "Unknown")

    garp_data = {
        "ticker": ticker_symbol,
        "price": price,
        "market_cap": market_cap,
        "shares_outstanding": shares_outstanding,

        # EPS data
        "eps_trailing": eps_trailing,
        "eps_forward": eps_forward,

        # P/E ratios
        "pe_trailing": pe_trailing,
        "pe_forward": pe_forward,

        # Growth rates (as decimals, e.g., 0.15 = 15%)
        "earnings_growth": earnings_growth,
        "earnings_quarterly_growth": earnings_quarterly_growth,
        "revenue_growth": revenue_growth,
        "eps_growth_1y": eps_growth_1y,
        "growth_estimate_5y": growth_estimate_5y,

        # PEG from yfinance (for comparison)
        "peg_ratio_yf": peg_ratio_yf,

        # Quality metrics
        "free_cash_flow": free_cash_flow,
        "operating_cash_flow": operating_cash_flow,
        "net_income": net_income,
        "total_revenue": total_revenue,

        # Balance sheet
        "total_debt": total_debt,
        "total_equity": total_equity,
        "total_cash": total_cash,
        "debt_to_equity": debt_to_equity,

        # Returns (as decimals)
        "roe": roe,
        "roa": roa,

        # Derived metrics
        "fcf_conversion": fcf_conversion,
        "fcf_per_share": fcf_per_share,
        "book_value_per_share": book_value_ps,
        "net_cash_per_share": net_cash_per_share,

        # Dividend (for PEGY)
        "dividend_yield": dividend_yield,
        "dividend_rate": dividend_rate,

        # Classification
        "sector": sector,
        "industry": industry,
    }

    return garp_data



def main():
    parser = argparse.ArgumentParser(description="Fetch GARP/PEG analysis data")
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g., AAPL)")
    parser.add_argument("--output", default="/tmp", help="Output directory for JSON files")
    args = parser.parse_args()

    ticker_symbol = args.ticker.upper()
    output_dir = Path(args.output)

    # Add small random delay to reduce parallel request contention
    initial_delay = random.uniform(0, 0.5)
    time.sleep(initial_delay)

    print(f"Fetching GARP data for {ticker_symbol}...")

    try:
        # Fetch ticker data with retry logic
        ticker = retry_with_backoff(lambda: yf.Ticker(ticker_symbol))

        # Extract GARP data
        garp_data = retry_with_backoff(lambda: fetch_garp_data(ticker, ticker_symbol))

        # Validate critical fields
        if garp_data["price"] == 0.0:
            raise ValueError("Current price is zero or not available")
        if garp_data["eps_trailing"] == 0.0 and garp_data["eps_forward"] == 0.0:
            print("Warning: No EPS data available - PEG calculation may be invalid", file=sys.stderr)

        # Write JSON file
        output_file = output_dir / f"garp_data_{ticker_symbol}.json"

        with open(output_file, "w") as f:
            json.dump(garp_data, f, indent=2)
        print(f"GARP data written to: {output_file}")

        print("Data fetch successful!")

    except Exception as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

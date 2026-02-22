#!/usr/bin/env python3
"""
Fetch dividend data for income investor analysis.

Uses yfinance for fundamental data (dividend history, financials).
Note: IBKR doesn't provide dividend history, so yfinance is required here.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf

from lib.python.retry import retry_with_backoff


def _annual_dividends(dividends: list[dict]) -> dict[str, float]:
    """Aggregate dividends by year, excluding current year if incomplete."""
    annual = {}
    payment_counts = {}
    for d in dividends:
        year = d["date"][:4]
        annual[year] = annual.get(year, 0.0) + d["amount"]
        payment_counts[year] = payment_counts.get(year, 0) + 1

    if not annual:
        return {}

    # Drop the most recent year if it has fewer payments than the prior year
    # (indicates partial year data that would distort growth/streak calculations)
    years = sorted(annual.keys(), reverse=True)
    if len(years) >= 2:
        latest = years[0]
        prior = years[1]
        if payment_counts[latest] < payment_counts[prior]:
            del annual[latest]

    return annual


def calculate_dividend_growth_rates(dividends: list[dict]) -> dict:
    """Calculate dividend growth rates over various periods."""
    if len(dividends) < 2:
        return {"dgr_1y": 0.0, "dgr_3y": 0.0, "dgr_5y": 0.0, "dgr_10y": 0.0}

    annual = _annual_dividends(dividends)

    years = sorted(annual.keys(), reverse=True)
    if len(years) < 2:
        return {"dgr_1y": 0.0, "dgr_3y": 0.0, "dgr_5y": 0.0, "dgr_10y": 0.0}

    def cagr(start_val: float, end_val: float, years: int) -> float:
        if start_val <= 0 or end_val <= 0 or years <= 0:
            return 0.0
        return (end_val / start_val) ** (1.0 / years) - 1.0

    current_year = years[0]
    current_div = annual[current_year]

    dgr_1y = 0.0
    dgr_3y = 0.0
    dgr_5y = 0.0
    dgr_10y = 0.0

    if len(years) >= 2:
        prev_div = annual.get(years[1], 0)
        if prev_div > 0:
            dgr_1y = (current_div - prev_div) / prev_div

    if len(years) >= 4:
        past_div = annual.get(years[3], 0)
        if past_div > 0:
            dgr_3y = cagr(past_div, current_div, 3)

    if len(years) >= 6:
        past_div = annual.get(years[5], 0)
        if past_div > 0:
            dgr_5y = cagr(past_div, current_div, 5)

    if len(years) >= 11:
        past_div = annual.get(years[10], 0)
        if past_div > 0:
            dgr_10y = cagr(past_div, current_div, 10)

    return {
        "dgr_1y": round(dgr_1y, 4),
        "dgr_3y": round(dgr_3y, 4),
        "dgr_5y": round(dgr_5y, 4),
        "dgr_10y": round(dgr_10y, 4),
    }


def count_consecutive_increases(dividends: list[dict]) -> int:
    """Count consecutive years of dividend increases.

    Uses a tolerance to handle yfinance split-adjustment artifacts:
    when a stock splits mid-year, the split-adjusted annual sum can appear
    to decrease even though the actual per-share dividend increased.
    We skip years where the drop is between 0-50% (likely split artifact)
    and only break the streak on genuine cuts (>50% drop or zero).
    """
    annual = _annual_dividends(dividends)

    if len(annual) < 2:
        return 0

    years = sorted(annual.keys(), reverse=True)
    consecutive = 0

    for i in range(len(years) - 1):
        current = annual[years[i]]
        previous = annual[years[i + 1]]
        if current > previous:
            consecutive += 1
        elif previous > 0 and current / previous >= 0.5:
            # Likely a split-adjustment artifact — skip but don't break streak
            consecutive += 1
        else:
            break

    return consecutive


def get_dividend_status(consecutive_years: int) -> str:
    """Classify dividend growth streak."""
    if consecutive_years >= 50:
        return "Dividend King"
    elif consecutive_years >= 25:
        return "Dividend Aristocrat"
    elif consecutive_years >= 10:
        return "Dividend Achiever"
    elif consecutive_years >= 5:
        return "Dividend Contender"
    elif consecutive_years >= 1:
        return "Dividend Challenger"
    else:
        return "No Streak"


def fetch_dividend_data(ticker_symbol: str) -> dict:
    """Fetch comprehensive dividend data for a ticker."""
    print(f"Fetching dividend data for {ticker_symbol}...")

    ticker = yf.Ticker(ticker_symbol)
    info = retry_with_backoff(lambda: ticker.info)

    # Get dividend history
    dividends = retry_with_backoff(lambda: ticker.dividends)
    dividend_history = []
    if not dividends.empty:
        for date, amount in dividends.items():
            dividend_history.append({
                "date": date.strftime("%Y-%m-%d"),
                "amount": round(float(amount), 4)
            })

    # Calculate growth rates
    growth_rates = calculate_dividend_growth_rates(dividend_history)

    # Count consecutive increases
    consecutive_increases = count_consecutive_increases(dividend_history)
    dividend_status = get_dividend_status(consecutive_increases)

    # Get current metrics from info
    current_price = info.get("currentPrice", info.get("regularMarketPrice", 0.0))
    dividend_rate = info.get("dividendRate", 0.0) or 0.0
    dividend_yield = info.get("dividendYield", 0.0) or 0.0
    # yfinance sometimes returns yield as percentage, sometimes as decimal
    # Normalize to decimal (e.g., 0.025 for 2.5%)
    if dividend_yield > 1.0:
        dividend_yield = dividend_yield / 100.0
    payout_ratio = info.get("payoutRatio", 0.0) or 0.0

    # EPS for coverage calculation
    trailing_eps = info.get("trailingEps", 0.0) or 0.0
    forward_eps = info.get("forwardEps", 0.0) or 0.0

    # FCF for FCF payout ratio
    free_cashflow = info.get("freeCashflow", 0) or 0
    shares_outstanding = info.get("sharesOutstanding", 0) or 0
    fcf_per_share = free_cashflow / shares_outstanding if shares_outstanding > 0 else 0.0

    # Calculate coverage ratios
    eps_coverage = trailing_eps / dividend_rate if dividend_rate > 0 and trailing_eps > 0 else 0.0
    fcf_coverage = fcf_per_share / dividend_rate if dividend_rate > 0 and fcf_per_share > 0 else 0.0

    # FCF payout ratio
    fcf_payout_ratio = dividend_rate / fcf_per_share if fcf_per_share > 0 else 0.0

    # Balance sheet metrics
    debt_to_equity = info.get("debtToEquity", 0.0) or 0.0
    if debt_to_equity > 0:
        debt_to_equity = debt_to_equity / 100.0  # Convert from percentage

    current_ratio = info.get("currentRatio", 0.0) or 0.0

    # Profitability
    roe = info.get("returnOnEquity", 0.0) or 0.0
    roa = info.get("returnOnAssets", 0.0) or 0.0
    profit_margin = info.get("profitMargins", 0.0) or 0.0

    # Calculate Chowder Number (Yield + 5Y DGR)
    chowder_number = (dividend_yield * 100) + (growth_rates["dgr_5y"] * 100)

    # Ex-dividend date
    ex_dividend_date = info.get("exDividendDate", None)
    if ex_dividend_date:
        ex_dividend_date = datetime.fromtimestamp(ex_dividend_date).strftime("%Y-%m-%d")

    # Market cap for size classification
    market_cap = info.get("marketCap", 0) or 0

    # 5-year beta for volatility
    beta = info.get("beta", 1.0) or 1.0

    # Sector for context
    sector = info.get("sector", "Unknown")
    industry = info.get("industry", "Unknown")

    # Build result
    result = {
        "ticker": ticker_symbol,
        "company_name": info.get("longName", ticker_symbol),
        "sector": sector,
        "industry": industry,
        "current_price": round(current_price, 2),
        "market_cap": market_cap,
        "beta": round(beta, 2),

        # Current dividend metrics
        "dividend_rate": round(dividend_rate, 4),
        "dividend_yield": round(dividend_yield, 4),
        "ex_dividend_date": ex_dividend_date,

        # Payout ratios
        "payout_ratio_eps": round(payout_ratio, 4),
        "payout_ratio_fcf": round(fcf_payout_ratio, 4),

        # Coverage ratios
        "eps_coverage": round(eps_coverage, 2),
        "fcf_coverage": round(fcf_coverage, 2),

        # EPS data
        "trailing_eps": round(trailing_eps, 2),
        "forward_eps": round(forward_eps, 2),
        "fcf_per_share": round(fcf_per_share, 2),

        # Dividend growth
        "dgr_1y": growth_rates["dgr_1y"],
        "dgr_3y": growth_rates["dgr_3y"],
        "dgr_5y": growth_rates["dgr_5y"],
        "dgr_10y": growth_rates["dgr_10y"],

        # Streak
        "consecutive_increases": consecutive_increases,
        "dividend_status": dividend_status,

        # Chowder number
        "chowder_number": round(chowder_number, 2),

        # Quality metrics
        "debt_to_equity": round(debt_to_equity, 4),
        "current_ratio": round(current_ratio, 2),
        "roe": round(roe, 4),
        "roa": round(roa, 4),
        "profit_margin": round(profit_margin, 4),

        # Dividend history (last 20 payments for chart)
        "dividend_history": dividend_history[-20:] if len(dividend_history) > 20 else dividend_history,

        # Full history length
        "history_years": len(set(d["date"][:4] for d in dividend_history)),
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="Fetch dividend data for income analysis")
    parser.add_argument("--ticker", required=True, help="Stock ticker symbol")
    parser.add_argument("--output", default="valuation/dividend_income/data", help="Output directory")

    args = parser.parse_args()

    try:
        data = fetch_dividend_data(args.ticker)

        # Write to file
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"dividend_data_{args.ticker}.json"

        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Dividend data written to: {output_file}")
        print("Data fetch successful!")

    except Exception as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

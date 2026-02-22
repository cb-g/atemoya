#!/usr/bin/env python3
"""Fetch growth metrics for growth investor analysis."""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf

from lib.python.retry import retry_with_backoff


def fetch_growth_data(ticker_symbol: str) -> dict:
    """Fetch comprehensive growth metrics for a ticker."""
    print(f"Fetching growth data for {ticker_symbol}...")

    ticker = yf.Ticker(ticker_symbol)
    info = retry_with_backoff(lambda: ticker.info)

    # Current price and market data
    current_price = info.get("currentPrice", info.get("regularMarketPrice", 0.0))
    market_cap = info.get("marketCap", 0) or 0
    enterprise_value = info.get("enterpriseValue", 0) or 0
    shares_outstanding = info.get("sharesOutstanding", 0) or 0

    # Revenue metrics
    revenue = info.get("totalRevenue", 0) or 0
    revenue_growth = info.get("revenueGrowth", 0.0) or 0.0
    revenue_per_share = info.get("revenuePerShare", 0.0) or 0.0

    # Earnings metrics
    trailing_eps = info.get("trailingEps", 0.0) or 0.0
    forward_eps = info.get("forwardEps", 0.0) or 0.0
    earnings_growth = info.get("earningsGrowth", 0.0) or 0.0

    # Calculate EPS growth from trailing to forward
    eps_growth_fwd = 0.0
    if trailing_eps > 0 and forward_eps > 0:
        eps_growth_fwd = (forward_eps - trailing_eps) / trailing_eps

    # Profitability margins
    gross_margin = info.get("grossMargins", 0.0) or 0.0
    operating_margin = info.get("operatingMargins", 0.0) or 0.0
    profit_margin = info.get("profitMargins", 0.0) or 0.0
    ebitda_margin = info.get("ebitdaMargins", 0.0) or 0.0

    # EBITDA
    ebitda = info.get("ebitda", 0) or 0

    # Free cash flow
    free_cashflow = info.get("freeCashflow", 0) or 0
    fcf_margin = free_cashflow / revenue if revenue > 0 else 0.0
    fcf_per_share = free_cashflow / shares_outstanding if shares_outstanding > 0 else 0.0

    # Operating cash flow
    operating_cashflow = info.get("operatingCashflow", 0) or 0

    # EV multiples
    ev_revenue = enterprise_value / revenue if revenue > 0 else 0.0
    ev_ebitda = enterprise_value / ebitda if ebitda > 0 else 0.0

    # P/E ratios
    trailing_pe = info.get("trailingPE", 0.0) or 0.0
    forward_pe = info.get("forwardPE", 0.0) or 0.0

    # Rule of 40 (Revenue Growth % + FCF Margin %)
    rule_of_40 = (revenue_growth * 100) + (fcf_margin * 100)

    # Returns
    roe = info.get("returnOnEquity", 0.0) or 0.0
    roa = info.get("returnOnAssets", 0.0) or 0.0
    roic = info.get("returnOnCapital", 0.0) or 0.0

    # Beta for risk assessment
    beta = info.get("beta", 1.0) or 1.0

    # Analyst estimates
    target_mean = info.get("targetMeanPrice", 0.0) or 0.0
    target_high = info.get("targetHighPrice", 0.0) or 0.0
    target_low = info.get("targetLowPrice", 0.0) or 0.0
    recommendation = info.get("recommendationKey", "none")
    num_analysts = info.get("numberOfAnalystOpinions", 0) or 0

    # Get historical financials for CAGR calculation
    try:
        financials = retry_with_backoff(lambda: ticker.quarterly_financials)
        if not financials.empty and "Total Revenue" in financials.index:
            revenues = financials.loc["Total Revenue"].dropna().sort_index()
            if len(revenues) >= 4:
                # YoY revenue growth (compare to 4 quarters ago)
                recent = revenues.iloc[-1]
                year_ago = revenues.iloc[-4] if len(revenues) >= 4 else revenues.iloc[0]
                if year_ago > 0:
                    revenue_growth_yoy = (recent - year_ago) / year_ago
                else:
                    revenue_growth_yoy = revenue_growth
            else:
                revenue_growth_yoy = revenue_growth
        else:
            revenue_growth_yoy = revenue_growth
    except Exception:
        revenue_growth_yoy = revenue_growth

    # Calculate revenue CAGR if we have annual data
    revenue_cagr_3y = 0.0
    try:
        annual_financials = retry_with_backoff(lambda: ticker.financials)
        if not annual_financials.empty and "Total Revenue" in annual_financials.index:
            revenues = annual_financials.loc["Total Revenue"].dropna().sort_index()
            if len(revenues) >= 3:
                start_rev = revenues.iloc[0]
                end_rev = revenues.iloc[-1]
                years = len(revenues) - 1
                if start_rev > 0 and years > 0:
                    revenue_cagr_3y = (end_rev / start_rev) ** (1.0 / years) - 1
    except Exception:
        pass

    # Sector and industry
    sector = info.get("sector", "Unknown")
    industry = info.get("industry", "Unknown")

    # Build result
    result = {
        "ticker": ticker_symbol,
        "company_name": info.get("longName", ticker_symbol),
        "sector": sector,
        "industry": industry,

        # Price and size
        "current_price": round(current_price, 2),
        "market_cap": market_cap,
        "enterprise_value": enterprise_value,
        "shares_outstanding": shares_outstanding,

        # Revenue metrics
        "revenue": revenue,
        "revenue_growth": round(revenue_growth, 4),
        "revenue_growth_yoy": round(revenue_growth_yoy, 4),
        "revenue_cagr_3y": round(revenue_cagr_3y, 4),
        "revenue_per_share": round(revenue_per_share, 2),

        # Earnings metrics
        "trailing_eps": round(trailing_eps, 2),
        "forward_eps": round(forward_eps, 2),
        "earnings_growth": round(earnings_growth, 4),
        "eps_growth_fwd": round(eps_growth_fwd, 4),

        # Margins
        "gross_margin": round(gross_margin, 4),
        "operating_margin": round(operating_margin, 4),
        "ebitda_margin": round(ebitda_margin, 4),
        "profit_margin": round(profit_margin, 4),
        "fcf_margin": round(fcf_margin, 4),

        # Cash flows
        "ebitda": ebitda,
        "free_cashflow": free_cashflow,
        "operating_cashflow": operating_cashflow,
        "fcf_per_share": round(fcf_per_share, 2),

        # Multiples
        "ev_revenue": round(ev_revenue, 2),
        "ev_ebitda": round(ev_ebitda, 2),
        "trailing_pe": round(trailing_pe, 2),
        "forward_pe": round(forward_pe, 2),

        # Growth efficiency
        "rule_of_40": round(rule_of_40, 1),

        # Returns
        "roe": round(roe, 4),
        "roa": round(roa, 4),
        "roic": round(roic, 4),

        # Risk
        "beta": round(beta, 2),

        # Analyst data
        "analyst_target_mean": round(target_mean, 2),
        "analyst_target_high": round(target_high, 2),
        "analyst_target_low": round(target_low, 2),
        "analyst_recommendation": recommendation,
        "num_analysts": num_analysts,
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="Fetch growth data for analysis")
    parser.add_argument("--ticker", required=True, help="Stock ticker symbol")
    parser.add_argument("--output", default="valuation/growth_analysis/data", help="Output directory")

    args = parser.parse_args()

    try:
        data = fetch_growth_data(args.ticker)

        # Write to file
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"growth_data_{args.ticker}.json"

        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Growth data written to: {output_file}")
        print("Data fetch successful!")

    except Exception as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

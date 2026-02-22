#!/usr/bin/env python3
"""Fetch peer company data for relative valuation analysis."""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf

from lib.python.retry import retry_with_backoff


def fetch_company_data(ticker_symbol: str) -> dict | None:
    """Fetch key metrics for a single company."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = retry_with_backoff(lambda: ticker.info)

        if not info or "currentPrice" not in info and "regularMarketPrice" not in info:
            print(f"Warning: Could not fetch data for {ticker_symbol}")
            return None

        # Current price and market cap
        current_price = info.get("currentPrice", info.get("regularMarketPrice", 0.0))
        market_cap = info.get("marketCap", 0) or 0
        shares_outstanding = info.get("sharesOutstanding", 0) or 0

        # Enterprise value components
        total_debt = info.get("totalDebt", 0) or 0
        total_cash = info.get("totalCash", 0) or 0
        enterprise_value = info.get("enterpriseValue", 0) or 0

        # If EV not available, calculate it
        if enterprise_value == 0 and market_cap > 0:
            enterprise_value = market_cap + total_debt - total_cash

        # Earnings metrics
        trailing_eps = info.get("trailingEps", 0.0) or 0.0
        forward_eps = info.get("forwardEps", 0.0) or 0.0
        trailing_pe = info.get("trailingPE", 0.0) or 0.0
        forward_pe = info.get("forwardPE", 0.0) or 0.0

        # Book value
        book_value = info.get("bookValue", 0.0) or 0.0
        pb_ratio = info.get("priceToBook", 0.0) or 0.0

        # Revenue and sales
        revenue = info.get("totalRevenue", 0) or 0
        revenue_per_share = info.get("revenuePerShare", 0.0) or 0.0
        ps_ratio = info.get("priceToSalesTrailing12Months", 0.0) or 0.0

        # Free cash flow
        free_cashflow = info.get("freeCashflow", 0) or 0
        fcf_per_share = free_cashflow / shares_outstanding if shares_outstanding > 0 else 0.0
        p_fcf = current_price / fcf_per_share if fcf_per_share > 0 else 0.0

        # EBITDA
        ebitda = info.get("ebitda", 0) or 0
        ev_ebitda = enterprise_value / ebitda if ebitda > 0 else 0.0

        # Operating income (EBIT proxy)
        operating_income = info.get("operatingIncome", 0) or 0
        ev_ebit = enterprise_value / operating_income if operating_income > 0 else 0.0

        # EV/Revenue
        ev_revenue = enterprise_value / revenue if revenue > 0 else 0.0

        # Growth metrics
        revenue_growth = info.get("revenueGrowth", 0.0) or 0.0
        earnings_growth = info.get("earningsGrowth", 0.0) or 0.0

        # Profitability
        gross_margin = info.get("grossMargins", 0.0) or 0.0
        operating_margin = info.get("operatingMargins", 0.0) or 0.0
        profit_margin = info.get("profitMargins", 0.0) or 0.0
        ebitda_margin = ebitda / revenue if revenue > 0 else 0.0

        # Returns
        roe = info.get("returnOnEquity", 0.0) or 0.0
        roa = info.get("returnOnAssets", 0.0) or 0.0
        roic = info.get("returnOnCapital", 0.0) or 0.0

        # Sector and industry
        sector = info.get("sector", "Unknown")
        industry = info.get("industry", "Unknown")

        # Beta
        beta = info.get("beta", 1.0) or 1.0

        # Dividend
        dividend_yield = info.get("dividendYield", 0.0) or 0.0

        return {
            "ticker": ticker_symbol,
            "company_name": info.get("longName", ticker_symbol),
            "sector": sector,
            "industry": industry,

            # Size metrics
            "current_price": round(current_price, 2),
            "market_cap": market_cap,
            "enterprise_value": enterprise_value,
            "shares_outstanding": shares_outstanding,

            # EPS and P/E
            "trailing_eps": round(trailing_eps, 2),
            "forward_eps": round(forward_eps, 2),
            "trailing_pe": round(trailing_pe, 2),
            "forward_pe": round(forward_pe, 2),

            # Book value
            "book_value": round(book_value, 2),
            "pb_ratio": round(pb_ratio, 2),

            # Revenue
            "revenue": revenue,
            "revenue_per_share": round(revenue_per_share, 2),
            "ps_ratio": round(ps_ratio, 2),

            # FCF
            "free_cashflow": free_cashflow,
            "fcf_per_share": round(fcf_per_share, 2),
            "p_fcf": round(p_fcf, 2),

            # EBITDA and EV multiples
            "ebitda": ebitda,
            "operating_income": operating_income,
            "ev_ebitda": round(ev_ebitda, 2),
            "ev_ebit": round(ev_ebit, 2),
            "ev_revenue": round(ev_revenue, 2),

            # Growth
            "revenue_growth": round(revenue_growth, 4),
            "earnings_growth": round(earnings_growth, 4),

            # Margins
            "gross_margin": round(gross_margin, 4),
            "operating_margin": round(operating_margin, 4),
            "ebitda_margin": round(ebitda_margin, 4),
            "profit_margin": round(profit_margin, 4),

            # Returns
            "roe": round(roe, 4),
            "roa": round(roa, 4),
            "roic": round(roic, 4),

            # Other
            "beta": round(beta, 2),
            "dividend_yield": round(dividend_yield, 4),
        }

    except Exception as e:
        print(f"Error fetching {ticker_symbol}: {e}")
        return None


def fetch_peer_group(target: str, peers: list[str]) -> dict:
    """Fetch data for target and all peers."""
    print(f"Fetching data for {target} and {len(peers)} peers...")

    # Fetch target
    target_data = fetch_company_data(target)
    if not target_data:
        print(f"Error: Could not fetch target {target}")
        sys.exit(1)

    # Fetch peers
    peer_data = []
    for peer in peers:
        data = fetch_company_data(peer)
        if data:
            peer_data.append(data)
        else:
            print(f"  Skipping {peer} - no data available")

    return {
        "target": target_data,
        "peers": peer_data,
        "peer_count": len(peer_data),
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch peer data for relative valuation")
    parser.add_argument("--target", required=True, help="Target ticker to analyze")
    parser.add_argument("--peers", required=True, help="Comma-separated list of peer tickers")
    parser.add_argument("--output", default="valuation/relative_valuation/data", help="Output directory")

    args = parser.parse_args()

    peers = [p.strip() for p in args.peers.split(",")]

    data = fetch_peer_group(args.target, peers)

    # Write to file
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"peer_data_{args.target}.json"

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Peer data written to: {output_file}")
    print(f"Fetched {data['peer_count']} peers successfully")


if __name__ == "__main__":
    main()

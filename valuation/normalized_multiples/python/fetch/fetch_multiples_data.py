#!/usr/bin/env python3
"""
Fetch normalized multiples data with explicit time window labeling.
Eliminates confusion about what period each multiple represents.

Usage:
    python fetch_multiples_data.py --ticker AAPL [--output data/]
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


def fetch_multiples_data(ticker_symbol: str) -> dict:
    """Fetch all multiples with explicit time window labeling."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = retry_with_backoff(lambda: ticker.info)

        if not info or "currentPrice" not in info and "regularMarketPrice" not in info:
            return {"ticker": ticker_symbol, "error": "No data available"}

        # Basic data
        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
        market_cap = info.get("marketCap") or 0.0
        shares = info.get("sharesOutstanding") or 0.0

        # Enterprise value calculation
        total_debt = info.get("totalDebt") or 0.0
        total_cash = info.get("totalCash") or 0.0
        ev = info.get("enterpriseValue") or (market_cap + total_debt - total_cash)

        # TTM (Trailing) metrics
        eps_ttm = info.get("trailingEps") or 0.0
        pe_ttm = info.get("trailingPE") or 0.0

        # NTM (Forward) metrics - consensus estimates
        eps_ntm = info.get("forwardEps") or 0.0
        pe_ntm = info.get("forwardPE") or 0.0

        # Revenue and P/S
        revenue = info.get("totalRevenue") or 0.0
        ps_ttm = info.get("priceToSalesTrailing12Months") or 0.0
        revenue_per_share = revenue / shares if shares > 0 else 0.0

        # Book value and P/B
        book_value = info.get("bookValue") or 0.0
        pb_ttm = info.get("priceToBook") or 0.0

        # FCF and P/FCF
        fcf = info.get("freeCashflow") or 0.0
        fcf_per_share = fcf / shares if shares > 0 else 0.0
        p_fcf_ttm = price / fcf_per_share if fcf_per_share > 0 else 0.0

        # EBITDA and EV/EBITDA
        ebitda = info.get("ebitda") or 0.0
        ev_ebitda_ttm = info.get("enterpriseToEbitda") or 0.0

        # EBIT (operating income) and EV/EBIT
        ebit = info.get("operatingIncome") or 0.0
        ev_ebit_ttm = ev / ebit if ebit > 0 else 0.0

        # EV/Sales
        ev_sales_ttm = info.get("enterpriseToRevenue") or 0.0

        # EV/FCF
        ev_fcf_ttm = ev / fcf if fcf > 0 else 0.0

        # Growth rates
        revenue_growth = info.get("revenueGrowth") or 0.0
        earnings_growth = info.get("earningsGrowth") or 0.0

        # Get better growth estimate from analyst data
        eps_growth_ntm = 0.0
        try:
            growth_est = retry_with_backoff(lambda: ticker.growth_estimates)
            if growth_est is not None and not growth_est.empty:
                # Use next year growth estimate
                if "+1y" in growth_est.index:
                    val = growth_est.loc["+1y", "stockTrend"]
                    eps_growth_ntm = float(val) if val is not None and val == val else 0.0  # NaN check
                elif "0y" in growth_est.index:
                    val = growth_est.loc["0y", "stockTrend"]
                    eps_growth_ntm = float(val) if val is not None and val == val else 0.0
        except Exception:
            eps_growth_ntm = 0.0

        # PEG ratio - try multiple sources
        peg = float(info.get("pegRatio") or info.get("trailingPegRatio") or 0.0)

        # If still no PEG but we have forward P/E and growth, calculate it
        if peg == 0 and pe_ntm > 0 and eps_growth_ntm > 0:
            peg = pe_ntm / (eps_growth_ntm * 100)  # growth is decimal, need percentage
        elif peg == 0 and pe_ntm > 0 and earnings_growth > 0:
            peg = pe_ntm / (earnings_growth * 100)

        # Margins
        gross_margin = info.get("grossMargins") or 0.0
        operating_margin = info.get("operatingMargins") or 0.0
        ebitda_margin = ebitda / revenue if revenue > 0 else 0.0

        # Returns
        roe = info.get("returnOnEquity") or 0.0
        roic = info.get("returnOnCapital") or 0.0

        return {
            "ticker": ticker_symbol,
            "company_name": info.get("longName") or ticker_symbol,
            "sector": info.get("sector") or "Unknown",
            "industry": info.get("industry") or "Unknown",
            "current_price": round(price, 2),
            "market_cap": market_cap,
            "enterprise_value": ev,
            "shares_outstanding": shares,
            # P/E with explicit time windows
            "pe_ttm": {
                "name": "P/E",
                "time_window": "TTM",
                "value": round(pe_ttm, 2) if pe_ttm else 0.0,
                "underlying_metric": round(eps_ttm, 2),
                "is_valid": eps_ttm > 0,
            },
            "pe_ntm": {
                "name": "P/E",
                "time_window": "NTM",
                "value": round(pe_ntm, 2) if pe_ntm else 0.0,
                "underlying_metric": round(eps_ntm, 2),
                "is_valid": eps_ntm > 0,
            },
            # P/S
            "ps_ttm": {
                "name": "P/S",
                "time_window": "TTM",
                "value": round(ps_ttm, 2) if ps_ttm else 0.0,
                "underlying_metric": round(revenue_per_share, 2),
                "is_valid": revenue > 0,
            },
            # P/B
            "pb_ttm": {
                "name": "P/B",
                "time_window": "TTM",
                "value": round(pb_ttm, 2) if pb_ttm else 0.0,
                "underlying_metric": round(book_value, 2),
                "is_valid": book_value > 0,
            },
            # P/FCF
            "p_fcf_ttm": {
                "name": "P/FCF",
                "time_window": "TTM",
                "value": round(p_fcf_ttm, 2) if p_fcf_ttm > 0 else 0.0,
                "underlying_metric": round(fcf_per_share, 2),
                "is_valid": fcf > 0,
            },
            # PEG (uses forward growth, so NTM)
            "peg_ratio": {
                "name": "PEG",
                "time_window": "NTM",
                "value": round(peg, 2) if peg else 0.0,
                "underlying_metric": round((eps_growth_ntm or earnings_growth) * 100, 2),
                "is_valid": peg > 0 and (eps_growth_ntm > 0 or earnings_growth > 0),
            },
            # EV/EBITDA
            "ev_ebitda_ttm": {
                "name": "EV/EBITDA",
                "time_window": "TTM",
                "value": round(ev_ebitda_ttm, 2) if ev_ebitda_ttm else 0.0,
                "underlying_metric": round(ebitda, 0),
                "is_valid": ebitda > 0,
            },
            # EV/EBIT
            "ev_ebit_ttm": {
                "name": "EV/EBIT",
                "time_window": "TTM",
                "value": round(ev_ebit_ttm, 2) if ev_ebit_ttm > 0 else 0.0,
                "underlying_metric": round(ebit, 0),
                "is_valid": ebit > 0,
            },
            # EV/Sales
            "ev_sales_ttm": {
                "name": "EV/Sales",
                "time_window": "TTM",
                "value": round(ev_sales_ttm, 2) if ev_sales_ttm else 0.0,
                "underlying_metric": round(revenue, 0),
                "is_valid": revenue > 0,
            },
            # EV/FCF
            "ev_fcf_ttm": {
                "name": "EV/FCF",
                "time_window": "TTM",
                "value": round(ev_fcf_ttm, 2) if ev_fcf_ttm > 0 else 0.0,
                "underlying_metric": round(fcf, 0),
                "is_valid": fcf > 0,
            },
            # Growth and quality metrics
            "revenue_growth_ttm": round(revenue_growth, 4),
            "eps_growth_ttm": round(earnings_growth, 4),
            "eps_growth_ntm": round(eps_growth_ntm if eps_growth_ntm > 0 else earnings_growth, 4),
            "gross_margin": round(gross_margin, 4),
            "operating_margin": round(operating_margin, 4),
            "ebitda_margin": round(ebitda_margin, 4),
            "roe": round(roe, 4),
            "roic": round(roic, 4),
            "fetch_time": datetime.now().isoformat(),
        }

    except Exception as e:
        return {"ticker": ticker_symbol, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Fetch normalized multiples data")
    parser.add_argument("--ticker", required=True, help="Ticker symbol")
    parser.add_argument(
        "--output",
        default="valuation/normalized_multiples/data",
        help="Output directory",
    )
    args = parser.parse_args()

    ticker = args.ticker.upper()
    print(f"Fetching multiples for {ticker}...", end=" ", flush=True)

    data = fetch_multiples_data(ticker)

    if "error" in data:
        print(f"ERROR: {data['error']}")
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"multiples_data_{ticker}.json"

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"OK")
    print(f"  Price: ${data['current_price']:.2f}")
    print(f"  P/E (TTM): {data['pe_ttm']['value']:.1f}x")
    print(f"  P/E (NTM): {data['pe_ntm']['value']:.1f}x")
    print(f"  EV/EBITDA (TTM): {data['ev_ebitda_ttm']['value']:.1f}x")
    print(f"  Data written to: {output_file}")


if __name__ == "__main__":
    main()

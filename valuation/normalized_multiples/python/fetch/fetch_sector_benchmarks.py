#!/usr/bin/env python3
"""
Fetch sector benchmark data by sampling major companies in each sector.
Calculates median, 25th, and 75th percentiles for all multiples.

Usage:
    python fetch_sector_benchmarks.py --sector Technology
    python fetch_sector_benchmarks.py --sector all
"""

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf

from lib.python.retry import retry_with_backoff

# S&P 500 sector representatives (10 per sector)
SECTOR_TICKERS = {
    "Technology": [
        "AAPL", "MSFT", "NVDA", "AVGO", "CRM",
        "ADBE", "AMD", "INTC", "CSCO", "IBM",
    ],
    "Healthcare": [
        "UNH", "JNJ", "LLY", "PFE", "ABBV",
        "MRK", "TMO", "ABT", "DHR", "BMY",
    ],
    "Financials": [
        "BRK-B", "JPM", "V", "MA", "BAC",
        "WFC", "GS", "MS", "SPGI", "BLK",
    ],
    "Consumer Discretionary": [
        "AMZN", "TSLA", "HD", "MCD", "NKE",
        "SBUX", "LOW", "TJX", "BKNG", "CMG",
    ],
    "Communication Services": [
        "GOOGL", "META", "NFLX", "DIS", "CMCSA",
        "VZ", "T", "TMUS", "CHTR", "EA",
    ],
    "Industrials": [
        "GE", "CAT", "HON", "UNP", "BA",
        "RTX", "DE", "LMT", "MMM", "UPS",
    ],
    "Consumer Staples": [
        "PG", "KO", "PEP", "COST", "WMT",
        "PM", "MO", "CL", "MDLZ", "KHC",
    ],
    "Energy": [
        "XOM", "CVX", "COP", "EOG", "SLB",
        "MPC", "PSX", "VLO", "OXY", "HAL",
    ],
    "Utilities": [
        "NEE", "DUK", "SO", "D", "AEP",
        "SRE", "EXC", "XEL", "ED", "WEC",
    ],
    "Real Estate": [
        "PLD", "AMT", "EQIX", "PSA", "CCI",
        "O", "WELL", "SPG", "DLR", "AVB",
    ],
    "Materials": [
        "LIN", "APD", "SHW", "ECL", "DD",
        "NEM", "FCX", "NUE", "VMC", "MLM",
    ],
}


def calculate_percentiles(values: list[float]) -> dict:
    """Calculate median, p25, p75 from a list of values."""
    if len(values) < 3:
        return {"median": 0.0, "p25": 0.0, "p75": 0.0, "count": 0}

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    return {
        "median": round(statistics.median(sorted_vals), 2),
        "p25": round(sorted_vals[n // 4], 2),
        "p75": round(sorted_vals[3 * n // 4], 2),
        "count": n,
    }


def fetch_sector_benchmarks(sector: str, tickers: list[str]) -> dict:
    """Calculate benchmark statistics for a sector."""
    multiples = {
        "pe_ttm": [],
        "pe_ntm": [],
        "ps": [],
        "pb": [],
        "p_fcf": [],
        "peg": [],
        "ev_ebitda": [],
        "ev_ebit": [],
        "ev_sales": [],
        "ev_fcf": [],
        "revenue_growth": [],
        "ebitda_margin": [],
        "roe": [],
    }

    successful = 0
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = retry_with_backoff(lambda: t.info)
            time.sleep(0.2)  # Rate limiting

            # P/E
            if (pe := info.get("trailingPE")) and 0 < pe < 200:
                multiples["pe_ttm"].append(pe)
            if (pe_fwd := info.get("forwardPE")) and 0 < pe_fwd < 200:
                multiples["pe_ntm"].append(pe_fwd)

            # P/S
            if (ps := info.get("priceToSalesTrailing12Months")) and 0 < ps < 100:
                multiples["ps"].append(ps)

            # P/B
            if (pb := info.get("priceToBook")) and 0 < pb < 100:
                multiples["pb"].append(pb)

            # P/FCF (calculated)
            fcf = info.get("freeCashflow") or 0
            shares = info.get("sharesOutstanding") or 0
            price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
            if fcf > 0 and shares > 0 and price > 0:
                p_fcf = price / (fcf / shares)
                if 0 < p_fcf < 200:
                    multiples["p_fcf"].append(p_fcf)

            # PEG
            if (peg := info.get("pegRatio")) and 0 < peg < 10:
                multiples["peg"].append(peg)

            # EV/EBITDA
            if (ev_ebitda := info.get("enterpriseToEbitda")) and 0 < ev_ebitda < 100:
                multiples["ev_ebitda"].append(ev_ebitda)

            # EV/EBIT (calculated)
            ev = info.get("enterpriseValue") or 0
            ebit = info.get("operatingIncome") or 0
            if ev > 0 and ebit > 0:
                ev_ebit = ev / ebit
                if 0 < ev_ebit < 100:
                    multiples["ev_ebit"].append(ev_ebit)

            # EV/Sales
            if (ev_sales := info.get("enterpriseToRevenue")) and 0 < ev_sales < 50:
                multiples["ev_sales"].append(ev_sales)

            # EV/FCF (calculated)
            if ev > 0 and fcf > 0:
                ev_fcf = ev / fcf
                if 0 < ev_fcf < 200:
                    multiples["ev_fcf"].append(ev_fcf)

            # Revenue growth
            if (rg := info.get("revenueGrowth")) and -0.5 < rg < 2:
                multiples["revenue_growth"].append(rg)

            # EBITDA margin (calculated)
            ebitda = info.get("ebitda") or 0
            revenue = info.get("totalRevenue") or 0
            if ebitda > 0 and revenue > 0:
                margin = ebitda / revenue
                if 0 < margin < 1:
                    multiples["ebitda_margin"].append(margin)

            # ROE
            if (roe := info.get("returnOnEquity")) and -0.5 < roe < 1:
                multiples["roe"].append(roe)

            successful += 1

        except Exception as e:
            print(f"  Warning: Could not fetch {ticker}: {e}")

    # Calculate percentiles for each multiple
    pe_ttm = calculate_percentiles(multiples["pe_ttm"])
    pe_ntm = calculate_percentiles(multiples["pe_ntm"])
    ps = calculate_percentiles(multiples["ps"])
    pb = calculate_percentiles(multiples["pb"])
    p_fcf = calculate_percentiles(multiples["p_fcf"])
    peg = calculate_percentiles(multiples["peg"])
    ev_ebitda = calculate_percentiles(multiples["ev_ebitda"])
    ev_ebit = calculate_percentiles(multiples["ev_ebit"])
    ev_sales = calculate_percentiles(multiples["ev_sales"])
    ev_fcf = calculate_percentiles(multiples["ev_fcf"])
    revenue_growth = calculate_percentiles(multiples["revenue_growth"])
    ebitda_margin = calculate_percentiles(multiples["ebitda_margin"])
    roe = calculate_percentiles(multiples["roe"])

    return {
        "sector": sector,
        "industry": None,
        "sample_size": successful,
        "tickers_sampled": tickers,
        "fetch_time": datetime.now().isoformat(),
        # P/E
        "pe_ttm_median": pe_ttm["median"],
        "pe_ttm_p25": pe_ttm["p25"],
        "pe_ttm_p75": pe_ttm["p75"],
        "pe_ntm_median": pe_ntm["median"],
        "pe_ntm_p25": pe_ntm["p25"],
        "pe_ntm_p75": pe_ntm["p75"],
        # Other price multiples
        "ps_median": ps["median"],
        "ps_p25": ps["p25"],
        "ps_p75": ps["p75"],
        "pb_median": pb["median"],
        "pb_p25": pb["p25"],
        "pb_p75": pb["p75"],
        "p_fcf_median": p_fcf["median"],
        "p_fcf_p25": p_fcf["p25"],
        "p_fcf_p75": p_fcf["p75"],
        "peg_median": peg["median"],
        "peg_p25": peg["p25"],
        "peg_p75": peg["p75"],
        # EV multiples
        "ev_ebitda_median": ev_ebitda["median"],
        "ev_ebitda_p25": ev_ebitda["p25"],
        "ev_ebitda_p75": ev_ebitda["p75"],
        "ev_ebit_median": ev_ebit["median"],
        "ev_sales_median": ev_sales["median"],
        "ev_fcf_median": ev_fcf["median"],
        # Quality metrics
        "revenue_growth_median": round(revenue_growth["median"], 4),
        "ebitda_margin_median": round(ebitda_margin["median"], 4),
        "roe_median": round(roe["median"], 4),
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch sector benchmarks")
    parser.add_argument(
        "--sector",
        default="all",
        help="Sector name or 'all' for all sectors",
    )
    parser.add_argument(
        "--output",
        default="valuation/normalized_multiples/data/sector_benchmarks",
        help="Output directory",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.sector.lower() == "all":
        sectors = list(SECTOR_TICKERS.keys())
    else:
        # Find matching sector (case-insensitive)
        sectors = [s for s in SECTOR_TICKERS if s.lower() == args.sector.lower()]
        if not sectors:
            print(f"Unknown sector: {args.sector}")
            print(f"Available sectors: {', '.join(SECTOR_TICKERS.keys())}")
            return

    for sector in sectors:
        print(f"\nCalculating benchmarks for {sector}...")
        tickers = SECTOR_TICKERS[sector]

        benchmarks = fetch_sector_benchmarks(sector, tickers)

        output_file = output_dir / f"benchmark_{sector.replace(' ', '_')}.json"
        with open(output_file, "w") as f:
            json.dump(benchmarks, f, indent=2)

        print(f"  Sample size: {benchmarks['sample_size']}/{len(tickers)}")
        print(f"  P/E (TTM) median: {benchmarks['pe_ttm_median']:.1f}x")
        print(f"  EV/EBITDA median: {benchmarks['ev_ebitda_median']:.1f}x")
        print(f"  Written to: {output_file}")


if __name__ == "__main__":
    main()

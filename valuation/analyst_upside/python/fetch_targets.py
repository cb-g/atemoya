#!/usr/bin/env python3
"""Analyst price target scanner - find biggest upside opportunities."""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import warnings

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[3]))

import yfinance as yf

from lib.python.retry import retry_with_backoff

warnings.filterwarnings('ignore')

# Common universes
SP500_TOP50 = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK-B', 'UNH', 'JNJ',
    'JPM', 'V', 'XOM', 'PG', 'MA', 'HD', 'CVX', 'MRK', 'ABBV', 'LLY',
    'PEP', 'KO', 'COST', 'AVGO', 'WMT', 'MCD', 'CSCO', 'TMO', 'ACN', 'ABT',
    'DHR', 'NEE', 'VZ', 'ADBE', 'CMCSA', 'NKE', 'PM', 'TXN', 'WFC', 'BMY',
    'COP', 'RTX', 'UPS', 'HON', 'ORCL', 'QCOM', 'LOW', 'INTC', 'IBM', 'SPGI',
]

NASDAQ_TOP30 = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO', 'COST', 'ADBE',
    'CSCO', 'PEP', 'NFLX', 'AMD', 'INTC', 'CMCSA', 'TXN', 'QCOM', 'AMGN', 'INTU',
    'TMUS', 'ISRG', 'HON', 'SBUX', 'AMAT', 'BKNG', 'GILD', 'ADP', 'MDLZ', 'LRCX',
]

INCOME_ETF_UNDERLYINGS = [
    'SPY', 'QQQ', 'NVDA', 'TSLA', 'COIN', 'AMZN', 'MSTR', 'AAPL', 'GOOGL', 'META', 'MSFT',
]

# Index-based
DOW30 = [
    'AAPL', 'AMGN', 'AMZN', 'AXP', 'BA', 'CAT', 'CRM', 'CSCO', 'CVX', 'DIS',
    'GS', 'HD', 'HON', 'IBM', 'INTC', 'JNJ', 'JPM', 'KO', 'MCD', 'MMM',
    'MRK', 'MSFT', 'NKE', 'PG', 'SHW', 'TRV', 'UNH', 'V', 'VZ', 'WMT',
]

# Sector-based
SECTOR_TECH = [
    'AAPL', 'MSFT', 'NVDA', 'AVGO', 'ADBE', 'CRM', 'ORCL', 'CSCO', 'AMD', 'INTC',
    'TXN', 'QCOM', 'AMAT', 'LRCX', 'INTU', 'NOW', 'SNPS', 'CDNS', 'PANW', 'FTNT',
]

SECTOR_HEALTHCARE = [
    'UNH', 'JNJ', 'LLY', 'ABBV', 'MRK', 'TMO', 'ABT', 'PFE', 'DHR', 'BMY',
    'AMGN', 'GILD', 'ISRG', 'VRTX', 'MDT', 'SYK', 'BSX', 'CI', 'ELV', 'HCA',
]

SECTOR_INDUSTRIALS = [
    'CAT', 'DE', 'GE', 'HON', 'RTX', 'UPS', 'BA', 'LMT', 'MMM', 'EMR',
    'ITW', 'ETN', 'FDX', 'NSC', 'WM', 'GD', 'NOC', 'TT', 'PH', 'CARR',
]

SECTOR_CONSUMER = [
    'AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'LOW', 'TJX', 'BKNG', 'CMG',
    'COST', 'WMT', 'PG', 'KO', 'PEP', 'PM', 'CL', 'MDLZ', 'EL', 'SYY',
]

SECTOR_FINANCIALS = [
    'JPM', 'V', 'MA', 'BAC', 'WFC', 'GS', 'MS', 'SPGI', 'BLK', 'C',
    'AXP', 'SCHW', 'CME', 'ICE', 'CB', 'MMC', 'AON', 'PGR', 'TFC', 'USB',
]

SECTOR_ENERGY = [
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'OXY', 'WMB',
    'PXD', 'DVN', 'HES', 'HAL', 'FANG', 'KMI', 'BKR', 'CTRA', 'OKE', 'TRGP',
]

# Thematic
THEME_AI = [
    'NVDA', 'MSFT', 'GOOGL', 'META', 'AMD', 'AVGO', 'PLTR', 'SNOW', 'AI', 'PATH',
    'SMCI', 'ARM', 'MRVL', 'CDNS', 'SNPS', 'DDOG', 'MDB', 'CRWD', 'NET', 'ABNB',
]

THEME_CLEAN_ENERGY = [
    'NEE', 'ENPH', 'SEDG', 'FSLR', 'RUN', 'PLUG', 'BE', 'NOVA', 'CSIQ', 'JKS',
    'DQ', 'ARRY', 'STEM', 'CHPT', 'BLNK', 'RIVN', 'LCID', 'QS', 'NIO', 'XPEV',
]

THEME_DIVIDEND_ARISTOCRATS = [
    'JNJ', 'PG', 'KO', 'PEP', 'MMM', 'ABT', 'ABBV', 'MCD', 'CL', 'EMR',
    'XOM', 'CVX', 'ITW', 'GD', 'SHW', 'ADP', 'BDX', 'CAH', 'ED', 'SWK',
]

# Market-cap tiers
MIDCAP_PICKS = [
    'DECK', 'TOL', 'BURL', 'WSM', 'FND', 'WFRD', 'SKX', 'MOD', 'CASY', 'LNTH',
    'PSTG', 'FIX', 'IBP', 'RGLD', 'TTEK', 'KNSL', 'ELF', 'DUOL', 'CWAN', 'TXRH',
]

SMALLCAP_PICKS = [
    'RMBS', 'CORT', 'KTOS', 'BOOT', 'LBRT', 'CALM', 'POWL', 'CPRX', 'AEHR', 'INTA',
    'BROS', 'SHAK', 'DOCS', 'TMDX', 'KRYS', 'OSCR', 'RVMD', 'GERN', 'AROC', 'TGTX',
]

UNIVERSES = {
    # Index-based
    'sp50': SP500_TOP50,
    'nasdaq30': NASDAQ_TOP30,
    'dow30': DOW30,
    # Sector-based
    'tech': SECTOR_TECH,
    'healthcare': SECTOR_HEALTHCARE,
    'industrials': SECTOR_INDUSTRIALS,
    'consumer': SECTOR_CONSUMER,
    'financials': SECTOR_FINANCIALS,
    'energy': SECTOR_ENERGY,
    # Thematic
    'ai': THEME_AI,
    'clean_energy': THEME_CLEAN_ENERGY,
    'div_aristocrats': THEME_DIVIDEND_ARISTOCRATS,
    'income': INCOME_ETF_UNDERLYINGS,
    # Market-cap tiers
    'midcap': MIDCAP_PICKS,
    'smallcap': SMALLCAP_PICKS,
}


def fetch_single_target(ticker: str) -> dict | None:
    """Fetch analyst price target data for a single ticker."""
    try:
        stock = yf.Ticker(ticker)
        info = retry_with_backoff(lambda: stock.info)

        current_price = info.get('currentPrice') or info.get('regularMarketPrice')
        if current_price is None:
            return None

        # Get price targets
        targets = retry_with_backoff(lambda: stock.analyst_price_targets)
        if targets is None or not isinstance(targets, dict):
            # Fallback to info dict
            target_mean = info.get('targetMeanPrice')
            target_median = info.get('targetMedianPrice')
            target_low = info.get('targetLowPrice')
            target_high = info.get('targetHighPrice')
            num_analysts = info.get('numberOfAnalystOpinions', 0)
        else:
            target_mean = targets.get('mean')
            target_median = targets.get('median')
            target_low = targets.get('low')
            target_high = targets.get('high')
            num_analysts = info.get('numberOfAnalystOpinions', 0)

        if target_mean is None and target_median is None:
            return None

        target = target_median or target_mean

        # Calculate upside
        upside = (target - current_price) / current_price if current_price > 0 else 0

        # Calculate dispersion (how much analysts disagree)
        dispersion = None
        if target_low and target_high and target_mean and target_mean > 0:
            dispersion = (target_high - target_low) / target_mean

        # 52-week range position
        week52_low = info.get('fiftyTwoWeekLow')
        week52_high = info.get('fiftyTwoWeekHigh')
        week52_pct = None
        if week52_low and week52_high and week52_high > week52_low:
            week52_pct = (current_price - week52_low) / (week52_high - week52_low)

        # Recommendation
        recommendation = info.get('recommendationKey', 'N/A')

        return {
            'ticker': ticker,
            'name': info.get('shortName', ticker),
            'current_price': current_price,
            'target_mean': target_mean,
            'target_median': target_median,
            'target_low': target_low,
            'target_high': target_high,
            'upside': upside,
            'num_analysts': num_analysts,
            'dispersion': dispersion,
            'week52_low': week52_low,
            'week52_high': week52_high,
            'week52_pct': week52_pct,
            'recommendation': recommendation,
            'market_cap': info.get('marketCap'),
            'sector': info.get('sector', 'N/A'),
        }
    except Exception as e:
        return None


def fetch_all_targets(tickers: list[str], max_workers: int = 10) -> list[dict]:
    """Fetch targets for multiple tickers in parallel."""
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {executor.submit(fetch_single_target, t): t for t in tickers}

        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
                    print(f"  Fetched {ticker}: {result['upside']*100:+.1f}% upside")
                else:
                    print(f"  Skipped {ticker}: no target data")
            except Exception as e:
                print(f"  Error {ticker}: {e}")

    return results


def format_market_cap(cap: float | None) -> str:
    """Format market cap for display."""
    if cap is None:
        return "N/A"
    if cap >= 1e12:
        return f"${cap/1e12:.1f}T"
    if cap >= 1e9:
        return f"${cap/1e9:.0f}B"
    if cap >= 1e6:
        return f"${cap/1e6:.0f}M"
    return f"${cap:.0f}"


def main():
    parser = argparse.ArgumentParser(description="Analyst price target scanner")
    parser.add_argument("--tickers", "-t", help="Comma-separated list of tickers")
    parser.add_argument("--universe", "-u", choices=list(UNIVERSES.keys()),
                        help="Predefined universe to scan")
    parser.add_argument("--min-analysts", type=int, default=5,
                        help="Minimum number of analysts (default: 5)")
    parser.add_argument("--min-upside", type=float, default=0,
                        help="Minimum upside %% to display (default: 0)")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--top", type=int, default=50, help="Show top N results (default: 50)")

    args = parser.parse_args()

    # Determine tickers to scan
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]
    elif args.universe:
        tickers = UNIVERSES[args.universe]
    else:
        # Default to combined universe
        tickers = list(set(SP500_TOP50 + NASDAQ_TOP30))

    print()
    print(f"ANALYST PRICE TARGET SCANNER")
    print(f"=" * 80)
    print(f"Scanning {len(tickers)} tickers...")
    print()

    # Fetch data
    results = fetch_all_targets(tickers)

    # Filter
    filtered = [r for r in results
                if r['num_analysts'] >= args.min_analysts
                and r['upside'] * 100 >= args.min_upside]

    # Sort by upside descending
    filtered.sort(key=lambda x: x['upside'], reverse=True)

    # Limit to top N
    filtered = filtered[:args.top]

    # Display
    print()
    print(f"=" * 120)
    print(f"TOP ANALYST UPSIDE OPPORTUNITIES (min {args.min_analysts} analysts)")
    print(f"=" * 120)
    print()
    print(f"{'Ticker':<7} {'Price':>8} {'Target':>8} {'Upside':>8} {'Analysts':>8} {'Dispersion':>10} {'52wk%':>7} {'MCap':>8} {'Rec':<12}")
    print("-" * 120)

    for r in filtered:
        dispersion_str = f"{r['dispersion']:.2f}" if r['dispersion'] else "N/A"
        week52_str = f"{r['week52_pct']*100:.0f}%" if r['week52_pct'] is not None else "N/A"
        mcap_str = format_market_cap(r['market_cap'])

        # Color coding via symbols
        if r['upside'] >= 0.30:
            upside_indicator = "***"
        elif r['upside'] >= 0.15:
            upside_indicator = "**"
        elif r['upside'] >= 0.05:
            upside_indicator = "*"
        else:
            upside_indicator = ""

        print(f"{r['ticker']:<7} ${r['current_price']:>7.2f} ${r['target_median'] or r['target_mean']:>7.2f} {r['upside']*100:>+7.1f}% {upside_indicator:<3} {r['num_analysts']:>5} {dispersion_str:>10} {week52_str:>7} {mcap_str:>8} {r['recommendation']:<12}")

    print()
    print(f"=" * 120)
    print("LEGEND: *** = 30%+ upside | ** = 15%+ upside | * = 5%+ upside")
    print("Dispersion = (high - low) / mean target — higher = more analyst disagreement")
    print(f"=" * 120)

    # Summary stats
    if filtered:
        avg_upside = sum(r['upside'] for r in filtered) / len(filtered)
        max_upside = max(r['upside'] for r in filtered)
        print()
        print(f"SUMMARY: {len(filtered)} stocks | Avg upside: {avg_upside*100:+.1f}% | Max upside: {max_upside*100:+.1f}%")

    # Sector breakdown
    sectors = {}
    for r in filtered:
        s = r['sector']
        if s not in sectors:
            sectors[s] = []
        sectors[s].append(r)

    if len(sectors) > 1:
        print()
        print("BY SECTOR:")
        for sector, stocks in sorted(sectors.items(), key=lambda x: -sum(s['upside'] for s in x[1])/len(x[1])):
            avg = sum(s['upside'] for s in stocks) / len(stocks)
            names = ', '.join(s['ticker'] for s in stocks[:5])
            print(f"  {sector:<25} ({len(stocks):>2}) avg {avg*100:+.1f}%: {names}")

    print()

    # Save output
    if args.output:
        output_data = {
            'scan_date': datetime.now().isoformat(),
            'universe_size': len(tickers),
            'results_count': len(filtered),
            'min_analysts': args.min_analysts,
            'results': filtered,
        }
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()

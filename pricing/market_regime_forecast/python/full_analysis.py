#!/usr/bin/env python3
"""Combined regime + earnings analysis for income ETFs."""

import json
import sys
from pathlib import Path
from datetime import datetime
import warnings

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[3]))

import yfinance as yf

from lib.python.retry import retry_with_backoff

warnings.filterwarnings('ignore')

# Configuration
TICKERS = ['spy', 'qqq', 'nvda', 'tsla', 'coin', 'amzn', 'mstr', 'aapl', 'googl', 'meta', 'msft']
ETF_MAP = {
    'spy': 'JEPI, SPYI, BALI, XYLD, DIVO',
    'qqq': 'JEPQ, QQQI, QYLD, NUSI',
    'nvda': 'NVDY, NVDW',
    'tsla': 'TSLY, TSLW',
    'coin': 'CONY',
    'amzn': 'AMZW, AMZY',
    'mstr': 'MSTY',
    'aapl': 'APLY',
    'googl': 'GOOY',
    'meta': 'FBY, METW',
    'msft': 'MSFO, MSFW',
}


def get_earnings_date(ticker: str) -> tuple:
    """Get next earnings date and days until."""
    if ticker.upper() in ['SPY', 'QQQ']:
        return None, None

    try:
        stock = yf.Ticker(ticker.upper())
        calendar = retry_with_backoff(lambda: stock.calendar)
        if calendar is not None and isinstance(calendar, dict) and 'Earnings Date' in calendar:
            ed = calendar['Earnings Date']
            if isinstance(ed, list) and len(ed) > 0:
                next_date = ed[0]
                if hasattr(next_date, 'date'):
                    next_date = next_date.date()
                days = (next_date - datetime.now().date()).days
                return str(next_date), days
    except:
        pass
    return None, None


def main():
    results = []

    for ticker in TICKERS:
        path = Path(__file__).resolve().parent.parent / "output" / f"{ticker}_regime.json"
        if not path.exists():
            continue

        data = json.load(open(path))
        regime = data['current_regime']
        actual = regime.get('actual_returns', {})

        earnings_date, days_until = get_earnings_date(ticker)

        results.append({
            'ticker': ticker.upper(),
            'etfs': ETF_MAP.get(ticker, ''),
            'trend': regime['trend'],
            'vol': regime['volatility'],
            'suitability': data['income_etf']['covered_call_suitability'],
            'ret_6m': actual.get('return_6m', 0) * 100,
            'earnings_date': earnings_date,
            'days_until': days_until,
        })

    # Sort by suitability, then by earnings proximity (further = better)
    results.sort(key=lambda x: (-x['suitability'], -(x['days_until'] or 999)))

    print()
    print("=" * 110)
    print("INCOME ETF REGIME + EARNINGS ANALYSIS")
    print("=" * 110)
    print()
    print(f"{'Underlying':<8} {'Income ETFs':<25} {'Regime':<20} {'Stars':<6} {'6M Ret':<8} {'Earnings':<12} {'Action':<15}")
    print("-" * 110)

    for r in results:
        regime_str = f"{r['trend']}/{r['vol'].split()[0]}"

        if r['days_until'] is None:
            earnings_str = "N/A"
            action = ""
        elif r['days_until'] <= 7:
            earnings_str = f"{r['days_until']}d ⚠️"
            action = "WAIT/EXIT"
        elif r['days_until'] <= 14:
            earnings_str = f"{r['days_until']}d ⚡"
            action = "CAUTION"
        else:
            earnings_str = f"{r['days_until']}d"
            action = ""

        # Combine regime and earnings for final action
        if r['suitability'] >= 4:
            if action == "WAIT/EXIT":
                final = "Wait for earnings"
            elif action == "CAUTION":
                final = "Enter small"
            else:
                final = "ENTER" if r['suitability'] == 5 else "Good entry"
        elif r['suitability'] == 3:
            if action in ["WAIT/EXIT", "CAUTION"]:
                final = "Avoid for now"
            else:
                final = "Neutral"
        else:
            final = "Avoid"

        print(f"{r['ticker']:<8} {r['etfs']:<25} {regime_str:<20} {r['suitability']}/5   {r['ret_6m']:>+5.1f}%   {earnings_str:<12} {final:<15}")

    print()
    print("=" * 110)
    print("LEGEND: ⚠️ = Earnings <7 days (high risk) | ⚡ = Earnings <14 days (elevated risk)")
    print("=" * 110)

    # Summary
    print()
    print("TOP PICKS (4-5 stars + earnings >14 days):")
    for r in results:
        if r['suitability'] >= 4 and (r['days_until'] is None or r['days_until'] > 14):
            print(f"  • {r['ticker']}: {r['etfs']} - {r['trend']} regime")

    print()
    print("AVOID (earnings <7 days):")
    for r in results:
        if r['days_until'] is not None and r['days_until'] <= 7:
            print(f"  • {r['ticker']}: {r['etfs']} - earnings in {r['days_until']} days")

    print()


if __name__ == "__main__":
    main()

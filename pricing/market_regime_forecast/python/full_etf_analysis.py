#!/usr/bin/env python3
"""Full analysis of all income ETFs with regime and earnings data."""

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

# ETF to underlying mapping
ETF_UNDERLYING = {
    'JEPI': 'SPY', 'SPYI': 'SPY', 'BALI': 'SPY', 'XYLD': 'SPY', 'DIVO': 'SPY',
    'JEPQ': 'QQQ', 'QQQI': 'QQQ', 'QYLD': 'QQQ', 'NUSI': 'QQQ',
    'NVDY': 'NVDA', 'NVDW': 'NVDA',
    'TSLY': 'TSLA', 'TSLW': 'TSLA',
    'CONY': 'COIN',
    'AMZW': 'AMZN', 'AMZY': 'AMZN',
    'MSTY': 'MSTR',
    'APLY': 'AAPL',
    'GOOY': 'GOOGL',
    'FBY': 'META', 'METW': 'META',
    'MSFO': 'MSFT', 'MSFW': 'MSFT',
}

# Provider info
ETF_PROVIDER = {
    'JEPI': 'JPMorgan', 'JEPQ': 'JPMorgan',
    'SPYI': 'NEOS', 'QQQI': 'NEOS',
    'QYLD': 'GlobalX', 'XYLD': 'GlobalX',
    'BALI': 'iShares',
    'DIVO': 'Amplify',
    'NUSI': 'Nationwide',
    'NVDY': 'YieldMax', 'TSLY': 'YieldMax', 'CONY': 'YieldMax', 'MSTY': 'YieldMax',
    'AMZY': 'YieldMax', 'APLY': 'YieldMax',
    'GOOY': 'YieldMax', 'FBY': 'YieldMax', 'MSFO': 'YieldMax',
    'NVDW': 'Roundhill', 'TSLW': 'Roundhill', 'AMZW': 'Roundhill',
    'METW': 'Roundhill', 'MSFW': 'Roundhill',
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


def load_etf_data(ticker: str) -> dict:
    """Load ETF data from income analysis."""
    path = Path(__file__).resolve().parent.parent.parent.parent / "valuation" / "etf_analysis" / "data" / f"etf_data_{ticker}.json"
    if path.exists():
        return json.load(open(path))
    return None


def load_regime_data(underlying: str) -> dict:
    """Load regime data for underlying."""
    path = Path(__file__).resolve().parent.parent / "output" / f"{underlying.lower()}_regime.json"
    if path.exists():
        return json.load(open(path))
    return None


def main():
    etfs = list(ETF_UNDERLYING.keys())
    results = []

    # Cache earnings dates
    earnings_cache = {}
    for underlying in set(ETF_UNDERLYING.values()):
        earnings_cache[underlying] = get_earnings_date(underlying)

    for etf in etfs:
        underlying = ETF_UNDERLYING[etf]

        etf_data = load_etf_data(etf)
        regime_data = load_regime_data(underlying)

        if etf_data is None or regime_data is None:
            continue

        regime = regime_data['current_regime']
        dist = etf_data.get('distribution', {})
        nav = etf_data.get('nav_trend', {})

        earnings_date, days_until = earnings_cache.get(underlying, (None, None))

        trend_probs = regime.get('trend_probabilities', {})
        results.append({
            'etf': etf,
            'underlying': underlying,
            'provider': ETF_PROVIDER.get(etf, 'Unknown'),
            'price': etf_data.get('current_price', 0),
            'yield': dist.get('current_yield', 0) * 100,
            'nav_return': nav.get('price_return', 0) * 100,
            'trend': regime['trend'],
            'vol_regime': regime['volatility'],
            'bull_prob': trend_probs.get('bull', 0) * 100,
            'bear_prob': trend_probs.get('bear', 0) * 100,
            'side_prob': trend_probs.get('sideways', 0) * 100,
            'vol_pct': regime.get('vol_percentile', 0) * 100,
            'suitability': regime_data['income_etf']['covered_call_suitability'],
            'earnings_date': earnings_date,
            'days_until': days_until,
            'is_new': dist.get('is_new_etf', False),
        })

    # Sort by suitability desc, then yield desc
    results.sort(key=lambda x: (-x['suitability'], -(x['days_until'] or 999), -x['yield']))

    print()
    print("=" * 165)
    print("COMPLETE INCOME ETF ANALYSIS - Regime + Earnings + Yield")
    print("=" * 165)
    print()
    print(f"{'ETF':<6} {'Under':<6} {'Price':>7} {'Yield':>7} {'NAV':>7} {'Bull%':>6} {'Bear%':>6} {'Side%':>6} {'Vol%':>5} {'Trend':<9} {'Stars':<5} {'Earn':<8} {'Action':<16}")
    print("-" * 165)

    for r in results:
        if r['days_until'] is None:
            earnings_str = "N/A"
        elif r['days_until'] <= 7:
            earnings_str = f"{r['days_until']}d ⚠️"
        elif r['days_until'] <= 14:
            earnings_str = f"{r['days_until']}d ⚡"
        else:
            earnings_str = f"{r['days_until']}d"

        # Determine action
        if r['suitability'] >= 4:
            if r['days_until'] is not None and r['days_until'] <= 7:
                action = "⏳ Wait"
            elif r['days_until'] is not None and r['days_until'] <= 14:
                action = "⚡ Small pos"
            else:
                action = "✅ Good entry"
        elif r['suitability'] == 3:
            if r['days_until'] is not None and r['days_until'] <= 14:
                action = "❌ Avoid"
            else:
                action = "⚖️ Neutral"
        else:
            action = "❌ Avoid"

        new_flag = "*" if r['is_new'] else ""

        print(f"{r['etf']:<6} {r['underlying']:<6} ${r['price']:>6.2f} {r['yield']:>6.1f}% {r['nav_return']:>+6.1f}% {r['bull_prob']:>5.0f}% {r['bear_prob']:>5.0f}% {r['side_prob']:>5.0f}% {r['vol_pct']:>4.0f}% {r['trend']:<9} {r['suitability']}/5   {earnings_str:<8} {action:<16}{new_flag}")

    print()
    print("=" * 140)
    print("LEGEND: ⚠️ Earnings <7d | ⚡ Earnings <14d | *NEW* = <1 year track record")
    print("=" * 140)

    # Summary by action
    print()
    print("SUMMARY BY ACTION:")
    print("-" * 80)

    good_entries = [r for r in results if r['suitability'] >= 4 and (r['days_until'] is None or r['days_until'] > 14)]
    wait_earnings = [r for r in results if r['suitability'] >= 4 and r['days_until'] is not None and r['days_until'] <= 7]
    small_pos = [r for r in results if r['suitability'] >= 4 and r['days_until'] is not None and 7 < r['days_until'] <= 14]
    avoid = [r for r in results if r['suitability'] < 4 or (r['days_until'] is not None and r['days_until'] <= 7 and r['suitability'] < 4)]

    print()
    print("✅ GOOD ENTRY (4+ stars, no imminent earnings):")
    for r in good_entries:
        print(f"   {r['etf']:<6} ({r['underlying']}) - {r['yield']:.1f}% yield, {r['trend']} regime")

    print()
    print("⏳ WAIT FOR EARNINGS (good regime but <7 days to earnings):")
    for r in wait_earnings:
        print(f"   {r['etf']:<6} ({r['underlying']}) - earnings {r['earnings_date']}, wait then enter")

    print()
    print("⚡ SMALL POSITION ONLY (7-14 days to earnings):")
    for r in small_pos:
        print(f"   {r['etf']:<6} ({r['underlying']}) - earnings in {r['days_until']} days")

    print()
    print("❌ AVOID:")
    avoid_list = [r for r in results if r['suitability'] <= 2]
    for r in avoid_list:
        print(f"   {r['etf']:<6} ({r['underlying']}) - {r['trend']} regime = opportunity cost")

    print()


if __name__ == "__main__":
    main()

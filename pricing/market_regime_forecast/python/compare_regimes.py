#!/usr/bin/env python3
"""Compare regime forecasts for income ETF underlyings."""

import json
from pathlib import Path

tickers = ['spy', 'qqq', 'nvda', 'tsla', 'coin', 'amzn', 'mstr', 'aapl', 'googl', 'meta', 'msft']
etf_map = {
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

results = []
for ticker in tickers:
    path = Path(__file__).resolve().parent.parent / "output" / f"{ticker}_regime.json"
    if path.exists():
        data = json.load(open(path))
        regime = data['current_regime']
        actual = regime.get('actual_returns', {})
        results.append({
            'ticker': ticker.upper(),
            'etfs': etf_map.get(ticker, ''),
            'trend': regime['trend'],
            'vol': regime['volatility'],
            'bull_prob': regime['trend_probabilities']['bull'] * 100,
            'bear_prob': regime['trend_probabilities']['bear'] * 100,
            'side_prob': regime['trend_probabilities']['sideways'] * 100,
            'vol_pct': regime['vol_percentile'] * 100,
            'vol_forecast': data['garch_fit']['unconditional_vol'] * 100,
            'suitability': data['income_etf']['covered_call_suitability'],
            'recommendation': data['income_etf']['recommendation'],
            'ret_1m': actual.get('return_1m', 0) * 100,
            'ret_3m': actual.get('return_3m', 0) * 100,
            'ret_6m': actual.get('return_6m', 0) * 100,
        })

# Sort by suitability (descending), then by vol percentile (descending for high vol)
results.sort(key=lambda x: (-x['suitability'], -x['vol_pct']))

print()
print("INCOME ETF REGIME RANKING (Best to Worst for Covered Calls)")
print("=" * 105)
print(f"{'Underlying':<10} {'Income ETFs':<18} {'Trend':<10} {'Vol Regime':<18} {'Vol %ile':<10} {'Stars':<6}")
print("-" * 105)
for r in results:
    print(f"{r['ticker']:<10} {r['etfs']:<18} {r['trend']:<10} {r['vol']:<18} {r['vol_pct']:>5.0f}%     {r['suitability']}/5")

print()
print("TREND PROBABILITIES")
print("-" * 105)
print(f"{'Underlying':<10} {'Bull %':<10} {'Bear %':<10} {'Sideways %':<12} {'Dominant':<12}")
print("-" * 105)
for r in results:
    probs = [('Bull', r['bull_prob']), ('Bear', r['bear_prob']), ('Sideways', r['side_prob'])]
    dominant = max(probs, key=lambda x: x[1])[0]
    print(f"{r['ticker']:<10} {r['bull_prob']:>6.1f}%    {r['bear_prob']:>6.1f}%    {r['side_prob']:>8.1f}%     {dominant:<12}")

print()
print("ACTUAL RETURNS (Period) - Sanity Check")
print("-" * 105)
print(f"{'Underlying':<10} {'1M':<10} {'3M':<10} {'6M':<10} {'HMM Trend':<12} {'Match?':<8}")
print("-" * 105)
for r in results:
    # Check if HMM trend matches actual returns
    avg_ret = (r['ret_1m'] + r['ret_3m'] + r['ret_6m']) / 3
    expected_trend = 'Bull' if avg_ret > 5 else ('Bear' if avg_ret < -5 else 'Sideways')
    match = 'Yes' if r['trend'] == expected_trend else 'CHECK'
    print(f"{r['ticker']:<10} {r['ret_1m']:>+6.1f}%    {r['ret_3m']:>+6.1f}%    {r['ret_6m']:>+6.1f}%    {r['trend']:<12} {match:<8}")

print()
print("RECOMMENDATIONS")
print("-" * 105)
for r in results:
    print(f"{r['ticker']:<6} ({r['suitability']}/5): {r['recommendation']}")
print()

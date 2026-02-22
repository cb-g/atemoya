#!/usr/bin/env python3
"""Fetch next earnings dates for tickers."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
import warnings

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf

from lib.python.retry import retry_with_backoff

warnings.filterwarnings('ignore')


def fetch_earnings(tickers: list[str]) -> dict:
    """Fetch next earnings dates for a list of tickers."""
    results = {}
    today = datetime.now().date()

    for ticker in tickers:
        # Skip ETFs - they don't have earnings
        if ticker in ['SPY', 'QQQ']:
            results[ticker] = {
                'next_earnings': 'N/A (ETF)',
                'days_until': None,
            }
            continue

        try:
            stock = yf.Ticker(ticker)

            # Try multiple approaches
            next_date = None

            # Approach 1: calendar
            try:
                calendar = retry_with_backoff(lambda: stock.calendar)
                if calendar is not None:
                    if isinstance(calendar, dict) and 'Earnings Date' in calendar:
                        ed = calendar['Earnings Date']
                        if isinstance(ed, list) and len(ed) > 0:
                            next_date = ed[0]
                        elif hasattr(ed, 'date'):
                            next_date = ed
            except:
                pass

            # Approach 2: get_earnings_dates
            if next_date is None:
                try:
                    # Use info dict
                    info = retry_with_backoff(lambda: stock.info)
                    if 'nextEarningsDate' in info:
                        next_date = datetime.fromtimestamp(info['nextEarningsDate']).date()
                except:
                    pass

            if next_date is not None:
                if hasattr(next_date, 'date'):
                    next_date = next_date.date()
                elif isinstance(next_date, str):
                    next_date = datetime.strptime(next_date, '%Y-%m-%d').date()

                days_until = (next_date - today).days
                results[ticker] = {
                    'next_earnings': str(next_date),
                    'days_until': days_until,
                }
            else:
                results[ticker] = {
                    'next_earnings': 'Unknown',
                    'days_until': None,
                }

        except Exception as e:
            results[ticker] = {
                'next_earnings': 'Unknown',
                'days_until': None,
            }

    return results


def main():
    parser = argparse.ArgumentParser(description="Fetch earnings dates")
    parser.add_argument("tickers", nargs='+', help="Ticker symbols")
    parser.add_argument("--output", "-o", help="Output JSON file")

    args = parser.parse_args()

    results = fetch_earnings(args.tickers)

    print()
    print("EARNINGS CALENDAR")
    print("-" * 50)
    print(f"{'Ticker':<10} {'Next Earnings':<15} {'Days Until':<12}")
    print("-" * 50)

    for ticker, data in sorted(results.items(), key=lambda x: x[1].get('days_until') or 999):
        days = data.get('days_until')
        days_str = f"{days:>3} days" if days is not None else "Unknown"
        warning = " ⚠️ SOON!" if days is not None and days <= 14 else ""
        print(f"{ticker:<10} {data['next_earnings']:<15} {days_str:<12}{warning}")

    print()

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()

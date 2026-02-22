#!/usr/bin/env python3
"""
Fetch historical earnings events for backtesting.

Strategy: Fetch earnings dates for a universe of liquid stocks
over the past 2-3 years where we can get reliable data.
"""

import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf
import pandas as pd
import argparse
from datetime import datetime, timedelta
import time

from lib.python.retry import retry_with_backoff

# Universe: Liquid stocks with high options volume
UNIVERSE = [
    # Mega cap tech
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    # Other mega caps
    'SPY', 'QQQ', 'JPM', 'BAC', 'WMT', 'JNJ', 'V', 'MA',
    # High vol tech
    'AMD', 'NFLX', 'PYPL', 'SQ', 'SHOP', 'ROKU', 'ZM',
    # Other sectors
    'DIS', 'BA', 'GS', 'GE', 'F', 'GM', 'XOM', 'CVX',
]

def fetch_historical_earnings(ticker: str, start_date: str) -> list:
    """Fetch all earnings dates since start_date for ticker."""

    try:
        stock = yf.Ticker(ticker)

        # Use earnings_history instead of get_earnings_dates to avoid timezone issues
        print(f"  Fetching earnings for {ticker}...")
        earnings_history = retry_with_backoff(lambda: stock.get_earnings_history())

        if earnings_history is None or len(earnings_history) == 0:
            print(f"  ⚠ No earnings history for {ticker}")
            return []

        print(f"  Found {len(earnings_history)} total earnings events")

        # Convert to datetime for filtering
        start_dt = pd.to_datetime(start_date)

        events = []
        for _, row in earnings_history.iterrows():
            try:
                # Get earnings date from the row
                if 'startdatetime' in row and pd.notna(row['startdatetime']):
                    earn_date = pd.to_datetime(row['startdatetime'])
                elif 'date' in row and pd.notna(row['date']):
                    earn_date = pd.to_datetime(row['date'])
                else:
                    continue

                # Remove timezone if present
                if hasattr(earn_date, 'tz_localize'):
                    if earn_date.tzinfo is not None:
                        earn_date = earn_date.replace(tzinfo=None)

                # Filter by date
                if earn_date >= start_dt:
                    events.append({
                        'ticker': ticker,
                        'earnings_date': earn_date.strftime('%Y-%m-%d'),
                        'reported_eps': row.get('epsactual', None),
                        'surprise_pct': row.get('epssurprisepercent', None),
                    })
            except Exception as e:
                print(f"    ⚠ Skipping row: {e}")

        print(f"  ✓ {ticker}: Found {len(events)} earnings events since {start_date}")
        return events

    except Exception as e:
        print(f"  ✗ {ticker}: Error fetching earnings - {e}")
        return []

def fetch_price_data(ticker: str, earnings_date: str, lookback_days: int = 90) -> dict:
    """Fetch price data around earnings event."""

    try:
        earn_dt = pd.to_datetime(earnings_date)
        start_date = earn_dt - timedelta(days=lookback_days)
        end_date = earn_dt + timedelta(days=10)  # Post-earnings data

        stock = yf.Ticker(ticker)
        hist = retry_with_backoff(lambda: stock.history(start=start_date, end=end_date))

        if len(hist) == 0:
            return None

        # Get price before/after earnings
        pre_earnings = hist[hist.index < earn_dt]
        post_earnings = hist[hist.index >= earn_dt]

        if len(pre_earnings) == 0 or len(post_earnings) == 0:
            return None

        pre_close = pre_earnings['Close'].iloc[-1]
        post_open = post_earnings['Open'].iloc[0] if len(post_earnings) > 0 else None
        post_close = post_earnings['Close'].iloc[0] if len(post_earnings) > 0 else None

        # Calculate volume
        avg_volume_30d = pre_earnings['Volume'].tail(30).mean()

        return {
            'pre_close': pre_close,
            'post_open': post_open,
            'post_close': post_close,
            'avg_volume_30d': avg_volume_30d,
            'prices_90d': pre_earnings['Close'].values,
        }

    except Exception as e:
        print(f"    ⚠ Error fetching price data for {ticker} on {earnings_date}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Fetch historical earnings for backtest')
    parser.add_argument('--start-date', type=str, default='2022-01-01',
                       help='Start date for historical data (YYYY-MM-DD)')
    parser.add_argument('--output-dir', type=str, default='pricing/earnings_vol/data/backtest',
                       help='Output directory')
    parser.add_argument('--universe', type=str, nargs='+', default=UNIVERSE,
                       help='List of tickers to fetch')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nFetching historical earnings since {args.start_date}")
    print(f"Universe: {len(args.universe)} tickers\n")

    all_events = []

    for ticker in args.universe:
        # Fetch earnings dates
        events = fetch_historical_earnings(ticker, args.start_date)

        # For each event, fetch price data
        for event in events:
            price_data = fetch_price_data(
                event['ticker'],
                event['earnings_date'],
                lookback_days=90
            )

            if price_data:
                event.update({
                    'pre_close': price_data['pre_close'],
                    'post_open': price_data['post_open'],
                    'post_close': price_data['post_close'],
                    'avg_volume_30d': price_data['avg_volume_30d'],
                })

                # Save individual price history
                prices_df = pd.DataFrame({
                    'date': range(len(price_data['prices_90d'])),
                    'price': price_data['prices_90d']
                })

                prices_file = output_dir / f"{event['ticker']}_{event['earnings_date']}_prices.csv"
                prices_df.to_csv(prices_file, index=False)

                all_events.append(event)

        # Rate limit
        time.sleep(0.5)

    # Save all events
    if len(all_events) > 0:
        events_df = pd.DataFrame(all_events)
        events_file = output_dir / "historical_earnings_events.csv"
        events_df.to_csv(events_file, index=False)

        print(f"\n✅ Backtest data collection complete")
        print(f"  Total events: {len(all_events)}")
        print(f"  Date range: {events_df['earnings_date'].min()} to {events_df['earnings_date'].max()}")
        print(f"  Tickers: {events_df['ticker'].nunique()}")
        print(f"  Output: {events_file}")
    else:
        print("\n⚠ No events found")

if __name__ == "__main__":
    main()

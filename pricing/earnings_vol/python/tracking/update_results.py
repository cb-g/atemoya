#!/usr/bin/env python3
"""
Update trade database with post-earnings results.

Run this after earnings to calculate actual P&L and add to historical dataset.
"""

import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import argparse

from lib.python.retry import retry_with_backoff

DATABASE_FILE = "pricing/earnings_vol/data/trade_history.csv"

def calculate_calendar_pnl(spot: float, post_close: float, front_iv: float, back_iv: float) -> float:
    """Estimate calendar P&L based on move size."""
    move_pct = abs((post_close - spot) / spot)
    expected_move = front_iv * (7.0 / 365.0) ** 0.5  # Weekly move

    # Calendar profits from IV crush + time decay
    if move_pct < expected_move * 0.5:
        return 0.073  # 7.3% profit
    elif move_pct < expected_move:
        return 0.04
    elif move_pct < expected_move * 1.5:
        return -0.03
    else:
        return -0.15  # Capped loss

def calculate_straddle_pnl(spot: float, post_close: float, front_iv: float) -> float:
    """Estimate straddle P&L based on move size."""
    move_pct = abs((post_close - spot) / spot)
    expected_move = front_iv * (7.0 / 365.0) ** 0.5

    if move_pct < expected_move * 0.5:
        return 0.09
    elif move_pct < expected_move:
        return 0.05
    elif move_pct < expected_move * 1.5:
        return -0.10
    else:
        return -0.30

def update_trade_result(ticker: str, earnings_date: str):
    """Update a specific trade with post-earnings results."""

    db_path = Path(DATABASE_FILE)
    if not db_path.exists():
        print(f"✗ Database not found: {DATABASE_FILE}")
        return

    df = pd.read_csv(db_path)

    # Find the trade
    mask = (df['ticker'] == ticker) & (df['earnings_date'] == earnings_date) & (df['status'] == 'pending')
    if mask.sum() == 0:
        print(f"✗ No pending trade found for {ticker} on {earnings_date}")
        return

    idx = df[mask].index[0]
    trade = df.loc[idx]

    print(f"\nUpdating {ticker} earnings on {earnings_date}...")
    print(f"  Pre-earnings price: ${trade['spot_price']:.2f}")
    print(f"  Recommendation: {trade['recommendation']}")

    # Fetch post-earnings price
    try:
        stock = yf.Ticker(ticker)
        earn_dt = pd.to_datetime(earnings_date)
        end_date = earn_dt + timedelta(days=5)

        hist = retry_with_backoff(lambda: stock.history(start=earn_dt, end=end_date))
        if len(hist) == 0:
            print(f"  ✗ No post-earnings price data available yet")
            return

        post_close = hist['Close'].iloc[0]
        stock_move_pct = (post_close - trade['spot_price']) / trade['spot_price']

        print(f"  Post-earnings price: ${post_close:.2f}")
        print(f"  Stock move: {stock_move_pct*100:.2f}%")

        # Calculate P&L based on position type
        if pd.notna(trade['position_type']):
            if trade['position_type'].lower() == 'calendar':
                pnl_pct = calculate_calendar_pnl(
                    trade['spot_price'],
                    post_close,
                    trade['front_month_iv'],
                    trade['back_month_iv']
                )
            else:  # straddle
                pnl_pct = calculate_straddle_pnl(
                    trade['spot_price'],
                    post_close,
                    trade['front_month_iv']
                )

            is_win = pnl_pct > 0
            print(f"  Estimated P&L: {pnl_pct*100:.2f}%")
            print(f"  Result: {'WIN' if is_win else 'LOSS'}")

            # Update database
            df.loc[idx, 'post_earnings_price'] = post_close
            df.loc[idx, 'stock_move_pct'] = stock_move_pct
            df.loc[idx, 'actual_return_pct'] = pnl_pct
            df.loc[idx, 'is_win'] = is_win
            df.loc[idx, 'status'] = 'completed'

            df.to_csv(db_path, index=False)

            print(f"\n✓ Trade updated in database")
            print(f"  Completed trades: {len(df[df['status'] == 'completed'])}")

        else:
            print(f"  ⚠ No position type recorded (scan only, not traded)")
            df.loc[idx, 'post_earnings_price'] = post_close
            df.loc[idx, 'stock_move_pct'] = stock_move_pct
            df.loc[idx, 'status'] = 'skipped'
            df.to_csv(db_path, index=False)

    except Exception as e:
        print(f"  ✗ Error fetching post-earnings data: {e}")

def update_all_pending():
    """Update all pending trades that have passed their earnings date."""

    db_path = Path(DATABASE_FILE)
    if not db_path.exists():
        print(f"✗ Database not found: {DATABASE_FILE}")
        return

    df = pd.read_csv(db_path)

    pending = df[df['status'] == 'pending']
    today = datetime.now()

    print(f"\nChecking {len(pending)} pending trades...")

    for idx, trade in pending.iterrows():
        earnings_dt = pd.to_datetime(trade['earnings_date'])

        # Check if earnings have passed (give 2 days buffer)
        if earnings_dt < today - timedelta(days=2):
            print(f"\n→ Updating {trade['ticker']} (earnings {trade['earnings_date']})")
            update_trade_result(trade['ticker'], trade['earnings_date'])

def main():
    parser = argparse.ArgumentParser(description='Update trade results after earnings')
    parser.add_argument('--ticker', type=str, help='Specific ticker to update')
    parser.add_argument('--earnings-date', type=str, help='Earnings date (YYYY-MM-DD)')
    parser.add_argument('--all', action='store_true', help='Update all pending trades')

    args = parser.parse_args()

    if args.all:
        update_all_pending()
    elif args.ticker and args.earnings_date:
        update_trade_result(args.ticker, args.earnings_date)
    else:
        print("Usage: --ticker TICKER --earnings-date DATE  OR  --all")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Update Trade Results

Updates pending trades after they've exited (day before earnings).
Fetches exit straddle price and calculates actual P&L.
"""

import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta
import argparse

DATABASE_FILE = "pricing/pre_earnings_straddle/data/trade_history.csv"

def update_trade_results(ticker: str = None):
    """
    Update results for trades that should have exited.

    Exit timing: Day before earnings (to avoid holding through the gap).
    """

    db_path = Path(DATABASE_FILE)
    if not db_path.exists():
        print(f"✗ Database not found: {db_path}")
        return

    df = pd.read_csv(db_path)

    # Filter pending trades
    if ticker:
        mask = (df['ticker'] == ticker) & (df['status'] == 'pending')
    else:
        # Find all pending trades past their earnings date
        today = datetime.now().strftime('%Y-%m-%d')
        mask = (df['status'] == 'pending') & (df['earnings_date'] <= today)

    pending = df[mask]

    if len(pending) == 0:
        print("No pending trades to update.")
        return

    print(f"\nUpdating {len(pending)} pending trade(s)...\n")

    for idx, row in pending.iterrows():
        ticker = row['ticker']
        earnings_date = row['earnings_date']
        expiration = row['expiration']
        atm_strike = row['atm_strike']
        entry_cost = row['straddle_cost']

        print(f"Processing {ticker} (earnings: {earnings_date})...")

        try:
            # Exit date is day before earnings
            exit_date = pd.to_datetime(earnings_date) - timedelta(days=1)

            # Fetch options chain on exit date
            # Note: This requires historical options data, which yfinance doesn't provide well
            # In practice, you'd log the exit price in real-time
            # For now, we'll note that this needs to be done manually or with better data

            print(f"  ⚠ Manual update required")
            print(f"    Exit date: {exit_date.strftime('%Y-%m-%d')}")
            print(f"    Need to fetch ATM straddle price on exit date")
            print(f"    Entry cost: ${entry_cost:.2f}")
            print(f"    Use: python3 update_results.py --ticker {ticker} --exit-price <PRICE>")

        except Exception as e:
            print(f"  ✗ Error: {e}\n")

def update_single_trade(ticker: str, exit_price: float):
    """Update a single trade with manual exit price."""

    db_path = Path(DATABASE_FILE)
    if not db_path.exists():
        print(f"✗ Database not found: {db_path}")
        return

    df = pd.read_csv(db_path)

    # Find pending trade for this ticker
    mask = (df['ticker'] == ticker) & (df['status'] == 'pending')
    pending = df[mask]

    if len(pending) == 0:
        print(f"No pending trade found for {ticker}")
        return

    if len(pending) > 1:
        print(f"Multiple pending trades for {ticker}. Using most recent.")

    idx = pending.index[-1]
    row = df.loc[idx]

    entry_cost = row['straddle_cost']
    pnl = exit_price - entry_cost
    return_pct = (pnl / entry_cost * 100) if entry_cost > 0 else 0

    # Update row
    df.loc[idx, 'status'] = 'completed'
    df.loc[idx, 'exit_date'] = datetime.now().strftime('%Y-%m-%d')
    df.loc[idx, 'exit_straddle_price'] = exit_price
    df.loc[idx, 'actual_pnl'] = pnl
    df.loc[idx, 'actual_return_pct'] = return_pct

    # Save
    df.to_csv(db_path, index=False)

    print(f"\n✓ Trade updated:")
    print(f"  Ticker: {ticker}")
    print(f"  Entry cost: ${entry_cost:.2f}")
    print(f"  Exit price: ${exit_price:.2f}")
    print(f"  P&L: ${pnl:.2f} ({return_pct:+.1f}%)")
    print(f"  Status: completed")

def main():
    parser = argparse.ArgumentParser(description='Update trade results')
    parser.add_argument('--ticker', type=str, help='Specific ticker to update')
    parser.add_argument('--exit-price', type=float, help='Exit straddle price (for manual update)')

    args = parser.parse_args()

    if args.ticker and args.exit_price:
        update_single_trade(args.ticker, args.exit_price)
    elif args.ticker:
        update_trade_results(ticker=args.ticker)
    else:
        update_trade_results()

if __name__ == "__main__":
    main()

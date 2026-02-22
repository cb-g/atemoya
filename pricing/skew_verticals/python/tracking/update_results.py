#!/usr/bin/env python3
"""
Update Trade Results

Closes out pending trades after expiration by fetching the exit spot price
and calculating actual P&L.
"""

import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import pandas as pd
import yfinance as yf
from datetime import datetime
import argparse

from lib.python.retry import retry_with_backoff

DATABASE_FILE = "pricing/skew_verticals/data/trade_history.csv"

def calculate_spread_pnl(
    exit_spot: float,
    long_strike: float,
    short_strike: float,
    debit: float,
    spread_type: str
) -> float:
    """Calculate actual P&L of vertical spread at expiration."""

    if spread_type == "bull_call":
        # Long call payoff
        long_payoff = max(0, exit_spot - long_strike)
        # Short call payoff (negative)
        short_payoff = -max(0, exit_spot - short_strike)
        total_payoff = long_payoff + short_payoff
        pnl = total_payoff - debit
        return pnl

    elif spread_type == "bear_put":
        # Long put payoff
        long_payoff = max(0, long_strike - exit_spot)
        # Short put payoff (negative)
        short_payoff = -max(0, short_strike - exit_spot)
        total_payoff = long_payoff + short_payoff
        pnl = total_payoff - debit
        return pnl

    else:
        return 0.0

def update_trade_results(ticker: str = None, expiration: str = None):
    """
    Update results for expired trades.

    If ticker and expiration specified, updates that specific trade.
    Otherwise, updates all pending trades past their expiration.
    """

    db_path = Path(DATABASE_FILE)
    if not db_path.exists():
        print(f"✗ Database not found: {db_path}")
        return

    df = pd.read_csv(db_path)

    # Filter pending trades
    if ticker and expiration:
        mask = (df['ticker'] == ticker) & (df['expiration'] == expiration) & (df['status'] == 'pending')
    else:
        # Find all pending trades past expiration
        today = datetime.now().strftime('%Y-%m-%d')
        mask = (df['status'] == 'pending') & (df['expiration'] < today)

    pending = df[mask]

    if len(pending) == 0:
        print("No pending trades to update.")
        return

    print(f"\nUpdating {len(pending)} pending trade(s)...\n")

    for idx, row in pending.iterrows():
        ticker = row['ticker']
        expiration = row['expiration']

        print(f"Processing {ticker} (exp: {expiration})...")

        try:
            # Fetch stock data at expiration
            stock = yf.Ticker(ticker)
            hist = retry_with_backoff(lambda: stock.history(start=expiration, end=expiration))

            if len(hist) == 0:
                # Try next trading day
                exp_date = pd.to_datetime(expiration)
                next_day = (exp_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
                hist = retry_with_backoff(lambda: stock.history(start=next_day, end=next_day))

            if len(hist) == 0:
                print(f"  ✗ Could not fetch exit price for {ticker}")
                continue

            exit_spot = hist['Close'].iloc[0]

            # Calculate P&L
            pnl = calculate_spread_pnl(
                exit_spot=exit_spot,
                long_strike=row['long_strike'],
                short_strike=row['short_strike'],
                debit=row['debit'],
                spread_type=row['spread_type']
            )

            return_pct = (pnl / row['debit'] * 100) if row['debit'] > 0 else 0

            # Update row
            df.loc[idx, 'status'] = 'completed'
            df.loc[idx, 'close_date'] = expiration
            df.loc[idx, 'exit_spot_price'] = exit_spot
            df.loc[idx, 'actual_pnl'] = pnl
            df.loc[idx, 'actual_return_pct'] = return_pct

            print(f"  ✓ Exit spot: ${exit_spot:.2f}")
            print(f"  ✓ P&L: ${pnl:.2f} ({return_pct:+.1f}%)")
            print(f"  ✓ Status: completed\n")

        except Exception as e:
            print(f"  ✗ Error: {e}\n")

    # Save updated database
    df.to_csv(db_path, index=False)
    print(f"✓ Database updated: {db_path}")

def main():
    parser = argparse.ArgumentParser(description='Update trade results')
    parser.add_argument('--ticker', type=str, help='Specific ticker to update')
    parser.add_argument('--expiration', type=str, help='Specific expiration to update (YYYY-MM-DD)')

    args = parser.parse_args()

    if args.ticker and not args.expiration:
        print("✗ Must specify both --ticker and --expiration")
        return

    update_trade_results(ticker=args.ticker, expiration=args.expiration)

if __name__ == "__main__":
    main()

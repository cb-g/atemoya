#!/usr/bin/env python3
"""
Trade Logger for Pre-Earnings Straddles

Logs scan results to build a forward-testing database.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import argparse

# Database path
DATABASE_FILE = "pricing/pre_earnings_straddle/data/trade_history.csv"

# Column schema
COLUMNS = [
    # Scan metadata
    'scan_date',
    'ticker',
    'earnings_date',
    'days_to_earnings',

    # Pre-trade data
    'entry_date',
    'spot_price',
    'atm_strike',
    'atm_call_price',
    'atm_put_price',
    'straddle_cost',
    'current_implied_move',
    'expiration',
    'days_to_expiry',

    # Signals
    'implied_vs_last_implied_ratio',
    'implied_vs_last_realized_gap',
    'implied_vs_avg_implied_ratio',
    'implied_vs_avg_realized_gap',
    'last_implied',
    'last_realized',
    'avg_implied',
    'avg_realized',
    'num_historical_events',

    # Prediction
    'predicted_return',
    'recommendation',
    'rank_score',
    'kelly_fraction',
    'suggested_size',

    # Post-trade results (filled later)
    'status',
    'exit_date',
    'exit_straddle_price',
    'actual_pnl',
    'actual_return_pct',
]

def log_scan_data(scan_data: dict):
    """Log a new scan to the database."""

    db_path = Path(DATABASE_FILE)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing or create new
    if db_path.exists():
        df = pd.read_csv(db_path)
    else:
        df = pd.DataFrame(columns=COLUMNS)

    # Add scan metadata
    scan_data['scan_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    scan_data['entry_date'] = datetime.now().strftime('%Y-%m-%d')
    scan_data['status'] = 'pending'
    scan_data['exit_date'] = None
    scan_data['exit_straddle_price'] = None
    scan_data['actual_pnl'] = None
    scan_data['actual_return_pct'] = None

    # Append
    new_row = pd.DataFrame([scan_data])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(db_path, index=False)

    print(f"\n✓ Scan logged to database: {db_path}")
    print(f"  Ticker: {scan_data['ticker']}")
    print(f"  Earnings: {scan_data['earnings_date']} ({scan_data['days_to_earnings']} days)")
    print(f"  Recommendation: {scan_data['recommendation']}")
    print(f"  Predicted return: {scan_data['predicted_return']:.2%}")
    print(f"  Status: pending")

def main():
    parser = argparse.ArgumentParser(description='Log scan to trade database')
    parser.add_argument('--ticker', type=str, required=True)
    parser.add_argument('--earnings-date', type=str, required=True)
    parser.add_argument('--days-to-earnings', type=int, required=True)
    parser.add_argument('--spot', type=float, required=True)
    parser.add_argument('--atm-strike', type=float, required=True)
    parser.add_argument('--call-price', type=float, required=True)
    parser.add_argument('--put-price', type=float, required=True)
    parser.add_argument('--cost', type=float, required=True)
    parser.add_argument('--current-implied', type=float, required=True)
    parser.add_argument('--expiration', type=str, required=True)
    parser.add_argument('--dte', type=int, required=True)
    parser.add_argument('--sig1', type=float, required=True)
    parser.add_argument('--sig2', type=float, required=True)
    parser.add_argument('--sig3', type=float, required=True)
    parser.add_argument('--sig4', type=float, required=True)
    parser.add_argument('--last-implied', type=float, required=True)
    parser.add_argument('--last-realized', type=float, required=True)
    parser.add_argument('--avg-implied', type=float, required=True)
    parser.add_argument('--avg-realized', type=float, required=True)
    parser.add_argument('--num-events', type=int, required=True)
    parser.add_argument('--predicted-return', type=float, required=True)
    parser.add_argument('--recommendation', type=str, required=True)
    parser.add_argument('--rank-score', type=float, required=True)
    parser.add_argument('--kelly', type=float, required=True)
    parser.add_argument('--size', type=float, required=True)

    args = parser.parse_args()

    scan_data = {
        'ticker': args.ticker,
        'earnings_date': args.earnings_date,
        'days_to_earnings': args.days_to_earnings,
        'spot_price': args.spot,
        'atm_strike': args.atm_strike,
        'atm_call_price': args.call_price,
        'atm_put_price': args.put_price,
        'straddle_cost': args.cost,
        'current_implied_move': args.current_implied,
        'expiration': args.expiration,
        'days_to_expiry': args.dte,
        'implied_vs_last_implied_ratio': args.sig1,
        'implied_vs_last_realized_gap': args.sig2,
        'implied_vs_avg_implied_ratio': args.sig3,
        'implied_vs_avg_realized_gap': args.sig4,
        'last_implied': args.last_implied,
        'last_realized': args.last_realized,
        'avg_implied': args.avg_implied,
        'avg_realized': args.avg_realized,
        'num_historical_events': args.num_events,
        'predicted_return': args.predicted_return,
        'recommendation': args.recommendation,
        'rank_score': args.rank_score,
        'kelly_fraction': args.kelly,
        'suggested_size': args.size,
    }

    log_scan_data(scan_data)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Forward-building trade database for earnings volatility strategy.

Every time you scan a ticker, this logs it to the database.
After earnings, you update with actual results.
Over time, you build a real historical dataset.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import argparse

DATABASE_FILE = "pricing/earnings_vol/data/trade_history.csv"

# Database schema
COLUMNS = [
    # Scan metadata
    'scan_date',
    'ticker',
    'earnings_date',
    'days_to_earnings',

    # Pre-earnings data
    'spot_price',
    'avg_volume_30d',
    'front_month_iv',
    'back_month_iv',
    'term_slope',
    'rv_30d',
    'iv_rv_ratio',

    # Filter results
    'passes_term_slope',
    'passes_volume',
    'passes_iv_rv',
    'recommendation',

    # Position if traded
    'position_type',  # calendar or straddle
    'kelly_fraction',
    'position_size',
    'num_contracts',

    # Post-earnings results (filled in later)
    'post_earnings_price',
    'stock_move_pct',
    'actual_pnl',
    'actual_return_pct',
    'is_win',
    'status',  # pending, completed, skipped
]

def log_scan(scan_data: dict):
    """Log a new scan to the database."""

    db_path = Path(DATABASE_FILE)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing database or create new
    if db_path.exists():
        df = pd.read_csv(db_path)
    else:
        df = pd.DataFrame(columns=COLUMNS)

    # Add scan date
    scan_data['scan_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    scan_data['status'] = 'pending'

    # Set post-earnings fields to None
    for field in ['post_earnings_price', 'stock_move_pct', 'actual_pnl',
                  'actual_return_pct', 'is_win']:
        if field not in scan_data:
            scan_data[field] = None

    # Append to database
    new_row = pd.DataFrame([scan_data])
    df = pd.concat([df, new_row], ignore_index=True)

    # Save
    df.to_csv(db_path, index=False)

    print(f"✓ Logged scan for {scan_data['ticker']} to database")
    print(f"  Database now has {len(df)} total scans")
    print(f"  Pending: {len(df[df['status'] == 'pending'])}")
    print(f"  Completed: {len(df[df['status'] == 'completed'])}")

def main():
    parser = argparse.ArgumentParser(description='Log earnings vol scan to database')
    parser.add_argument('--ticker', type=str, required=True)
    parser.add_argument('--earnings-date', type=str, required=True)
    parser.add_argument('--days-to-earnings', type=int, required=True)
    parser.add_argument('--spot-price', type=float, required=True)
    parser.add_argument('--volume', type=float, required=True)
    parser.add_argument('--front-iv', type=float, required=True)
    parser.add_argument('--back-iv', type=float, required=True)
    parser.add_argument('--term-slope', type=float, required=True)
    parser.add_argument('--rv', type=float, required=True)
    parser.add_argument('--iv-rv-ratio', type=float, required=True)
    parser.add_argument('--recommendation', type=str, required=True)
    parser.add_argument('--position-type', type=str, default=None)
    parser.add_argument('--kelly-fraction', type=float, default=None)
    parser.add_argument('--position-size', type=float, default=None)
    parser.add_argument('--num-contracts', type=int, default=None)

    args = parser.parse_args()

    scan_data = {
        'ticker': args.ticker,
        'earnings_date': args.earnings_date,
        'days_to_earnings': args.days_to_earnings,
        'spot_price': args.spot_price,
        'avg_volume_30d': args.volume,
        'front_month_iv': args.front_iv,
        'back_month_iv': args.back_iv,
        'term_slope': args.term_slope,
        'rv_30d': args.rv,
        'iv_rv_ratio': args.iv_rv_ratio,
        'passes_term_slope': args.term_slope <= -0.05,
        'passes_volume': args.volume >= 1_000_000,
        'passes_iv_rv': args.iv_rv_ratio >= 1.1,
        'recommendation': args.recommendation,
        'position_type': args.position_type,
        'kelly_fraction': args.kelly_fraction,
        'position_size': args.position_size,
        'num_contracts': args.num_contracts,
    }

    log_scan(scan_data)

if __name__ == "__main__":
    main()

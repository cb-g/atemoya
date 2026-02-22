#!/usr/bin/env python3
"""
View and analyze the accumulated trade history database.
"""

import pandas as pd
from pathlib import Path
import argparse

DATABASE_FILE = "pricing/earnings_vol/data/trade_history.csv"

def view_database(filter_status=None):
    """View the trade history database."""

    db_path = Path(DATABASE_FILE)
    if not db_path.exists():
        print(f"✗ Database not found: {DATABASE_FILE}")
        print("  No scans logged yet. Run a scan first!")
        return

    df = pd.read_csv(db_path)

    print(f"\n═══ Earnings Volatility Trade History ═══\n")
    print(f"Total scans: {len(df)}")
    print(f"  Pending: {len(df[df['status'] == 'pending'])}")
    print(f"  Completed: {len(df[df['status'] == 'completed'])}")
    print(f"  Skipped: {len(df[df['status'] == 'skipped'])}")

    # Filter if requested
    if filter_status:
        df = df[df['status'] == filter_status]
        print(f"\nShowing {filter_status} trades only:")

    # Show summary stats for completed trades
    completed = df[df['status'] == 'completed']
    if len(completed) > 0:
        print(f"\n=== Performance Stats (Completed Trades) ===")
        print(f"Total Trades: {len(completed)}")

        wins = completed[completed['is_win'] == True]
        losses = completed[completed['is_win'] == False]

        print(f"Wins: {len(wins)} ({len(wins)/len(completed)*100:.1f}%)")
        print(f"Losses: {len(losses)} ({len(losses)/len(completed)*100:.1f}%)")

        print(f"\nReturns:")
        print(f"  Mean: {completed['actual_return_pct'].mean()*100:.2f}%")
        print(f"  Std Dev: {completed['actual_return_pct'].std()*100:.2f}%")
        print(f"  Best: {completed['actual_return_pct'].max()*100:.2f}%")
        print(f"  Worst: {completed['actual_return_pct'].min()*100:.2f}%")

        # Compare to claimed performance
        print(f"\n=== vs Claimed Performance ===")
        claimed_win_rate = 0.66
        claimed_mean_return = 0.073

        actual_win_rate = len(wins) / len(completed)
        actual_mean_return = completed['actual_return_pct'].mean()

        print(f"Win Rate: {actual_win_rate*100:.1f}% (claimed: {claimed_win_rate*100:.1f}%)")
        print(f"Mean Return: {actual_mean_return*100:.2f}% (claimed: {claimed_mean_return*100:.1f}%)")

        if abs(actual_win_rate - claimed_win_rate) < 0.1:
            print("✓ Win rate matches claimed performance!")
        else:
            diff = (actual_win_rate - claimed_win_rate) * 100
            print(f"{'⚠' if diff < 0 else '✓'} Win rate is {abs(diff):.1f}% {'lower' if diff < 0 else 'higher'} than claimed")

    # Show recent trades
    print(f"\n=== Recent Scans ===")
    recent = df.tail(10).sort_values('scan_date', ascending=False)

    for _, trade in recent.iterrows():
        status_icon = {
            'pending': '⏳',
            'completed': '✓' if trade.get('is_win') else '✗',
            'skipped': '−'
        }.get(trade['status'], '?')

        print(f"\n{status_icon} {trade['ticker']} - {trade['earnings_date']}")
        print(f"  Scanned: {trade['scan_date']}")
        print(f"  Recommendation: {trade['recommendation']}")
        print(f"  Term Slope: {trade['term_slope']:.4f} | IV/RV: {trade['iv_rv_ratio']:.2f}")

        if trade['status'] == 'completed':
            print(f"  Move: {trade['stock_move_pct']*100:.2f}% | P&L: {trade['actual_return_pct']*100:.2f}%")

def main():
    parser = argparse.ArgumentParser(description='View trade history database')
    parser.add_argument('--status', type=str, choices=['pending', 'completed', 'skipped'],
                       help='Filter by status')
    parser.add_argument('--export', type=str, help='Export to CSV file')

    args = parser.parse_args()

    view_database(filter_status=args.status)

    if args.export:
        db_path = Path(DATABASE_FILE)
        if db_path.exists():
            df = pd.read_csv(db_path)
            if args.status:
                df = df[df['status'] == args.status]
            df.to_csv(args.export, index=False)
            print(f"\n✓ Exported to {args.export}")

if __name__ == "__main__":
    main()

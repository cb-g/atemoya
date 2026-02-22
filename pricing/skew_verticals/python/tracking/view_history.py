#!/usr/bin/env python3
"""
View Trade History

Displays and analyzes forward-testing results.
"""

import pandas as pd
from pathlib import Path
import argparse

DATABASE_FILE = "pricing/skew_verticals/data/trade_history.csv"

def view_history(filter_recommendation: str = None):
    """View trade history with statistics."""

    db_path = Path(DATABASE_FILE)
    if not db_path.exists():
        print(f"✗ Database not found: {db_path}")
        return

    df = pd.read_csv(db_path)

    if len(df) == 0:
        print("No trades in database yet.")
        return

    # Filter if requested
    if filter_recommendation:
        df = df[df['recommendation'] == filter_recommendation]
        print(f"\nFiltered to: {filter_recommendation}")

    # Summary stats
    total = len(df)
    pending = len(df[df['status'] == 'pending'])
    completed = len(df[df['status'] == 'completed'])

    print(f"\n=== Trade History Summary ===")
    print(f"Total scans: {total}")
    print(f"Pending: {pending}")
    print(f"Completed: {completed}")

    # Recommendation breakdown
    print(f"\n=== Recommendations ===")
    rec_counts = df['recommendation'].value_counts()
    for rec, count in rec_counts.items():
        print(f"  {rec}: {count}")

    # Filter breakdown
    print(f"\n=== Filter Pass Rates ===")
    print(f"  Skew filter: {df['passes_skew_filter'].sum()}/{total} ({df['passes_skew_filter'].mean()*100:.1f}%)")
    print(f"  IV/RV filter: {df['passes_ivrv_filter'].sum()}/{total} ({df['passes_ivrv_filter'].mean()*100:.1f}%)")
    print(f"  Momentum filter: {df['passes_momentum_filter'].sum()}/{total} ({df['passes_momentum_filter'].mean()*100:.1f}%)")

    # Completed trades analysis
    if completed > 0:
        completed_df = df[df['status'] == 'completed'].copy()

        print(f"\n=== Completed Trades Performance ===")
        print(f"Total completed: {completed}")

        # Overall stats
        avg_return = completed_df['actual_return_pct'].mean()
        median_return = completed_df['actual_return_pct'].median()
        win_rate = (completed_df['actual_pnl'] > 0).mean() * 100
        wins = (completed_df['actual_pnl'] > 0).sum()
        losses = (completed_df['actual_pnl'] <= 0).sum()

        print(f"\nOverall:")
        print(f"  Win rate: {win_rate:.1f}% ({wins}W/{losses}L)")
        print(f"  Average return: {avg_return:+.1f}%")
        print(f"  Median return: {median_return:+.1f}%")

        # Breakdown by recommendation
        print(f"\nBy Recommendation:")
        for rec in ['Strong Buy', 'Buy', 'Pass']:
            rec_df = completed_df[completed_df['recommendation'] == rec]
            if len(rec_df) > 0:
                rec_win_rate = (rec_df['actual_pnl'] > 0).mean() * 100
                rec_avg_return = rec_df['actual_return_pct'].mean()
                print(f"  {rec}: {len(rec_df)} trades | {rec_win_rate:.1f}% win rate | {rec_avg_return:+.1f}% avg return")

        # Breakdown by spread type
        print(f"\nBy Spread Type:")
        for spread_type in completed_df['spread_type'].unique():
            st_df = completed_df[completed_df['spread_type'] == spread_type]
            st_win_rate = (st_df['actual_pnl'] > 0).mean() * 100
            st_avg_return = st_df['actual_return_pct'].mean()
            print(f"  {spread_type}: {len(st_df)} trades | {st_win_rate:.1f}% win rate | {st_avg_return:+.1f}% avg return")

        # Top performers
        print(f"\n=== Top 5 Winners ===")
        top_winners = completed_df.nlargest(5, 'actual_return_pct')[
            ['ticker', 'spread_type', 'actual_return_pct', 'actual_pnl', 'recommendation']
        ]
        print(top_winners.to_string(index=False))

        # Worst performers
        print(f"\n=== Top 5 Losers ===")
        top_losers = completed_df.nsmallest(5, 'actual_return_pct')[
            ['ticker', 'spread_type', 'actual_return_pct', 'actual_pnl', 'recommendation']
        ]
        print(top_losers.to_string(index=False))

    # Pending trades
    if pending > 0:
        print(f"\n=== Pending Trades ===")
        pending_df = df[df['status'] == 'pending'][
            ['ticker', 'expiration', 'spread_type', 'recommendation', 'edge_score']
        ].sort_values('expiration')
        print(pending_df.to_string(index=False))

    print()

def main():
    parser = argparse.ArgumentParser(description='View trade history')
    parser.add_argument('--filter', type=str, choices=['Strong Buy', 'Buy', 'Pass'],
                       help='Filter by recommendation')

    args = parser.parse_args()

    view_history(filter_recommendation=args.filter)

if __name__ == "__main__":
    main()

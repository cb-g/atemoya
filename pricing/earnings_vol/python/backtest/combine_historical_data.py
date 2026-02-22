#!/usr/bin/env python3
"""
Combine historical earnings events and metrics into single CSV for backtest.
"""

import pandas as pd
from pathlib import Path
import argparse

def main():
    parser = argparse.ArgumentParser(description='Combine historical data for backtest')
    parser.add_argument('--events', type=str,
                       default='pricing/earnings_vol/data/backtest/historical_earnings_events.csv',
                       help='Historical earnings events CSV')
    parser.add_argument('--metrics', type=str,
                       default='pricing/earnings_vol/data/backtest/historical_metrics.csv',
                       help='Historical metrics CSV')
    parser.add_argument('--output', type=str,
                       default='pricing/earnings_vol/data/backtest/historical_combined.csv',
                       help='Output combined CSV')

    args = parser.parse_args()

    print("\nCombining historical data...")

    # Load earnings events
    events_df = pd.read_csv(args.events)
    print(f"  Loaded {len(events_df)} earnings events")

    # Load metrics
    metrics_df = pd.read_csv(args.metrics)
    print(f"  Loaded {len(metrics_df)} metrics")

    # Merge on ticker + earnings_date
    combined = pd.merge(
        events_df,
        metrics_df,
        on=['ticker', 'earnings_date'],
        how='inner'
    )

    # Filter out events with missing data
    combined = combined.dropna(subset=['pre_close', 'post_close', 'avg_volume_30d'])

    print(f"\n  Combined: {len(combined)} events with complete data")

    # Save
    combined.to_csv(args.output, index=False)

    print(f"\n✅ Combined data saved: {args.output}")
    print(f"  Date range: {combined['earnings_date'].min()} to {combined['earnings_date'].max()}")
    print(f"  Tickers: {combined['ticker'].nunique()}")

if __name__ == "__main__":
    main()

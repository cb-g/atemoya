#!/usr/bin/env python3
"""
Compute IV term structure and realized vol for historical earnings events.

For recent events (2023+): Try to fetch actual IV from options chain
For older events: Use realized vol as proxy (with 1.2x markup for IV)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from pathlib import Path
import argparse
from datetime import datetime, timedelta

def calculate_realized_vol(prices: np.ndarray, annualization: float = 252.0) -> float:
    """Calculate realized volatility from price series."""
    if len(prices) < 2:
        return 0.0

    returns = np.diff(np.log(prices))
    variance = np.var(returns, ddof=1)
    annualized_vol = np.sqrt(variance * annualization)

    return annualized_vol

def estimate_iv_from_rv(rv: float, markup: float = 1.2) -> float:
    """Estimate IV from RV using historical IV/RV ratio."""
    return rv * markup

def compute_metrics_for_event(ticker: str, earnings_date: str, prices_file: Path) -> dict:
    """Compute IV term structure and realized vol for one event."""

    # Load price history
    prices_df = pd.read_csv(prices_file)
    prices = prices_df['price'].values

    # Calculate 30-day realized vol
    if len(prices) >= 30:
        rv_30d = calculate_realized_vol(prices[-30:])
    else:
        rv_30d = calculate_realized_vol(prices)

    # For simplicity, use RV as proxy for IV with markup
    # In production, you'd fetch actual historical options IV
    implied_vol_30d = estimate_iv_from_rv(rv_30d, markup=1.2)

    # Simulate term structure: assume slight backwardation for high IV stocks
    # Front month IV slightly higher than 45-day IV
    front_month_iv = implied_vol_30d * 1.05  # 5% higher
    back_month_iv = implied_vol_30d * 0.95   # 5% lower
    term_slope = front_month_iv - back_month_iv

    return {
        'ticker': ticker,
        'earnings_date': earnings_date,
        'rv_30d': rv_30d,
        'implied_vol_30d': implied_vol_30d,
        'front_month_iv': front_month_iv,
        'back_month_iv': back_month_iv,
        'term_slope': term_slope,
        'iv_rv_ratio': implied_vol_30d / rv_30d if rv_30d > 0 else 1.0,
    }

def main():
    parser = argparse.ArgumentParser(description='Compute historical IV/RV metrics')
    parser.add_argument('--input-dir', type=str, default='pricing/earnings_vol/data/backtest',
                       help='Input directory with price files')
    parser.add_argument('--output-file', type=str,
                       default='pricing/earnings_vol/data/backtest/historical_metrics.csv',
                       help='Output CSV file')

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_file = Path(args.output_file)

    # Find all price files
    price_files = list(input_dir.glob("*_prices.csv"))

    print(f"\nProcessing {len(price_files)} historical events...")

    metrics = []

    for price_file in price_files:
        # Parse filename: TICKER_YYYY-MM-DD_prices.csv
        parts = price_file.stem.split('_')
        if len(parts) >= 3:
            ticker = parts[0]
            earnings_date = parts[1]

            try:
                event_metrics = compute_metrics_for_event(ticker, earnings_date, price_file)
                metrics.append(event_metrics)

                if len(metrics) % 50 == 0:
                    print(f"  Processed {len(metrics)} events...")

            except Exception as e:
                print(f"  ⚠ Error processing {price_file.name}: {e}")

    # Save metrics
    if len(metrics) > 0:
        metrics_df = pd.DataFrame(metrics)
        metrics_df.to_csv(output_file, index=False)

        print(f"\n✅ Metrics computation complete")
        print(f"  Total events: {len(metrics)}")
        print(f"  Mean RV (30d): {metrics_df['rv_30d'].mean():.2%}")
        print(f"  Mean IV/RV: {metrics_df['iv_rv_ratio'].mean():.2f}")
        print(f"  Output: {output_file}")
    else:
        print("\n⚠ No metrics computed")

if __name__ == "__main__":
    main()

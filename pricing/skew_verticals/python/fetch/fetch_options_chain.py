#!/usr/bin/env python3
"""
Fetch complete options chain with IVs, deltas, and prices.

Required for skew-based vertical spread analysis.
"""

import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf
import pandas as pd
import numpy as np
import argparse
from datetime import datetime

from lib.python.retry import retry_with_backoff

def fetch_options_chain(ticker: str, expiration: str, output_dir: Path):
    """Fetch full options chain for a specific expiration."""

    print(f"\nFetching options chain for {ticker} expiring {expiration}...")

    stock = yf.Ticker(ticker)
    info = retry_with_backoff(lambda: stock.info)
    spot = info.get('currentPrice', info.get('regularMarketPrice', 100))

    print(f"  Spot price: ${spot:.2f}")

    try:
        # Get options chain
        opt_chain = retry_with_backoff(lambda: stock.option_chain(expiration))
        calls = opt_chain.calls
        puts = opt_chain.puts

        if len(calls) == 0:
            print(f"  ✗ No options data for {expiration}")
            return None

        # Calculate days to expiry
        exp_date = pd.to_datetime(expiration)
        days_to_exp = (exp_date - datetime.now()).days

        # Find ATM strike
        all_strikes = calls['strike'].values
        atm_strike = all_strikes[np.argmin(np.abs(all_strikes - spot))]

        print(f"  ATM strike: ${atm_strike:.2f}")
        print(f"  Days to expiry: {days_to_exp}")

        # Process calls (vectorized)
        calls_df = pd.DataFrame({
            'strike': calls['strike'].values,
            'option_type': 'call',
            'implied_vol': calls.get('impliedVolatility', pd.Series([0.0] * len(calls))).fillna(0).values,
            'bid': calls.get('bid', pd.Series([0.0] * len(calls))).fillna(0).values,
            'ask': calls.get('ask', pd.Series([0.0] * len(calls))).fillna(0).values,
            'open_interest': calls.get('openInterest', pd.Series([0] * len(calls))).fillna(0).values,
            'volume': calls.get('volume', pd.Series([0] * len(calls))).fillna(0).values,
        })

        # Calculate mid price vectorized
        valid_quotes = (calls_df['bid'] > 0) & (calls_df['ask'] > 0)
        calls_df['mid_price'] = np.where(
            valid_quotes,
            (calls_df['bid'] + calls_df['ask']) / 2,
            calls.get('lastPrice', pd.Series([0.0] * len(calls))).fillna(0).values
        )

        # Approximate delta for calls (vectorized)
        # ITM: delta = 0.5 + 0.4 * (S - K) / S
        # OTM: delta = 0.5 - 0.4 * (K - S) / S
        moneyness = (spot - calls_df['strike']) / spot
        calls_df['delta'] = np.clip(0.5 + 0.4 * moneyness, 0.01, 0.99)

        # Process puts (vectorized)
        puts_df = pd.DataFrame({
            'strike': puts['strike'].values,
            'option_type': 'put',
            'implied_vol': puts.get('impliedVolatility', pd.Series([0.0] * len(puts))).fillna(0).values,
            'bid': puts.get('bid', pd.Series([0.0] * len(puts))).fillna(0).values,
            'ask': puts.get('ask', pd.Series([0.0] * len(puts))).fillna(0).values,
            'open_interest': puts.get('openInterest', pd.Series([0] * len(puts))).fillna(0).values,
            'volume': puts.get('volume', pd.Series([0] * len(puts))).fillna(0).values,
        })

        # Calculate mid price vectorized
        valid_quotes = (puts_df['bid'] > 0) & (puts_df['ask'] > 0)
        puts_df['mid_price'] = np.where(
            valid_quotes,
            (puts_df['bid'] + puts_df['ask']) / 2,
            puts.get('lastPrice', pd.Series([0.0] * len(puts))).fillna(0).values
        )

        # Approximate delta for puts (vectorized, stored as positive)
        # ITM (K > S): |delta| = 0.5 + 0.4 * (K - S) / S
        # OTM (K < S): |delta| = 0.5 - 0.4 * (S - K) / S
        moneyness = (puts_df['strike'] - spot) / spot
        puts_df['delta'] = np.clip(0.5 + 0.4 * moneyness, 0.01, 0.99)
        # Replace NaN with 0.0 for numeric columns
        numeric_cols = ['strike', 'implied_vol', 'delta', 'bid', 'ask', 'mid_price', 'open_interest', 'volume']
        for col in numeric_cols:
            if col in calls_df.columns:
                calls_df[col] = calls_df[col].fillna(0.0)
        calls_file = output_dir / f"{ticker}_{expiration}_calls.csv"
        calls_df.to_csv(calls_file, index=False)

        # Save puts (puts_df already created above)
        for col in numeric_cols:
            if col in puts_df.columns:
                puts_df[col] = puts_df[col].fillna(0.0)
        puts_file = output_dir / f"{ticker}_{expiration}_puts.csv"
        puts_df.to_csv(puts_file, index=False)

        # Save metadata
        metadata = pd.DataFrame([{
            'ticker': ticker,
            'spot_price': spot,
            'expiration': expiration,
            'days_to_expiry': days_to_exp,
            'atm_strike': atm_strike,
            'num_calls': len(calls_df),
            'num_puts': len(puts_df),
        }])
        meta_file = output_dir / f"{ticker}_{expiration}_metadata.csv"
        metadata.to_csv(meta_file, index=False)

        print(f"\n✓ Options chain saved:")
        print(f"  Calls: {calls_file}")
        print(f"  Puts: {puts_file}")
        print(f"  {len(calls_df)} call strikes, {len(puts_df)} put strikes")

        return {
            'calls': calls_df,
            'puts': puts_df,
            'metadata': metadata.iloc[0].to_dict()
        }

    except Exception as e:
        print(f"  ✗ Error fetching options chain: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Fetch options chain')
    parser.add_argument('--ticker', type=str, required=True, help='Stock ticker')
    parser.add_argument('--expiration', type=str, help='Expiration date (YYYY-MM-DD). If not provided, uses nearest expiration.')
    parser.add_argument('--output-dir', type=str, default='pricing/skew_verticals/data',
                       help='Output directory')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get expiration
    if args.expiration:
        expiration = args.expiration
    else:
        # Get nearest expiration
        stock = yf.Ticker(args.ticker)
        expirations = retry_with_backoff(lambda: stock.options)
        if len(expirations) == 0:
            print(f"✗ No options available for {args.ticker}")
            return

        # Find expiration 7-30 days out
        today = datetime.now()
        valid_exps = []
        for exp in expirations:
            exp_date = pd.to_datetime(exp)
            days = (exp_date - today).days
            if 7 <= days <= 30:
                valid_exps.append((days, exp))

        if len(valid_exps) == 0:
            # Just use nearest
            expiration = expirations[0]
        else:
            # Use closest to 2 weeks
            valid_exps.sort(key=lambda x: abs(x[0] - 14))
            expiration = valid_exps[0][1]

        print(f"Using expiration: {expiration}")

    fetch_options_chain(args.ticker, expiration, output_dir)

if __name__ == "__main__":
    main()

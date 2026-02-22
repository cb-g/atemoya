#!/usr/bin/env python3
"""
Fetch implied volatility term structure for earnings analysis.
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

def fetch_iv_term_structure(ticker: str, output_dir: Path):
    """Fetch IV term structure from options chain."""

    stock = yf.Ticker(ticker)
    info = retry_with_backoff(lambda: stock.info)
    spot = info.get('currentPrice', info.get('regularMarketPrice', 100))

    # Get all available expirations
    expirations = retry_with_backoff(lambda: stock.options)

    if len(expirations) == 0:
        print(f"⚠ No options data available for {ticker}")
        return

    print(f"Found {len(expirations)} expiration dates")

    iv_data = []

    for expiration in expirations:
        try:
            # Calculate days to expiry
            exp_date = datetime.strptime(expiration, '%Y-%m-%d')
            days_to_exp = (exp_date - datetime.now()).days

            if days_to_exp < 1 or days_to_exp > 90:
                continue  # Only use 1-90 day expirations

            # Get options chain
            opt_chain = retry_with_backoff(lambda exp=expiration: stock.option_chain(exp))
            calls = opt_chain.calls
            puts = opt_chain.puts

            if len(calls) == 0:
                continue

            # Find ATM strike
            atm_strike = calls.iloc[(calls['strike'] - spot).abs().argsort()[0]]['strike']

            # Get ATM call IV
            atm_call = calls[calls['strike'] == atm_strike]
            if len(atm_call) > 0 and 'impliedVolatility' in atm_call.columns:
                atm_iv = atm_call['impliedVolatility'].iloc[0]

                iv_data.append({
                    'expiration': expiration,
                    'days_to_expiry': days_to_exp,
                    'atm_iv': atm_iv,
                    'strike': atm_strike
                })

                print(f"  {expiration} ({days_to_exp}d): IV={atm_iv:.2%}, K=${atm_strike:.2f}")

        except Exception as e:
            print(f"  ⚠ Error processing {expiration}: {e}")
            continue

    if len(iv_data) == 0:
        print(f"⚠ No valid IV data found for {ticker}")
        return

    # Save IV term structure
    df = pd.DataFrame(iv_data)
    df = df.sort_values('days_to_expiry')

    iv_file = output_dir / f"{ticker}_iv_term.csv"
    df.to_csv(iv_file, index=False)

    print(f"\n✓ IV term structure saved: {iv_file}")
    print(f"  Expirations: {len(df)}")
    print(f"  Front month IV: {df.iloc[0]['atm_iv']:.2%}")
    if len(df) > 1:
        print(f"  Back month IV (~45d): {df.iloc[-1]['atm_iv']:.2%}")

def main():
    parser = argparse.ArgumentParser(description='Fetch IV term structure')
    parser.add_argument('--ticker', type=str, required=True, help='Stock ticker')
    parser.add_argument('--output-dir', type=str, default='pricing/earnings_vol/data',
                       help='Output directory')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nFetching IV term structure for {args.ticker}...")
    fetch_iv_term_structure(args.ticker, output_dir)

    print(f"\n✅ IV fetch complete for {args.ticker}")

if __name__ == "__main__":
    main()

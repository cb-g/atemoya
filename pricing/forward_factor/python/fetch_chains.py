#!/usr/bin/env python3
"""
Fetch options chains for forward factor scanning.

This script fetches options data for a universe of tickers and calculates:
- ATM implied volatility for each expiration
- ATM strike and prices (call + put)
- 35-delta strikes and prices (for double calendars)

Output format: JSON compatible with OCaml scanner
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[3]))

import yfinance as yf

from lib.python.retry import retry_with_backoff


def calculate_dte(expiration_str: str) -> int:
    """Calculate days to expiration from date string."""
    exp_date = datetime.strptime(expiration_str, "%Y-%m-%d")
    today = datetime.now()
    return (exp_date - today).days


def find_atm_strike(ticker_obj, expiration: str, spot_price: float) -> Optional[float]:
    """Find the ATM strike closest to spot price."""
    try:
        chain = retry_with_backoff(lambda: ticker_obj.option_chain(expiration))
        calls = chain.calls

        # Find strike closest to spot
        calls['diff'] = abs(calls['strike'] - spot_price)
        atm_row = calls.loc[calls['diff'].idxmin()]
        return float(atm_row['strike'])
    except Exception as e:
        print(f"  Error finding ATM strike: {e}")
        return None


def estimate_delta_35_strikes(atm_strike: float, spot_price: float) -> tuple:
    """
    Estimate 35-delta strikes.

    For SPY/broad indices: ~0.5-1 standard deviation out
    For individual stocks: adjust based on IV

    This is a rough approximation. For accurate deltas, use:
    - mibian library for Black-Scholes
    - Actual exchange delta data if available
    """
    # Simple approximation: 35-delta is roughly 5-7% OTM
    otm_percent = 0.06  # 6% OTM

    call_strike = atm_strike * (1 + otm_percent)
    put_strike = atm_strike * (1 - otm_percent)

    return call_strike, put_strike


def get_option_price(ticker_obj, expiration: str, strike: float, option_type: str) -> Optional[float]:
    """Get option price (midpoint of bid-ask) for given strike."""
    try:
        chain = retry_with_backoff(lambda: ticker_obj.option_chain(expiration))
        options = chain.calls if option_type == 'call' else chain.puts

        # Find exact strike or closest
        option_row = options[options['strike'] == strike]
        if option_row.empty:
            # Find closest strike
            options['diff'] = abs(options['strike'] - strike)
            option_row = options.loc[[options['diff'].idxmin()]]

        # Use midpoint of bid-ask
        bid = float(option_row['bid'].iloc[0])
        ask = float(option_row['ask'].iloc[0])

        if bid > 0 and ask > 0:
            return (bid + ask) / 2.0
        else:
            return float(option_row['lastPrice'].iloc[0])
    except Exception as e:
        print(f"  Error getting price for {option_type} strike {strike}: {e}")
        return None


def calculate_atm_iv(ticker_obj, expiration: str, atm_strike: float) -> Optional[float]:
    """Get ATM implied volatility (average of call and put)."""
    try:
        chain = retry_with_backoff(lambda: ticker_obj.option_chain(expiration))

        # Get ATM call and put IV
        calls = chain.calls[chain.calls['strike'] == atm_strike]
        puts = chain.puts[chain.puts['strike'] == atm_strike]

        call_iv = float(calls['impliedVolatility'].iloc[0]) if not calls.empty else None
        put_iv = float(puts['impliedVolatility'].iloc[0]) if not puts.empty else None

        # Average if both available
        if call_iv and put_iv:
            return (call_iv + put_iv) / 2.0
        elif call_iv:
            return call_iv
        elif put_iv:
            return put_iv
        else:
            return None
    except Exception as e:
        print(f"  Error calculating IV: {e}")
        return None


def fetch_ticker_expirations(
    ticker: str,
    target_dtes: List[int] = [30, 60, 90]
) -> List[Dict]:
    """
    Fetch options chain data for a ticker.

    Returns list of expiration data compatible with OCaml types.
    """
    print(f"\nFetching {ticker}...")

    try:
        ticker_obj = yf.Ticker(ticker)
        spot_price = retry_with_backoff(lambda: ticker_obj.history(period="1d"))['Close'].iloc[-1]

        # Get all expirations
        expirations = retry_with_backoff(lambda: ticker_obj.options)

        if not expirations:
            print(f"  No expirations found for {ticker}")
            return []

        results = []

        for exp_str in expirations:
            dte = calculate_dte(exp_str)

            # Only fetch expirations near our target DTEs
            if not any(abs(dte - target) <= 7 for target in target_dtes):
                continue

            if dte < 20 or dte > 120:
                continue

            print(f"  Processing expiration: {exp_str} ({dte} DTE)")

            # Find ATM strike
            atm_strike = find_atm_strike(ticker_obj, exp_str, spot_price)
            if atm_strike is None:
                continue

            # Get ATM prices
            atm_call_price = get_option_price(ticker_obj, exp_str, atm_strike, 'call')
            atm_put_price = get_option_price(ticker_obj, exp_str, atm_strike, 'put')

            if atm_call_price is None or atm_put_price is None:
                continue

            # Get ATM IV
            atm_iv = calculate_atm_iv(ticker_obj, exp_str, atm_strike)
            if atm_iv is None or atm_iv <= 0:
                continue

            # Estimate 35-delta strikes
            delta_35_call_strike, delta_35_put_strike = estimate_delta_35_strikes(
                atm_strike, spot_price
            )

            # Get 35-delta prices
            delta_35_call_price = get_option_price(
                ticker_obj, exp_str, delta_35_call_strike, 'call'
            )
            delta_35_put_price = get_option_price(
                ticker_obj, exp_str, delta_35_put_strike, 'put'
            )

            if delta_35_call_price is None or delta_35_put_price is None:
                continue

            # Build expiration data
            exp_data = {
                'ticker': ticker,
                'expiration': exp_str,
                'dte': dte,
                'atm_iv': atm_iv,
                'atm_strike': atm_strike,
                'atm_call_price': atm_call_price,
                'atm_put_price': atm_put_price,
                'delta_35_call_strike': delta_35_call_strike,
                'delta_35_call_price': delta_35_call_price,
                'delta_35_put_strike': delta_35_put_strike,
                'delta_35_put_price': delta_35_put_price,
            }

            results.append(exp_data)
            print(f"    ✓ ATM IV: {atm_iv:.2%}, Strike: ${atm_strike:.2f}")

        return results

    except Exception as e:
        print(f"  Error fetching {ticker}: {e}")
        return []


def main():
    """Fetch options chains for default universe."""

    # Default universe: high liquidity names
    universe = [
        'SPY',    # S&P 500 ETF
        'QQQ',    # Nasdaq ETF
        'IWM',    # Russell 2000 ETF
        'AAPL',   # Apple
        'MSFT',   # Microsoft
        'AMZN',   # Amazon
        'GOOGL',  # Google
        'TSLA',   # Tesla
        'NVDA',   # Nvidia
    ]

    print("=" * 70)
    print("Forward Factor Options Chain Fetcher")
    print("=" * 70)
    print(f"Universe: {', '.join(universe)}")
    print(f"Target DTEs: 30, 60, 90")

    # Fetch all tickers
    all_data = {}
    for ticker in universe:
        expirations = fetch_ticker_expirations(ticker)
        if expirations:
            all_data[ticker] = expirations

    # Save to JSON
    output_dir = Path(__file__).parent.parent / 'data'
    output_dir.mkdir(exist_ok=True, parents=True)

    output_file = output_dir / 'options_chains.json'
    with open(output_file, 'w') as f:
        json.dump(all_data, f, indent=2)

    print(f"\n{'=' * 70}")
    print(f"✓ Saved {len(all_data)} tickers to: {output_file}")
    print(f"{'=' * 70}\n")

    # Print summary
    for ticker, exps in all_data.items():
        print(f"{ticker}: {len(exps)} expirations")
        for exp in exps:
            print(f"  {exp['expiration']} ({exp['dte']} DTE) - IV: {exp['atm_iv']:.2%}")


if __name__ == '__main__':
    main()

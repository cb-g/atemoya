#!/usr/bin/env python3
"""
Fetch Current Straddle Opportunity

Fetches current ATM straddle data for upcoming earnings:
- Earnings date
- ATM strike
- ATM call/put prices
- Current implied move

Uses the unified data provider system (IBKR if available, yfinance fallback).
Earnings dates are always fetched via yfinance (provider system doesn't wrap earnings calendars).

This is the "current opportunity" that we compare against history.
"""

import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import argparse

from lib.python.retry import retry_with_backoff
from lib.python.data_fetcher import get_provider


def find_atm_strike(spot: float, strikes: list) -> float:
    """Find ATM strike closest to spot price."""
    if len(strikes) == 0:
        return spot

    strikes_array = np.array(strikes)
    closest_idx = np.argmin(np.abs(strikes_array - spot))
    return strikes_array[closest_idx]

def calculate_implied_move_from_iv(iv: float, days: int) -> float:
    """
    Calculate 1-day implied move from annualized IV.

    Formula: sqrt(2/pi) * sigma * sqrt(1/365)
    """
    if days <= 0:
        return 0.0

    one_day_vol = iv * np.sqrt(1/365)
    implied_move = 0.798 * one_day_vol
    return implied_move

def fetch_straddle_opportunity(ticker: str, output_dir: Path):
    """
    Fetch current straddle opportunity for upcoming earnings.
    """

    provider = get_provider()
    print(f"\nFetching straddle opportunity for {ticker}...")
    print(f"  Data provider: {provider.name}")

    # Get next earnings date (always via yfinance — provider system doesn't wrap earnings)
    stock = yf.Ticker(ticker)

    try:
        earnings_dates = retry_with_backoff(lambda: stock.earnings_dates)
        if earnings_dates is None or len(earnings_dates) == 0:
            print(f"  x No earnings data available")
            return None

        # Find next earnings date
        future_earnings = [d for d in earnings_dates.index if d.date() > datetime.now().date()]
        if len(future_earnings) == 0:
            print(f"  x No upcoming earnings found")
            return None

        next_earnings = future_earnings[0]
        earnings_date_str = next_earnings.strftime('%Y-%m-%d')
        days_to_earnings = (next_earnings.date() - datetime.now().date()).days

        print(f"  Next earnings: {earnings_date_str} ({days_to_earnings} days)")

        # Check if we're in the entry window (~14 days before, +/- 4 days)
        if days_to_earnings < 10 or days_to_earnings > 18:
            print(f"  ! Outside ideal entry window (10-18 days before earnings)")
            print(f"    Current: {days_to_earnings} days")
            # Continue anyway for demo purposes

    except Exception as e:
        print(f"  x Error fetching earnings date: {e}")
        return None

    # Get current price via provider
    try:
        info = provider.fetch_ticker_info(ticker)
        if info is None:
            print(f"  x Could not get ticker info")
            return None

        current_price = info.price
        if current_price is None or current_price <= 0:
            print(f"  x Could not get current price")
            return None

        print(f"  Current price: ${current_price:.2f}")
    except Exception as e:
        print(f"  x Error fetching price: {e}")
        return None

    # Find expiration after earnings
    earnings_date = next_earnings.date()
    try:
        # Get available expiries from provider's option chain (fetches nearest 3 by default)
        chain = provider.fetch_option_chain(ticker)
        if chain is None or not chain.expiries:
            print(f"  x No options available")
            return None

        # Find first expiration after earnings
        valid_exps = []
        for exp_str in chain.expiries:
            exp_date = pd.to_datetime(exp_str).date()
            if exp_date > earnings_date:
                valid_exps.append((exp_date, exp_str))

        if len(valid_exps) == 0:
            # Need more expiries — try fetching with yfinance for full list
            stock_options = retry_with_backoff(lambda: stock.options)
            for exp_str in stock_options:
                exp_date = pd.to_datetime(exp_str).date()
                if exp_date > earnings_date:
                    valid_exps.append((exp_date, exp_str))

        if len(valid_exps) == 0:
            print(f"  x No expiration after earnings")
            return None

        # Use nearest expiration after earnings
        valid_exps.sort()
        expiration_date, expiration_str = valid_exps[0]
        days_to_expiry = (expiration_date - datetime.now().date()).days

        print(f"  Using expiration: {expiration_str} ({days_to_expiry} DTE)")

    except Exception as e:
        print(f"  x Error finding expiration: {e}")
        return None

    # Get options chain for the specific expiry via provider
    try:
        chain = provider.fetch_option_chain(ticker, expiry=expiration_str)
        if chain is None:
            print(f"  x No options data")
            return None

        calls = [c for c in chain.calls if c.expiry == expiration_str]
        puts = [p for p in chain.puts if p.expiry == expiration_str]

        if len(calls) == 0 or len(puts) == 0:
            print(f"  x No options data for expiry {expiration_str}")
            return None

        # Find ATM strike
        all_strikes = sorted(set(c.strike for c in calls))
        atm_strike = find_atm_strike(current_price, all_strikes)

        print(f"  ATM strike: ${atm_strike:.2f}")

        # Get ATM call and put
        atm_calls = [c for c in calls if c.strike == atm_strike]
        atm_puts = [p for p in puts if p.strike == atm_strike]

        if len(atm_calls) == 0 or len(atm_puts) == 0:
            print(f"  x Could not find ATM options")
            return None

        atm_call = atm_calls[0]
        atm_put = atm_puts[0]

        # Get prices (use mid of bid/ask)
        call_price = (atm_call.bid + atm_call.ask) / 2 if atm_call.bid > 0 and atm_call.ask > 0 else atm_call.last
        put_price = (atm_put.bid + atm_put.ask) / 2 if atm_put.bid > 0 and atm_put.ask > 0 else atm_put.last

        straddle_cost = call_price + put_price

        print(f"  Call price: ${call_price:.2f}")
        print(f"  Put price: ${put_price:.2f}")
        print(f"  Straddle cost: ${straddle_cost:.2f}")

        # Get IVs
        call_iv = atm_call.implied_volatility
        put_iv = atm_put.implied_volatility

        # Calculate current implied move
        avg_iv = (call_iv + put_iv) / 2
        current_implied_move = calculate_implied_move_from_iv(avg_iv, days_to_expiry)

        print(f"  ATM IV: {avg_iv*100:.1f}%")
        print(f"  Current implied move: {current_implied_move*100:.2f}%")

    except Exception as e:
        print(f"  x Error fetching options: {e}")
        return None

    # Create opportunity data
    opportunity = {
        'ticker': ticker,
        'earnings_date': earnings_date_str,
        'days_to_earnings': days_to_earnings,
        'spot_price': current_price,
        'atm_strike': atm_strike,
        'atm_call_price': call_price,
        'atm_put_price': put_price,
        'straddle_cost': straddle_cost,
        'current_implied_move': current_implied_move,
        'expiration': expiration_str,
        'days_to_expiry': days_to_expiry,
    }

    # Save to CSV
    df = pd.DataFrame([opportunity])
    output_file = output_dir / f"{ticker}_opportunity.csv"
    df.to_csv(output_file, index=False)

    print(f"\n+ Opportunity saved: {output_file}")

    return opportunity

def main():
    parser = argparse.ArgumentParser(description='Fetch straddle opportunity')
    parser.add_argument('--ticker', type=str, required=True, help='Stock ticker')
    parser.add_argument('--output-dir', type=str, default='pricing/pre_earnings_straddle/data',
                       help='Output directory')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fetch_straddle_opportunity(args.ticker, output_dir)

if __name__ == "__main__":
    main()

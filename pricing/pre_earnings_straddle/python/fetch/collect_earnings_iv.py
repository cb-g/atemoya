#!/usr/bin/env python3
"""
Daily earnings IV snapshot collector for pre-earnings straddle.

Captures ATM implied volatility for tickers with upcoming earnings,
building real implied move history over time. Designed for daily cron
execution after market close.

Each run:
- Checks which tickers have earnings within the entry window (18 days)
- Fetches ATM straddle IV (IBKR if available, yfinance fallback)
- Archives full snapshot to data/snapshots/{TICKER}/{YYYY-MM-DD}.json
- Appends one row to data/{TICKER}_iv_snapshots.csv

Idempotent: skips tickers already collected today.

The history CSV provides actual implied moves for fetch_earnings_data.py,
replacing the constant RV*1.2 assumption.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import argparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf
from lib.python.retry import retry_with_backoff
from lib.python.data_fetcher import get_provider

# CSV header for IV snapshot history
HISTORY_COLUMNS = [
    "date", "ticker", "spot", "earnings_date", "days_to_earnings",
    "avg_iv", "implied_move", "straddle_cost", "provider",
]


def already_collected_today(ticker: str, data_dir: Path) -> bool:
    """Check if today's snapshot already exists."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_file = data_dir / "snapshots" / ticker / f"{today}.json"
    return snapshot_file.exists()


def find_atm_strike(spot: float, strikes: list[float]) -> float:
    """Find ATM strike closest to spot price."""
    if not strikes:
        return spot
    arr = np.array(strikes)
    return arr[np.argmin(np.abs(arr - spot))]


def archive_snapshot(snapshot_data: dict, ticker: str, data_dir: Path) -> Path:
    """Save full snapshot to data/snapshots/{TICKER}/{YYYY-MM-DD}.json."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_dir = data_dir / "snapshots" / ticker
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    snapshot_file = snapshot_dir / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot_data, f, indent=2)

    print(f"  Archived snapshot: {snapshot_file}")
    return snapshot_file


def append_to_history(row: dict, ticker: str, data_dir: Path) -> None:
    """Append one row to {TICKER}_iv_snapshots.csv."""
    history_file = data_dir / f"{ticker}_iv_snapshots.csv"

    df = pd.DataFrame([row], columns=HISTORY_COLUMNS)

    if history_file.exists():
        df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        df.to_csv(history_file, index=False)

    print(f"  Appended to history: {history_file}")


def collect_one_ticker(ticker: str, data_dir: Path, entry_window: int = 18) -> bool:
    """
    Full collection pipeline for one ticker.

    Returns True if collection succeeded, False if skipped or failed.
    """
    print(f"\n{'='*60}")
    print(f"Collecting: {ticker}")
    print(f"{'='*60}")

    # Idempotency check
    if already_collected_today(ticker, data_dir):
        print(f"  Already collected today, skipping {ticker}")
        return False

    # Get next earnings date (always via yfinance)
    stock = yf.Ticker(ticker)
    try:
        earnings_dates = retry_with_backoff(lambda: stock.earnings_dates)
        if earnings_dates is None or len(earnings_dates) == 0:
            print(f"  No earnings data available, skipping {ticker}")
            return False

        future_earnings = [d for d in earnings_dates.index if d.date() > datetime.now().date()]
        if len(future_earnings) == 0:
            print(f"  No upcoming earnings, skipping {ticker}")
            return False

        next_earnings = future_earnings[0]
        earnings_date_str = next_earnings.strftime('%Y-%m-%d')
        days_to_earnings = (next_earnings.date() - datetime.now().date()).days

    except Exception as e:
        print(f"  ERROR fetching earnings for {ticker}: {e}")
        return False

    # Check if earnings is within entry window
    if days_to_earnings > entry_window:
        print(f"  Earnings {earnings_date_str} is {days_to_earnings} days away (window: {entry_window}), skipping")
        return False

    if days_to_earnings <= 0:
        print(f"  Earnings already passed, skipping")
        return False

    print(f"  Next earnings: {earnings_date_str} ({days_to_earnings} days)")

    # Get provider and fetch data
    provider = get_provider()
    print(f"  Provider: {provider.name}")

    # Get spot price
    try:
        info = provider.fetch_ticker_info(ticker)
        if info is None or info.price <= 0:
            print(f"  ERROR: Could not get spot price for {ticker}")
            return False
        spot = info.price
    except Exception as e:
        print(f"  ERROR fetching spot for {ticker}: {e}")
        return False

    # Find expiration after earnings and fetch option chain
    try:
        chain = provider.fetch_option_chain(ticker)
        if chain is None or not chain.expiries:
            print(f"  ERROR: No options available for {ticker}")
            return False

        # Find first expiration after earnings
        earnings_date = next_earnings.date()
        valid_exps = []
        for exp_str in chain.expiries:
            exp_date = pd.to_datetime(exp_str).date()
            if exp_date > earnings_date:
                valid_exps.append(exp_str)

        if not valid_exps:
            # Try full expiry list from yfinance
            stock_options = retry_with_backoff(lambda: stock.options)
            for exp_str in stock_options:
                exp_date = pd.to_datetime(exp_str).date()
                if exp_date > earnings_date:
                    valid_exps.append(exp_str)

        if not valid_exps:
            print(f"  ERROR: No expiration after earnings for {ticker}")
            return False

        target_expiry = sorted(valid_exps)[0]

        # Fetch chain for this specific expiry
        chain = provider.fetch_option_chain(ticker, expiry=target_expiry)
        if chain is None:
            print(f"  ERROR: Could not fetch chain for {target_expiry}")
            return False

        calls = [c for c in chain.calls if c.expiry == target_expiry]
        puts = [p for p in chain.puts if p.expiry == target_expiry]

        if not calls or not puts:
            print(f"  ERROR: No calls/puts for expiry {target_expiry}")
            return False

    except Exception as e:
        print(f"  ERROR fetching options for {ticker}: {e}")
        return False

    # Find ATM strike
    all_strikes = sorted(set(c.strike for c in calls))
    atm_strike = find_atm_strike(spot, all_strikes)

    # Get ATM call and put
    atm_calls = [c for c in calls if c.strike == atm_strike]
    atm_puts = [p for p in puts if p.strike == atm_strike]

    if not atm_calls or not atm_puts:
        print(f"  ERROR: Could not find ATM options at strike {atm_strike}")
        return False

    atm_call = atm_calls[0]
    atm_put = atm_puts[0]

    # Compute IVs and implied move
    call_iv = atm_call.implied_volatility
    put_iv = atm_put.implied_volatility
    avg_iv = (call_iv + put_iv) / 2

    # Implied move = sqrt(2/pi) * avg_IV * sqrt(1/365)
    implied_move = 0.798 * avg_iv * np.sqrt(1/365)

    # Straddle cost (mid price)
    call_price = (atm_call.bid + atm_call.ask) / 2 if atm_call.bid > 0 and atm_call.ask > 0 else atm_call.last
    put_price = (atm_put.bid + atm_put.ask) / 2 if atm_put.bid > 0 and atm_put.ask > 0 else atm_put.last
    straddle_cost = call_price + put_price

    print(f"  Spot:           ${spot:.2f}")
    print(f"  ATM strike:     ${atm_strike:.2f}")
    print(f"  ATM call IV:    {call_iv*100:.1f}%")
    print(f"  ATM put IV:     {put_iv*100:.1f}%")
    print(f"  Avg IV:         {avg_iv*100:.1f}%")
    print(f"  Implied move:   {implied_move*100:.2f}%")
    print(f"  Straddle cost:  ${straddle_cost:.2f}")

    # Archive full snapshot
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_data = {
        "date": today,
        "ticker": ticker,
        "spot": spot,
        "earnings_date": earnings_date_str,
        "days_to_earnings": days_to_earnings,
        "atm_strike": atm_strike,
        "atm_call_iv": call_iv,
        "atm_put_iv": put_iv,
        "avg_iv": avg_iv,
        "implied_move": implied_move,
        "straddle_cost": straddle_cost,
        "expiry": target_expiry,
        "provider": provider.name,
    }
    archive_snapshot(snapshot_data, ticker, data_dir)

    # Append to CSV history
    row = {
        "date": today,
        "ticker": ticker,
        "spot": spot,
        "earnings_date": earnings_date_str,
        "days_to_earnings": days_to_earnings,
        "avg_iv": avg_iv,
        "implied_move": implied_move,
        "straddle_cost": straddle_cost,
        "provider": provider.name,
    }
    append_to_history(row, ticker, data_dir)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Daily earnings IV snapshot collector for pre-earnings straddle"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", type=str, help="Single ticker symbol")
    group.add_argument("--tickers", type=str,
                       help="Comma-separated ticker list (e.g., AAPL,NVDA,TSLA)")
    parser.add_argument("--data-dir", type=str,
                        default="pricing/pre_earnings_straddle/data",
                        help="Data directory (default: pricing/pre_earnings_straddle/data)")
    parser.add_argument("--entry-window", type=int, default=18,
                        help="Days before earnings to start collecting (default: 18)")

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Parse ticker list
    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]

    print(f"Earnings IV Collection: {', '.join(tickers)}")
    print(f"Data dir: {data_dir}")
    print(f"Entry window: {args.entry_window} days")

    successes = 0
    for ticker in tickers:
        if collect_one_ticker(ticker, data_dir, args.entry_window):
            successes += 1

    print(f"\nCollection complete: {successes}/{len(tickers)} tickers collected")
    return 0 if successes > 0 or all(
        already_collected_today(t, data_dir) for t in tickers
    ) else 1


if __name__ == "__main__":
    exit(main())

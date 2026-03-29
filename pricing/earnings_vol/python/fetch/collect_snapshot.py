#!/usr/bin/env python3
"""
Daily earnings vol snapshot collector for IV crush strategy.

Captures IV term structure (front vs back month), volume, and realized vol
for tickers with upcoming earnings. Designed for daily cron after market close.

Each run:
- Checks which tickers have earnings within the entry window (18 days)
- Fetches front-month IV (expiry spanning earnings) and back-month IV (~45d later)
- Computes term structure slope, 30d avg volume, 30d realized vol, IV/RV ratio
- Archives full snapshot to data/snapshots/{TICKER}/{YYYY-MM-DD}.json
- Appends one row to data/{TICKER}_earnings_vol_yfinance.csv

Idempotent: skips tickers already collected today.

The 3-gate filter (term slope <= -0.05, volume >= 1M, IV/RV >= 1.1) is applied
by scan_signals.py, not here. This collector captures all metrics unconditionally.
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

# CSV header for earnings vol history
HISTORY_COLUMNS = [
    "date", "ticker", "spot", "earnings_date", "days_to_earnings",
    "front_iv", "back_iv", "term_slope", "volume", "rv", "iv_rv_ratio",
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


def compute_realized_vol(ticker: str, lookback: int = 30) -> float:
    """Compute annualized realized vol from close-to-close log returns."""
    stock = yf.Ticker(ticker)
    hist = retry_with_backoff(lambda: stock.history(period="3mo"))
    if hist is None or len(hist) < lookback:
        return 0.0

    closes = hist["Close"].values[-lookback:]
    log_returns = np.diff(np.log(closes))
    if len(log_returns) < 2:
        return 0.0

    return float(np.std(log_returns, ddof=1) * np.sqrt(252))


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
    """Append one row to {TICKER}_earnings_vol_yfinance.csv, skipping if date already exists."""
    history_file = data_dir / f"{ticker}_earnings_vol_yfinance.csv"

    df = pd.DataFrame([row], columns=HISTORY_COLUMNS)
    today = row["date"]

    if history_file.exists():
        existing = pd.read_csv(history_file, usecols=["date"], dtype=str)
        if today in existing["date"].values:
            print(f"  Skipped {ticker}: {today} already in history")
            return
        df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        df.to_csv(history_file, index=False)

    print(f"  Appended to history: {history_file}")


def get_atm_iv_for_expiry(provider, ticker: str, spot: float, expiry: str) -> float:
    """Fetch ATM IV for a specific expiration date."""
    chain = provider.fetch_option_chain(ticker, expiry=expiry)
    if chain is None:
        return 0.0

    calls = [c for c in chain.calls if c.expiry == expiry]
    puts = [p for p in chain.puts if p.expiry == expiry]

    if not calls or not puts:
        return 0.0

    all_strikes = sorted(set(c.strike for c in calls))
    atm_strike = find_atm_strike(spot, all_strikes)

    atm_calls = [c for c in calls if c.strike == atm_strike]
    atm_puts = [p for p in puts if p.strike == atm_strike]

    if not atm_calls or not atm_puts:
        return 0.0

    call_iv = atm_calls[0].implied_volatility
    put_iv = atm_puts[0].implied_volatility
    return (call_iv + put_iv) / 2


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

    # Get provider and fetch spot price
    provider = get_provider()
    print(f"  Provider: {provider.name}")

    try:
        info = provider.fetch_ticker_info(ticker)
        if info is None or info.price <= 0:
            print(f"  ERROR: Could not get spot price for {ticker}")
            return False
        spot = info.price
    except Exception as e:
        print(f"  ERROR fetching spot for {ticker}: {e}")
        return False

    # Get all available expirations
    try:
        chain = provider.fetch_option_chain(ticker)
        if chain is None or not chain.expiries:
            print(f"  ERROR: No options available for {ticker}")
            return False

        earnings_date = next_earnings.date()

        # Front month: first expiry AFTER earnings
        front_exps = sorted([
            e for e in chain.expiries
            if pd.to_datetime(e).date() > earnings_date
        ])

        if not front_exps:
            # Fallback to yfinance expiry list
            stock_options = retry_with_backoff(lambda: stock.options)
            front_exps = sorted([
                e for e in stock_options
                if pd.to_datetime(e).date() > earnings_date
            ])

        if not front_exps:
            print(f"  ERROR: No expiration after earnings for {ticker}")
            return False

        front_expiry = front_exps[0]

        # Back month: next expiry at least 30 days after front
        front_date = pd.to_datetime(front_expiry).date()
        back_exps = [
            e for e in (chain.expiries if chain.expiries else [])
            if (pd.to_datetime(e).date() - front_date).days >= 30
        ]
        if not back_exps:
            # Fallback
            stock_options = retry_with_backoff(lambda: stock.options) if 'stock_options' not in dir() else stock_options
            back_exps = [
                e for e in stock_options
                if (pd.to_datetime(e).date() - front_date).days >= 30
            ]

        if not back_exps:
            print(f"  ERROR: No back-month expiry for {ticker}")
            return False

        back_expiry = sorted(back_exps)[0]

    except Exception as e:
        print(f"  ERROR fetching expirations for {ticker}: {e}")
        return False

    # Fetch front and back month ATM IVs
    try:
        front_iv = retry_with_backoff(lambda: get_atm_iv_for_expiry(provider, ticker, spot, front_expiry))
        back_iv = retry_with_backoff(lambda: get_atm_iv_for_expiry(provider, ticker, spot, back_expiry))
    except Exception as e:
        print(f"  ERROR fetching IVs for {ticker}: {e}")
        return False

    if front_iv <= 0 or back_iv <= 0:
        print(f"  ERROR: Invalid IVs (front={front_iv:.4f}, back={back_iv:.4f}) for {ticker}")
        return False

    # Term structure slope: negative = backwardation (front > back)
    term_slope = front_iv - back_iv

    # 30-day average volume
    try:
        hist = retry_with_backoff(lambda: stock.history(period='1mo'))
        volume = float(hist['Volume'].mean()) if len(hist) > 0 else 0.0
    except Exception:
        volume = 0.0

    # Realized vol (30-day close-to-close)
    try:
        rv = compute_realized_vol(ticker, lookback=30)
    except Exception:
        rv = 0.0

    # IV/RV ratio (use front month IV as the "implied" side)
    iv_rv_ratio = front_iv / rv if rv > 0 else 0.0

    print(f"  Spot:           ${spot:.2f}")
    print(f"  Front expiry:   {front_expiry} (IV={front_iv*100:.1f}%)")
    print(f"  Back expiry:    {back_expiry} (IV={back_iv*100:.1f}%)")
    print(f"  Term slope:     {term_slope:+.4f}")
    print(f"  Avg volume:     {volume:,.0f}")
    print(f"  Realized vol:   {rv*100:.1f}%")
    print(f"  IV/RV ratio:    {iv_rv_ratio:.2f}")

    # Archive full snapshot
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_data = {
        "date": today,
        "ticker": ticker,
        "spot": spot,
        "earnings_date": earnings_date_str,
        "days_to_earnings": days_to_earnings,
        "front_expiry": front_expiry,
        "back_expiry": back_expiry,
        "front_iv": front_iv,
        "back_iv": back_iv,
        "term_slope": term_slope,
        "volume": volume,
        "rv": rv,
        "iv_rv_ratio": iv_rv_ratio,
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
        "front_iv": front_iv,
        "back_iv": back_iv,
        "term_slope": term_slope,
        "volume": volume,
        "rv": rv,
        "iv_rv_ratio": iv_rv_ratio,
    }
    append_to_history(row, ticker, data_dir)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Daily earnings vol snapshot collector for IV crush strategy"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", type=str, help="Single ticker symbol")
    group.add_argument("--tickers", type=str,
                       help="Comma-separated tickers, 'all_liquid', or path to .txt file")
    parser.add_argument("--data-dir", type=str,
                        default="pricing/earnings_vol/data",
                        help="Data directory (default: pricing/earnings_vol/data)")
    parser.add_argument("--entry-window", type=int, default=18,
                        help="Days before earnings to start collecting (default: 18)")

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Parse ticker list
    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.tickers == "all_liquid":
        liquid_file = Path(__file__).resolve().parents[4] / "pricing" / "liquidity" / "data" / "liquid_options.txt"
        if not liquid_file.exists():
            print(f"Error: {liquid_file} not found. Run filter_liquid_options.py first.", file=sys.stderr)
            return 1
        tickers = [t.strip() for t in liquid_file.read_text().splitlines() if t.strip()]
    elif args.tickers.endswith(".txt"):
        ticker_file = Path(args.tickers)
        if not ticker_file.exists():
            print(f"Error: {ticker_file} not found", file=sys.stderr)
            return 1
        tickers = [t.strip() for t in ticker_file.read_text().splitlines() if t.strip()]
    else:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]

    print(f"Earnings Vol Collection: {len(tickers)} tickers")
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

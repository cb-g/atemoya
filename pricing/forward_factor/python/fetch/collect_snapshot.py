#!/usr/bin/env python3
"""
Daily forward factor snapshot collector.

Fetches ATM IV for multiple expirations and computes forward volatility
for DTE pairs (30-60, 30-90, 60-90). Designed for daily cron after market close.

Each run:
- Fetches option chains, finds ATM IV for 3 target DTEs
- Computes forward vol and forward factor for each DTE pair
- Archives full snapshot to data/snapshots/{TICKER}/{YYYY-MM-DD}.json
- Appends rows to data/{TICKER}_ff_history_yfinance.csv (one row per DTE pair)

Idempotent: skips tickers already collected today.

The forward factor formula:
  V_fwd = (sigma2^2 * T2 - sigma1^2 * T1) / (T2 - T1)
  sigma_fwd = sqrt(V_fwd)
  FF = (sigma_front - sigma_fwd) / sigma_fwd
"""

import json
import math
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

# CSV header for forward factor history
HISTORY_COLUMNS = [
    "date", "ticker", "dte_pair", "front_dte", "back_dte",
    "front_iv", "back_iv", "forward_vol", "forward_factor",
]

# DTE pairs to scan
DTE_PAIRS = [(30, 60), (30, 90), (60, 90)]

# Tolerance for matching expirations to target DTEs
DTE_TOLERANCE = 10
DTE_MIN = 15
DTE_MAX = 130


def already_collected_today(ticker: str, data_dir: Path) -> bool:
    """Check if today's snapshot already exists."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_file = data_dir / "snapshots" / ticker / f"{today}.json"
    return snapshot_file.exists()


def find_atm_iv(provider, ticker: str, spot: float, expiry: str) -> float:
    """Fetch ATM IV for a specific expiration date."""
    chain = provider.fetch_option_chain(ticker, expiry=expiry)
    if chain is None:
        return 0.0

    calls = [c for c in chain.calls if c.expiry == expiry]
    puts = [p for p in chain.puts if p.expiry == expiry]

    if not calls or not puts:
        return 0.0

    all_strikes = sorted(set(c.strike for c in calls))
    if not all_strikes:
        return 0.0

    arr = np.array(all_strikes)
    atm_strike = arr[np.argmin(np.abs(arr - spot))]

    atm_calls = [c for c in calls if c.strike == atm_strike]
    atm_puts = [p for p in puts if p.strike == atm_strike]

    if not atm_calls or not atm_puts:
        return 0.0

    call_iv = atm_calls[0].implied_volatility
    put_iv = atm_puts[0].implied_volatility
    if call_iv > 0 and put_iv > 0:
        return (call_iv + put_iv) / 2
    return call_iv if call_iv > 0 else put_iv


def calculate_forward_factor(front_iv: float, back_iv: float,
                             front_dte: int, back_dte: int) -> tuple[float, float]:
    """
    Compute forward vol and forward factor.

    Returns (forward_vol, forward_factor).
    Matches OCaml forward_vol.ml logic exactly.
    """
    t1 = front_dte / 365.0
    t2 = back_dte / 365.0

    if t2 <= t1:
        return 0.0, 0.0

    v1 = front_iv ** 2
    v2 = back_iv ** 2

    forward_variance = (v2 * t2 - v1 * t1) / (t2 - t1)
    forward_variance = max(0.0, forward_variance)
    forward_volatility = math.sqrt(forward_variance)

    if forward_volatility > 0:
        ff = (front_iv - forward_volatility) / forward_volatility
    else:
        ff = 0.0

    return forward_volatility, ff


def find_best_expiry(expiries: list[str], target_dte: int) -> tuple[str, int] | None:
    """Find expiration closest to target DTE within tolerance."""
    today = datetime.now().date()
    best = None
    best_diff = float('inf')

    for exp_str in expiries:
        exp_date = pd.to_datetime(exp_str).date()
        dte = (exp_date - today).days

        if dte < DTE_MIN or dte > DTE_MAX:
            continue

        diff = abs(dte - target_dte)
        if diff <= DTE_TOLERANCE and diff < best_diff:
            best = (exp_str, dte)
            best_diff = diff

    return best


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


def append_to_history(rows: list[dict], ticker: str, data_dir: Path) -> None:
    """Append rows to {TICKER}_ff_history_yfinance.csv, skipping if date+dte_pair already exists."""
    history_file = data_dir / f"{ticker}_ff_history_yfinance.csv"
    today = rows[0]["date"] if rows else ""

    new_df = pd.DataFrame(rows, columns=HISTORY_COLUMNS)

    if history_file.exists():
        existing = pd.read_csv(history_file, usecols=["date", "dte_pair"], dtype=str)
        existing_keys = set(zip(existing["date"], existing["dte_pair"]))
        new_df = new_df[~new_df.apply(
            lambda r: (str(r["date"]), str(r["dte_pair"])) in existing_keys, axis=1
        )]
        if new_df.empty:
            print(f"  Skipped {ticker}: {today} already in history")
            return
        new_df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        new_df.to_csv(history_file, index=False)

    print(f"  Appended {len(new_df)} rows to history: {history_file}")


def collect_one_ticker(ticker: str, data_dir: Path) -> bool:
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

    # Get provider and spot price
    provider = get_provider()

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
        expiries = chain.expiries
    except Exception as e:
        print(f"  ERROR fetching chain for {ticker}: {e}")
        return False

    # Find expirations matching our target DTEs
    target_dtes = sorted(set(d for pair in DTE_PAIRS for d in pair))
    matched = {}
    for target in target_dtes:
        result = find_best_expiry(expiries, target)
        if result:
            matched[target] = result

    if len(matched) < 2:
        print(f"  Not enough expirations matched (need >=2, got {len(matched)}), skipping")
        return False

    # Fetch ATM IV for each matched expiration
    iv_data = {}
    for target, (exp_str, actual_dte) in matched.items():
        try:
            iv = retry_with_backoff(lambda e=exp_str: find_atm_iv(provider, ticker, spot, e))
            if iv > 0:
                iv_data[target] = {"expiry": exp_str, "dte": actual_dte, "iv": iv}
                print(f"  {exp_str} ({actual_dte}d, target {target}d): IV={iv*100:.1f}%")
            else:
                print(f"  {exp_str} ({actual_dte}d): IV=0, skipping")
        except Exception as e:
            print(f"  ERROR fetching IV for {exp_str}: {e}")

    # Compute forward factors for each DTE pair
    today = datetime.now().strftime("%Y-%m-%d")
    history_rows = []
    pair_results = []

    for front_target, back_target in DTE_PAIRS:
        if front_target not in iv_data or back_target not in iv_data:
            continue

        front = iv_data[front_target]
        back = iv_data[back_target]

        fwd_vol, ff = calculate_forward_factor(
            front["iv"], back["iv"], front["dte"], back["dte"]
        )

        dte_pair = f"{front_target}-{back_target}"
        print(f"  {dte_pair}: FF={ff:+.4f} (fwd_vol={fwd_vol*100:.1f}%)")

        pair_results.append({
            "dte_pair": dte_pair,
            "front_expiry": front["expiry"],
            "back_expiry": back["expiry"],
            "front_dte": front["dte"],
            "back_dte": back["dte"],
            "front_iv": front["iv"],
            "back_iv": back["iv"],
            "forward_vol": fwd_vol,
            "forward_factor": ff,
        })

        history_rows.append({
            "date": today,
            "ticker": ticker,
            "dte_pair": dte_pair,
            "front_dte": front["dte"],
            "back_dte": back["dte"],
            "front_iv": front["iv"],
            "back_iv": back["iv"],
            "forward_vol": fwd_vol,
            "forward_factor": ff,
        })

    if not history_rows:
        print(f"  No valid DTE pairs for {ticker}")
        return False

    # Archive full snapshot
    snapshot_data = {
        "date": today,
        "ticker": ticker,
        "spot": spot,
        "provider": provider.name,
        "pairs": pair_results,
    }
    archive_snapshot(snapshot_data, ticker, data_dir)

    # Append to history
    append_to_history(history_rows, ticker, data_dir)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Daily forward factor snapshot collector"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", type=str, help="Single ticker symbol")
    group.add_argument("--tickers", type=str,
                       help="Comma-separated tickers, 'all_liquid', or path to .txt file")
    parser.add_argument("--data-dir", type=str,
                        default="pricing/forward_factor/data",
                        help="Data directory (default: pricing/forward_factor/data)")

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

    print(f"Forward Factor Collection: {len(tickers)} tickers")
    print(f"Data dir: {data_dir}")
    print(f"DTE pairs: {', '.join(f'{a}-{b}' for a, b in DTE_PAIRS)}")

    successes = 0
    for ticker in tickers:
        if collect_one_ticker(ticker, data_dir):
            successes += 1

    print(f"\nCollection complete: {successes}/{len(tickers)} tickers collected")
    return 0 if successes > 0 or all(
        already_collected_today(t, data_dir) for t in tickers
    ) else 1


if __name__ == "__main__":
    exit(main())

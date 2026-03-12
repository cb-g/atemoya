#!/usr/bin/env python3
"""
Daily vol surface snapshot collector for variance swaps.

Fetches current option chains, calibrates SVI surfaces, extracts ATM IV
for implied variance, and archives results. Designed for daily cron
execution after market close.

Each run:
- Archives full SVI snapshot to data/snapshots/{TICKER}/{YYYY-MM-DD}.json
- Appends one row to data/{TICKER}_iv_history.csv

Idempotent: skips tickers already collected today.

The history CSV provides time-varying implied variance for backtesting,
replacing the constant ATM IV = 20% assumption.
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
sys.path.insert(0, str(Path(__file__).parents[3]))

from lib.python.retry import retry_with_backoff

from pricing.variance_swaps.python.fetch_data import (
    fetch_options_chain,
    fetch_underlying_data,
    calibrate_svi_surface,
)

# CSV header for implied variance history
HISTORY_COLUMNS = [
    "date", "ticker", "spot_price", "atm_iv", "implied_var",
    "num_expiries", "near_expiry_days",
]


def svi_atm_iv(svi_params: list[dict]) -> tuple[float, int, float]:
    """
    Extract ATM implied volatility from SVI surface.

    Uses the nearest expiry slice. ATM = log-moneyness k=0.
    Returns (atm_iv, num_expiries, near_expiry_years).
    """
    if not svi_params:
        return 0.20, 0, 0.0

    # Pick nearest expiry (most liquid, most relevant for 30-day horizon)
    nearest = min(svi_params, key=lambda p: p["expiry"])
    expiry = nearest["expiry"]

    # SVI at ATM (k = 0): w(0) = a + b*(rho*(0-m) + sqrt((0-m)^2 + sigma^2))
    a = nearest["a"]
    b = nearest["b"]
    rho = nearest["rho"]
    m = nearest["m"]
    sigma = nearest["sigma"]

    delta_k = 0.0 - m
    sqrt_term = math.sqrt(delta_k ** 2 + sigma ** 2)
    total_var = a + b * (rho * delta_k + sqrt_term)

    # IV = sqrt(total_var / T)
    atm_iv = math.sqrt(max(0.0001, total_var / expiry))

    return atm_iv, len(svi_params), expiry


def already_collected_today(ticker: str, data_dir: Path) -> bool:
    """Check if today's snapshot already exists."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_file = data_dir / "snapshots" / ticker / f"{today}.json"
    return snapshot_file.exists()


def archive_snapshot(svi_surface: dict, ticker: str, spot: float,
                     atm_iv: float, data_dir: Path) -> Path:
    """Save full SVI snapshot to data/snapshots/{TICKER}/{YYYY-MM-DD}.json."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_dir = data_dir / "snapshots" / ticker
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    snapshot_file = snapshot_dir / f"{today}.json"
    snapshot_data = {
        "date": today,
        "ticker": ticker,
        "spot": spot,
        "atm_iv": atm_iv,
        "implied_var": atm_iv ** 2,
        "model": svi_surface.get("model", "SVI"),
        "params": svi_surface.get("params", []),
    }

    with open(snapshot_file, "w") as f:
        json.dump(snapshot_data, f, indent=2)

    print(f"  Archived snapshot: {snapshot_file}")
    return snapshot_file


def append_to_history(row: dict, ticker: str, data_dir: Path) -> None:
    """Append one row to {TICKER}_iv_history.csv."""
    history_file = data_dir / f"{ticker}_iv_history.csv"

    df = pd.DataFrame([row], columns=HISTORY_COLUMNS)

    if history_file.exists():
        df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        df.to_csv(history_file, index=False)

    print(f"  Appended to history: {history_file}")


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

    # Fetch underlying data (spot, dividend yield)
    try:
        underlying = retry_with_backoff(lambda: fetch_underlying_data(ticker))
        spot = underlying["spot_price"]
    except Exception as e:
        print(f"  ERROR fetching underlying for {ticker}: {e}")
        return False

    # Fetch option chain and calibrate SVI
    try:
        options_df = retry_with_backoff(lambda: fetch_options_chain(ticker))
        svi_surface = calibrate_svi_surface(options_df, spot)
    except Exception as e:
        print(f"  ERROR calibrating vol surface for {ticker}: {e}")
        return False

    svi_params = svi_surface.get("params", [])
    if not svi_params:
        print(f"  ERROR: No SVI params for {ticker}")
        return False

    # Extract ATM IV
    atm_iv, num_expiries, near_expiry = svi_atm_iv(svi_params)
    implied_var = atm_iv ** 2

    print(f"  Spot:         ${spot:.2f}")
    print(f"  ATM IV:       {atm_iv*100:.2f}%")
    print(f"  Implied Var:  {implied_var:.6f}")
    print(f"  Expiries:     {num_expiries}")
    print(f"  Near Expiry:  {near_expiry*365:.0f} days")

    # Archive full snapshot
    archive_snapshot(svi_surface, ticker, spot, atm_iv, data_dir)

    # Build row and append to history
    today = datetime.now().strftime("%Y-%m-%d")
    row = {
        "date": today,
        "ticker": ticker,
        "spot_price": spot,
        "atm_iv": atm_iv,
        "implied_var": implied_var,
        "num_expiries": num_expiries,
        "near_expiry_days": int(near_expiry * 365),
    }
    append_to_history(row, ticker, data_dir)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Daily vol surface snapshot collector for variance swaps"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", type=str, help="Single ticker symbol")
    group.add_argument("--tickers", type=str,
                       help="Comma-separated tickers, 'all_liquid', or path to .txt file")
    parser.add_argument("--data-dir", type=str,
                        default="pricing/variance_swaps/data",
                        help="Data directory (default: pricing/variance_swaps/data)")

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Parse ticker list
    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.tickers == "all_liquid":
        liquid_file = Path(__file__).resolve().parents[3] / "pricing" / "liquidity" / "data" / "liquid_options.txt"
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

    print(f"Daily IV Collection: {len(tickers)} tickers")
    print(f"Data dir: {data_dir}")

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

#!/usr/bin/env python3
"""Replay ThetaData raw EOD chains into variance swaps history CSVs.

Reads raw option chain archives from pricing/thetadata/data/{TICKER}.csv,
computes SVI surface and ATM IV for each trading day, and appends rows to
the module's existing data/{TICKER}_iv_history.csv files.

Idempotent: skips dates already present in history.

Usage:
    uv run pricing/variance_swaps/python/replay_backfill.py --tickers SPY,AAPL
    uv run pricing/variance_swaps/python/replay_backfill.py --all
"""

import argparse
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[3]))

from pricing.variance_swaps.python.fetch_data import calibrate_svi_surface
from pricing.variance_swaps.python.collect_snapshot import (
    HISTORY_COLUMNS,
    svi_atm_iv,
)
from lib.python.iv import implied_vol_newton_raphson

THETADATA_DIR = Path(__file__).parents[3] / "pricing" / "thetadata" / "data"
MODULE_DATA_DIR = Path(__file__).parents[1] / "data"


def append_to_history_thetadata(row: dict, ticker: str, data_dir: Path) -> None:
    """Append one row to {TICKER}_iv_history_thetadata.csv."""
    history_file = data_dir / f"{ticker}_iv_history_thetadata.csv"
    df = pd.DataFrame([row], columns=HISTORY_COLUMNS)
    if history_file.exists():
        existing = pd.read_csv(history_file, usecols=["date"], dtype=str)
        if row["date"] in existing["date"].values:
            return
        df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        df.to_csv(history_file, index=False)


def parse_thetadata_csv(raw_df: pd.DataFrame, date_str: str, spot: float) -> pd.DataFrame:
    """Convert one day of ThetaData EOD rows into the DataFrame format
    that calibrate_svi_surface expects.

    Expected input columns: strike, right, expiration, bid, ask, volume, created
    Expected output columns: strike, impliedVolatility, bid, ask, volume, option_type, expiry
    """
    # Filter to this date
    df = raw_df[raw_df["_date"] == date_str].copy()
    if df.empty:
        return pd.DataFrame()

    # Parse fields
    df["strike"] = df["strike"].astype(float)
    df["bid"] = df["bid"].astype(float)
    df["ask"] = df["ask"].astype(float)
    df["volume"] = df["volume"].astype(int)
    df["option_type"] = df["right"].str.strip('"').str.lower()

    # Compute expiry in years
    df["expiration_clean"] = df["expiration"].str.strip('"')
    df["expiry_dt"] = pd.to_datetime(df["expiration_clean"])
    ref_date = pd.Timestamp(date_str)
    df["days_to_expiry"] = (df["expiry_dt"] - ref_date).dt.days
    df["expiry"] = df["days_to_expiry"] / 365.0

    # Compute mid price first (needed for quality filters)
    df["mid"] = (df["bid"] + df["ask"]) / 2

    # Quality filters for robust IV computation
    df = df[
        (df["bid"] > 0)
        & (df["ask"] > df["bid"])
        & (df["mid"] > 0.05)                          # no penny options
        & ((df["ask"] - df["bid"]) / df["mid"] < 1.0) # no wide spreads
        & (df["days_to_expiry"] >= 14)                 # near-expiry vega ≈ 0
        & (df["days_to_expiry"] <= 365)
    ]

    # OTM only: puts below spot, calls above spot
    df = df[
        ((df["option_type"] == "put") & (df["strike"] < spot))
        | ((df["option_type"] == "call") & (df["strike"] >= spot))
    ]

    if df.empty:
        return pd.DataFrame()

    df["impliedVolatility"] = implied_vol_newton_raphson(
        prices=df["mid"].values,
        spots=np.full(len(df), spot),
        strikes=df["strike"].values,
        expiries=df["expiry"].values,
        rates=np.full(len(df), 0.05),
        option_types=df["option_type"].values,
    )
    # Drop rows where IV computation failed
    df = df[df["impliedVolatility"] > 0]

    return df[["strike", "impliedVolatility", "bid", "ask", "volume", "option_type", "expiry"]]


def get_spot_for_date(ticker: str, date_str: str) -> float:
    """Get underlying closing price for a date from ThetaData stock EOD."""
    from lib.python.data_fetcher.thetadata_provider import ThetaDataProvider
    provider = ThetaDataProvider()
    if not provider.is_available():
        return 0.0
    price = provider._fetch_underlying_price(ticker, date_str.replace("-", ""))
    return price


def replay_ticker(ticker: str, thetadata_dir: Path, module_data_dir: Path, quiet: bool = False) -> int:
    """Replay all dates for one ticker. Returns number of new rows added."""
    raw_file = thetadata_dir / f"{ticker}.csv"
    if not raw_file.exists():
        if not quiet:
            print(f"  {ticker}: no ThetaData archive found")
        return 0

    # Load raw data and extract dates
    raw_df = pd.read_csv(raw_file, dtype=str)
    if raw_df.empty:
        return 0

    # Extract date from 'created' column (format: "2026-03-27T17:24:30.205")
    raw_df["_date"] = raw_df["created"].str.strip('"').str.split("T").str[0]
    dates = sorted(raw_df["_date"].unique())

    # Load existing history dates for idempotency
    history_file = module_data_dir / f"{ticker}_iv_history_thetadata.csv"
    existing_dates = set()
    if history_file.exists():
        try:
            existing = pd.read_csv(history_file, usecols=["date"], dtype=str)
            existing_dates = set(existing["date"].values)
        except Exception:
            pass

    new_dates = [d for d in dates if d not in existing_dates]
    if not new_dates:
        if not quiet:
            print(f"  {ticker}: all {len(dates)} dates already in history")
        return 0

    added = 0
    for date_str in new_dates:
        # Get spot price for this date
        spot = get_spot_for_date(ticker, date_str)
        if spot == 0.0:
            continue

        # Parse raw chain for this date
        options_df = parse_thetadata_csv(raw_df, date_str, spot)
        if options_df.empty:
            continue

        # Calibrate SVI and extract ATM IV
        svi_surface = calibrate_svi_surface(options_df, spot)
        svi_params = svi_surface.get("params", [])
        if not svi_params:
            continue

        atm_iv, num_expiries, near_expiry = svi_atm_iv(svi_params)

        # Zero fake data policy: skip if calibration fell back to default
        if atm_iv == 0.20 and num_expiries <= 3:
            continue

        implied_var = atm_iv ** 2

        row = {
            "date": date_str,
            "ticker": ticker,
            "spot_price": spot,
            "atm_iv": atm_iv,
            "implied_var": implied_var,
            "num_expiries": num_expiries,
            "near_expiry_days": int(near_expiry * 365),
        }
        append_to_history_thetadata(row, ticker, module_data_dir)
        added += 1

    if not quiet:
        print(f"  {ticker}: added {added}/{len(new_dates)} new dates ({len(existing_dates)} existing)")
    return added


def main():
    parser = argparse.ArgumentParser(description="Replay ThetaData into variance swaps history")
    parser.add_argument("--tickers", type=str, help="Comma-separated ticker list")
    parser.add_argument("--all", action="store_true", help="Replay all tickers with ThetaData archives")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-date output")
    args = parser.parse_args()

    thetadata_dir = THETADATA_DIR
    module_data_dir = MODULE_DATA_DIR
    module_data_dir.mkdir(parents=True, exist_ok=True)

    if args.all:
        tickers = sorted(f.stem for f in thetadata_dir.glob("*.csv"))
    elif args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
    else:
        print("Error: specify --tickers or --all", file=sys.stderr)
        sys.exit(1)

    print(f"Replay: {len(tickers)} tickers → variance_swaps history")
    print(f"Source: {thetadata_dir}")
    print(f"Target: {module_data_dir}")
    print()

    total_added = 0
    for i, ticker in enumerate(tickers, 1):
        added = replay_ticker(ticker, thetadata_dir, module_data_dir, quiet=args.quiet)
        total_added += added

    print(f"\nDone: {total_added} new history rows added across {len(tickers)} tickers")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Replay ThetaData raw EOD chains into skew trading history CSVs.

Reads raw option chain archives from pricing/thetadata/data/{TICKER}.csv,
computes IVs, calibrates SVI surfaces, extracts skew metrics (RR25, BF25,
skew slope), and appends rows to data/{TICKER}_skew_history.csv.

Idempotent: skips dates already present in history.
Zero fake data: skips dates where calibration fails.

Usage:
    uv run pricing/skew_trading/python/fetch/replay_backfill.py --tickers SPY,AAPL
    uv run pricing/skew_trading/python/fetch/replay_backfill.py --all
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.iv import implied_vol_newton_raphson
from pricing.skew_trading.python.fetch.fetch_options import (
    calibrate_svi_surface,
)
from pricing.skew_trading.python.fetch.collect_snapshot import (
    HISTORY_COLUMNS,
    select_target_expiry,
    compute_skew_metrics,
    load_config,
)

CONFIG = load_config()
THETADATA_DIR = Path(__file__).parents[4] / "pricing" / "thetadata" / "data"
MODULE_DATA_DIR = Path(__file__).parents[2] / "data"


def append_to_history_thetadata(row: dict, ticker: str, data_dir: Path) -> None:
    """Append one row to {TICKER}_skew_history_thetadata.csv."""
    history_file = data_dir / f"{ticker}_skew_history_thetadata.csv"
    df = pd.DataFrame([row], columns=HISTORY_COLUMNS)
    if history_file.exists():
        existing = pd.read_csv(history_file, usecols=["timestamp"], dtype=str)
        if str(row["timestamp"]) in existing["timestamp"].values:
            return
        df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        df.to_csv(history_file, index=False)


def parse_thetadata_for_skew(raw_df: pd.DataFrame, date_str: str, spot: float) -> pd.DataFrame:
    """Convert one day of ThetaData EOD rows into the DataFrame format
    that skew_trading's calibrate_svi_surface expects.

    Output columns: strike, expiry_years, bid, ask, mid, volume, option_type, implied_vol
    """
    df = raw_df[raw_df["_date"] == date_str].copy()
    if df.empty:
        return pd.DataFrame()

    df["strike"] = df["strike"].astype(float)
    df["bid"] = df["bid"].astype(float)
    df["ask"] = df["ask"].astype(float)
    df["volume"] = df["volume"].astype(int)
    df["option_type"] = df["right"].str.strip('"').str.lower()

    df["expiration_clean"] = df["expiration"].str.strip('"')
    df["expiry_dt"] = pd.to_datetime(df["expiration_clean"])
    ref_date = pd.Timestamp(date_str)
    df["days_to_expiry"] = (df["expiry_dt"] - ref_date).dt.days
    df["expiry_years"] = df["days_to_expiry"] / 365.0

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

    if df.empty:
        return pd.DataFrame()

    # Compute IV via Newton-Raphson
    df["implied_vol"] = implied_vol_newton_raphson(
        prices=df["mid"].values,
        spots=np.full(len(df), spot),
        strikes=df["strike"].values,
        expiries=df["expiry_years"].values,
        rates=np.full(len(df), CONFIG.get("options", {}).get("risk_free_rate", 0.05)),
        option_types=df["option_type"].values,
    )
    df = df[df["implied_vol"] > 0]

    return df[["strike", "expiry_years", "bid", "ask", "mid", "volume", "option_type", "implied_vol"]]


def get_spot_for_date(ticker: str, date_str: str) -> float:
    from lib.python.data_fetcher.thetadata_provider import ThetaDataProvider
    provider = ThetaDataProvider()
    if not provider.is_available():
        return 0.0
    return provider._fetch_underlying_price(ticker, date_str.replace("-", ""))


def replay_ticker(ticker: str, thetadata_dir: Path, module_data_dir: Path, quiet: bool = False) -> int:
    raw_file = thetadata_dir / f"{ticker}.csv"
    if not raw_file.exists():
        if not quiet:
            print(f"  {ticker}: no ThetaData archive found")
        return 0

    raw_df = pd.read_csv(raw_file, dtype=str)
    if raw_df.empty:
        return 0

    raw_df["_date"] = raw_df["created"].str.strip('"').str.split("T").str[0]
    dates = sorted(raw_df["_date"].unique())

    # Idempotency: check existing history
    history_file = module_data_dir / f"{ticker}_skew_history_thetadata.csv"
    existing_dates = set()
    if history_file.exists():
        try:
            existing = pd.read_csv(history_file, usecols=["timestamp"], dtype=str)
            existing_dates = set(existing["timestamp"].values)
        except Exception:
            pass

    # Skew trading uses Unix timestamps in history, but we compare date strings
    # Convert existing timestamps to date strings for comparison
    existing_date_strs = set()
    for ts in existing_dates:
        try:
            existing_date_strs.add(datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d"))
        except (ValueError, OSError):
            existing_date_strs.add(ts)

    new_dates = [d for d in dates if d not in existing_date_strs]
    if not new_dates:
        if not quiet:
            print(f"  {ticker}: all {len(dates)} dates already in history")
        return 0

    target_days = CONFIG.get("options", {}).get("target_expiry_days", 30)
    rate = CONFIG.get("options", {}).get("risk_free_rate", 0.05)
    dividend = 0.0

    added = 0
    for date_str in new_dates:
        spot = get_spot_for_date(ticker, date_str)
        if spot == 0.0:
            continue

        chain_df = parse_thetadata_for_skew(raw_df, date_str, spot)
        if chain_df.empty or len(chain_df) < 10:
            continue

        # Calibrate SVI surface
        svi_params = calibrate_svi_surface(chain_df, spot)
        if not svi_params or len(svi_params) < 1:
            continue

        # Select target expiry and compute skew metrics
        target = select_target_expiry(svi_params, target_days)
        if target is None:
            continue

        metrics = compute_skew_metrics(target, spot, rate, dividend)

        # Zero fake data: skip if ATM vol is unreasonable
        if metrics["atm_vol"] <= 0.01 or metrics["atm_vol"] >= 5.0:
            continue

        # Build timestamp (Unix timestamp at midnight of this date)
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        timestamp = dt.timestamp()

        row = {
            "timestamp": timestamp,
            "ticker": ticker,
            "expiry": metrics["expiry"],
            "rr25": metrics["rr25"],
            "bf25": metrics["bf25"],
            "skew_slope": metrics["skew_slope"],
            "atm_vol": metrics["atm_vol"],
            "put_25d_vol": metrics["put_25d_vol"],
            "call_25d_vol": metrics["call_25d_vol"],
            "put_25d_strike": metrics["put_25d_strike"],
            "call_25d_strike": metrics["call_25d_strike"],
        }
        append_to_history_thetadata(row, ticker, module_data_dir)
        added += 1

    if not quiet:
        print(f"  {ticker}: added {added}/{len(new_dates)} new dates ({len(existing_date_strs)} existing)")
    return added


def main():
    parser = argparse.ArgumentParser(description="Replay ThetaData into skew trading history")
    parser.add_argument("--tickers", type=str, help="Comma-separated ticker list")
    parser.add_argument("--all", action="store_true", help="Replay all tickers with ThetaData archives")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-date output")
    args = parser.parse_args()

    module_data_dir = MODULE_DATA_DIR
    module_data_dir.mkdir(parents=True, exist_ok=True)

    if args.all:
        tickers = sorted(f.stem for f in THETADATA_DIR.glob("*.csv"))
    elif args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
    else:
        print("Error: specify --tickers or --all", file=sys.stderr)
        sys.exit(1)

    print(f"Replay: {len(tickers)} tickers → skew_trading history")
    print()

    total_added = 0
    for ticker in tickers:
        added = replay_ticker(ticker, THETADATA_DIR, module_data_dir, quiet=args.quiet)
        total_added += added

    print(f"\nDone: {total_added} new history rows added across {len(tickers)} tickers")


if __name__ == "__main__":
    main()

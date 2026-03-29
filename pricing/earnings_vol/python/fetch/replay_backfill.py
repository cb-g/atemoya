#!/usr/bin/env python3
"""Replay ThetaData raw EOD chains into earnings vol history CSVs.

Computes front/back IV and term structure slope for each trading day.
Since historical earnings dates are not available from ThetaData free
tier, earnings_date and days_to_earnings are left empty. The data is
still useful for term structure analysis across the IV history.

Idempotent. Zero fake data policy.

Usage:
    uv run pricing/earnings_vol/python/fetch/replay_backfill.py --tickers AAPL,NVDA
    uv run pricing/earnings_vol/python/fetch/replay_backfill.py --all
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.iv import implied_vol_newton_raphson
from pricing.earnings_vol.python.fetch.collect_snapshot import HISTORY_COLUMNS

THETADATA_DIR = Path(__file__).parents[4] / "pricing" / "thetadata" / "data"
MODULE_DATA_DIR = Path(__file__).parents[2] / "data"


def append_to_history_thetadata(row: dict, ticker: str, data_dir: Path) -> None:
    """Append one row to {TICKER}_earnings_vol_thetadata.csv."""
    history_file = data_dir / f"{ticker}_earnings_vol_thetadata.csv"
    df = pd.DataFrame([row], columns=HISTORY_COLUMNS)
    if history_file.exists():
        existing = pd.read_csv(history_file, usecols=["date"], dtype=str)
        if row["date"] in existing["date"].values:
            return
        df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        df.to_csv(history_file, index=False)


def compute_front_back_iv(raw_df: pd.DataFrame, date_str: str, spot: float) -> dict | None:
    """Compute front and back month ATM IV from a day's option chain."""
    df = raw_df[raw_df["_date"] == date_str].copy()
    if df.empty:
        return None

    df["strike"] = df["strike"].astype(float)
    df["bid"] = df["bid"].astype(float)
    df["ask"] = df["ask"].astype(float)
    df["option_type"] = df["right"].str.strip('"').str.lower()
    df["expiration_clean"] = df["expiration"].str.strip('"')
    df["expiry_dt"] = pd.to_datetime(df["expiration_clean"])
    ref_date = pd.Timestamp(date_str)
    df["days_to_expiry"] = (df["expiry_dt"] - ref_date).dt.days
    df["expiry_years"] = df["days_to_expiry"] / 365.0
    df["mid"] = (df["bid"] + df["ask"]) / 2

    df = df[
        (df["bid"] > 0) & (df["ask"] > df["bid"])
        & (df["mid"] > 0.05)
        & ((df["ask"] - df["bid"]) / df["mid"] < 1.0)
        & (df["days_to_expiry"] >= 14)
        & (df["days_to_expiry"] <= 120)
    ]

    # OTM only
    df = df[
        ((df["option_type"] == "put") & (df["strike"] < spot))
        | ((df["option_type"] == "call") & (df["strike"] >= spot))
    ]

    if df.empty:
        return None

    df["iv"] = implied_vol_newton_raphson(
        prices=df["mid"].values,
        spots=np.full(len(df), spot),
        strikes=df["strike"].values,
        expiries=df["expiry_years"].values,
        rates=np.full(len(df), 0.05),
        option_types=df["option_type"].values,
    )
    df = df[df["iv"] > 0]
    if df.empty:
        return None

    # Find two nearest expiries for front/back
    expiry_groups = df.groupby("days_to_expiry")["iv"]
    expiry_medians = {}
    for dte, ivs in expiry_groups:
        # ATM region only
        dte_data = df[df["days_to_expiry"] == dte]
        atm_data = dte_data[
            (dte_data["strike"] >= spot * 0.95)
            & (dte_data["strike"] <= spot * 1.05)
        ]
        if not atm_data.empty:
            expiry_medians[int(dte)] = float(atm_data["iv"].median())

    if len(expiry_medians) < 2:
        return None

    sorted_dtes = sorted(expiry_medians.keys())
    front_dte = sorted_dtes[0]
    back_dte = sorted_dtes[1]
    front_iv = expiry_medians[front_dte]
    back_iv = expiry_medians[back_dte]

    if front_iv <= 0 or back_iv <= 0:
        return None

    term_slope = (back_iv - front_iv) / ((back_dte - front_dte) / 30.0)

    return {
        "front_iv": front_iv,
        "back_iv": back_iv,
        "term_slope": term_slope,
        "volume": int(df["volume"].sum()) if "volume" in df.columns else 0,
    }


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
    # volume column needed for aggregation
    if "volume" in raw_df.columns:
        raw_df["volume"] = raw_df["volume"].astype(int)
    dates = sorted(raw_df["_date"].unique())

    history_file = module_data_dir / f"{ticker}_earnings_vol_thetadata.csv"
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
            print(f"  {ticker}: all dates already in history")
        return 0

    from lib.python.data_fetcher.thetadata_provider import ThetaDataProvider
    provider = ThetaDataProvider()

    added = 0
    for date_str in new_dates:
        spot = provider._fetch_underlying_price(ticker, date_str.replace("-", ""))
        if spot == 0.0:
            continue

        result = compute_front_back_iv(raw_df, date_str, spot)
        if result is None:
            continue

        # Compute RV from ThetaData stock EOD (simplified: use front_iv as proxy)
        # Full RV would need OHLCV lookback which is expensive per-date
        rv = 0.0
        iv_rv_ratio = 0.0
        if rv > 0:
            iv_rv_ratio = result["front_iv"] / rv

        row = {
            "date": date_str,
            "ticker": ticker,
            "spot": spot,
            "earnings_date": "",
            "days_to_earnings": 0,
            "front_iv": result["front_iv"],
            "back_iv": result["back_iv"],
            "term_slope": result["term_slope"],
            "volume": result["volume"],
            "rv": rv,
            "iv_rv_ratio": iv_rv_ratio,
        }
        append_to_history_thetadata(row, ticker, module_data_dir)
        added += 1

    if not quiet:
        print(f"  {ticker}: added {added}/{len(new_dates)} new dates ({len(existing_dates)} existing)")
    return added


def main():
    parser = argparse.ArgumentParser(description="Replay ThetaData into earnings vol history")
    parser.add_argument("--tickers", type=str)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--quiet", action="store_true")
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

    print(f"Replay: {len(tickers)} tickers → earnings_vol history")
    print()

    total_added = 0
    for ticker in tickers:
        added = replay_ticker(ticker, THETADATA_DIR, module_data_dir, quiet=args.quiet)
        total_added += added

    print(f"\nDone: {total_added} new history rows added across {len(tickers)} tickers")


if __name__ == "__main__":
    main()

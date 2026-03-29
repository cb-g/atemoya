#!/usr/bin/env python3
"""Replay ThetaData raw EOD chains into pre-earnings straddle history CSVs.

Computes ATM straddle cost, avg IV, and implied move for each trading day.
Historical earnings dates are not available from ThetaData free tier, so
earnings_date and days_to_earnings are left empty. These can be enriched
later from a historical earnings calendar.

Idempotent. Zero fake data policy.

Usage:
    uv run pricing/pre_earnings_straddle/python/fetch/replay_backfill.py --tickers AAPL,NVDA
    uv run pricing/pre_earnings_straddle/python/fetch/replay_backfill.py --all
"""

import argparse
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.iv import implied_vol_newton_raphson
from pricing.pre_earnings_straddle.python.fetch.collect_earnings_iv import HISTORY_COLUMNS

THETADATA_DIR = Path(__file__).parents[4] / "pricing" / "thetadata" / "data"
MODULE_DATA_DIR = Path(__file__).parents[2] / "data"


def append_to_history_thetadata(row: dict, ticker: str, data_dir: Path) -> None:
    """Append one row to {TICKER}_iv_snapshots_thetadata.csv."""
    history_file = data_dir / f"{ticker}_iv_snapshots_thetadata.csv"
    df = pd.DataFrame([row], columns=HISTORY_COLUMNS)
    if history_file.exists():
        existing = pd.read_csv(history_file, usecols=["date"], dtype=str)
        if row["date"] in existing["date"].values:
            return
        df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        df.to_csv(history_file, index=False)


def compute_straddle_metrics(raw_df: pd.DataFrame, date_str: str, spot: float) -> dict | None:
    """Compute ATM straddle cost and IV from a day's option chain."""
    df = raw_df[raw_df["_date"] == date_str].copy()
    if df.empty:
        return None

    df["strike"] = df["strike"].astype(float)
    df["bid"] = df["bid"].astype(float)
    df["ask"] = df["ask"].astype(float)
    df["close_price"] = df["close"].astype(float)
    df["option_type"] = df["right"].str.strip('"').str.lower()
    df["expiration_clean"] = df["expiration"].str.strip('"')
    df["expiry_dt"] = pd.to_datetime(df["expiration_clean"])
    ref_date = pd.Timestamp(date_str)
    df["days_to_expiry"] = (df["expiry_dt"] - ref_date).dt.days
    df["expiry_years"] = df["days_to_expiry"] / 365.0
    df["mid"] = (df["bid"] + df["ask"]) / 2

    # Filter for near-term options (14-45 days)
    df = df[
        (df["bid"] > 0) & (df["ask"] > df["bid"])
        & (df["mid"] > 0.05)
        & ((df["ask"] - df["bid"]) / df["mid"] < 1.0)
        & (df["days_to_expiry"] >= 14)
        & (df["days_to_expiry"] <= 45)
    ]

    if df.empty:
        return None

    # Pick nearest ~30 day expiry
    best_dte = df.iloc[(df["days_to_expiry"] - 30).abs().argsort()[:1]]["days_to_expiry"].values[0]
    exp_data = df[df["days_to_expiry"] == best_dte]

    # Find ATM strike
    strikes = exp_data["strike"].unique()
    if len(strikes) == 0:
        return None
    atm_strike = strikes[np.argmin(np.abs(strikes - spot))]

    atm_calls = exp_data[(exp_data["strike"] == atm_strike) & (exp_data["option_type"] == "call")]
    atm_puts = exp_data[(exp_data["strike"] == atm_strike) & (exp_data["option_type"] == "put")]

    if atm_calls.empty or atm_puts.empty:
        return None

    call_mid = atm_calls["mid"].values[0]
    put_mid = atm_puts["mid"].values[0]
    straddle_cost = call_mid + put_mid

    # Compute IV for the ATM options
    expiry_years = best_dte / 365.0
    prices = np.array([call_mid, put_mid])
    ivs = implied_vol_newton_raphson(
        prices=prices,
        spots=np.full(2, spot),
        strikes=np.full(2, atm_strike),
        expiries=np.full(2, expiry_years),
        rates=np.full(2, 0.05),
        option_types=np.array(["call", "put"]),
    )
    valid_ivs = ivs[~np.isnan(ivs)]
    if len(valid_ivs) == 0:
        return None

    avg_iv = float(np.mean(valid_ivs))
    # Implied move: straddle_cost / spot (as percentage)
    implied_move = straddle_cost / spot if spot > 0 else 0.0

    return {
        "avg_iv": avg_iv,
        "implied_move": implied_move,
        "straddle_cost": straddle_cost,
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
    dates = sorted(raw_df["_date"].unique())

    history_file = module_data_dir / f"{ticker}_iv_snapshots_thetadata.csv"
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

        result = compute_straddle_metrics(raw_df, date_str, spot)
        if result is None:
            continue

        row = {
            "date": date_str,
            "ticker": ticker,
            "spot": spot,
            "earnings_date": "",
            "days_to_earnings": 0,
            "avg_iv": result["avg_iv"],
            "implied_move": result["implied_move"],
            "straddle_cost": result["straddle_cost"],
            "provider": "thetadata",
        }
        append_to_history_thetadata(row, ticker, module_data_dir)
        added += 1

    if not quiet:
        print(f"  {ticker}: added {added}/{len(new_dates)} new dates ({len(existing_dates)} existing)")
    return added


def main():
    parser = argparse.ArgumentParser(description="Replay ThetaData into pre-earnings straddle history")
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

    print(f"Replay: {len(tickers)} tickers → pre_earnings_straddle history")
    print()

    total_added = 0
    for ticker in tickers:
        added = replay_ticker(ticker, THETADATA_DIR, module_data_dir, quiet=args.quiet)
        total_added += added

    print(f"\nDone: {total_added} new history rows added across {len(tickers)} tickers")


if __name__ == "__main__":
    main()

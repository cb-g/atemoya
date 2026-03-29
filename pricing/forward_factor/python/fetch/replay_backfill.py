#!/usr/bin/env python3
"""Replay ThetaData raw EOD chains into forward factor history CSVs.

Reads raw option chain archives, computes ATM IV at multiple DTE targets,
derives forward volatility and forward factors for each DTE pair, and
appends rows to data/{TICKER}_ff_history_thetadata.csv.

Idempotent. Zero fake data policy.

Usage:
    uv run pricing/forward_factor/python/fetch/replay_backfill.py --tickers SPY,AAPL
    uv run pricing/forward_factor/python/fetch/replay_backfill.py --all
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.iv import implied_vol_newton_raphson
from pricing.forward_factor.python.fetch.collect_snapshot import (
    HISTORY_COLUMNS,
    DTE_PAIRS,
    DTE_TOLERANCE,
    DTE_MIN,
    calculate_forward_factor,
)

THETADATA_DIR = Path(__file__).parents[4] / "pricing" / "thetadata" / "data"
MODULE_DATA_DIR = Path(__file__).parents[2] / "data"


def append_to_history_thetadata(rows: list[dict], ticker: str, data_dir: Path) -> None:
    """Append rows to {TICKER}_ff_history_thetadata.csv."""
    history_file = data_dir / f"{ticker}_ff_history_thetadata.csv"
    df = pd.DataFrame(rows, columns=HISTORY_COLUMNS)
    if history_file.exists():
        existing = pd.read_csv(history_file, usecols=["date", "dte_pair"], dtype=str)
        existing_keys = set(zip(existing["date"], existing["dte_pair"]))
        df = df[~df.apply(lambda r: (r["date"], r["dte_pair"]) in existing_keys, axis=1)]
        if df.empty:
            return
        df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        df.to_csv(history_file, index=False)


def parse_chain_with_iv(raw_df: pd.DataFrame, date_str: str, spot: float) -> pd.DataFrame:
    """Parse one day of ThetaData EOD into chain with IVs."""
    df = raw_df[raw_df["_date"] == date_str].copy()
    if df.empty:
        return pd.DataFrame()

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
        & (df["days_to_expiry"] >= DTE_MIN)
        & (df["days_to_expiry"] <= 365)
    ]

    # OTM only
    df = df[
        ((df["option_type"] == "put") & (df["strike"] < spot))
        | ((df["option_type"] == "call") & (df["strike"] >= spot))
    ]

    if df.empty:
        return pd.DataFrame()

    df["implied_vol"] = implied_vol_newton_raphson(
        prices=df["mid"].values,
        spots=np.full(len(df), spot),
        strikes=df["strike"].values,
        expiries=df["expiry_years"].values,
        rates=np.full(len(df), 0.05),
        option_types=df["option_type"].values,
    )
    df = df[df["implied_vol"] > 0]
    return df


def find_atm_iv_for_dte(chain_df: pd.DataFrame, spot: float, target_dte: int) -> tuple[float, int]:
    """Find ATM IV for the expiry closest to target_dte.

    Returns (atm_iv, actual_dte) or (0.0, 0) if not found.
    """
    if chain_df.empty:
        return 0.0, 0

    # Find best matching expiry
    expiries = chain_df[["days_to_expiry", "expiry_years"]].drop_duplicates()
    expiries = expiries[
        (expiries["days_to_expiry"] >= target_dte - DTE_TOLERANCE)
        & (expiries["days_to_expiry"] <= target_dte + DTE_TOLERANCE)
    ]
    if expiries.empty:
        return 0.0, 0

    best_idx = (expiries["days_to_expiry"] - target_dte).abs().idxmin()
    best_dte = int(expiries.loc[best_idx, "days_to_expiry"])
    best_expiry_years = expiries.loc[best_idx, "expiry_years"]

    expiry_data = chain_df[chain_df["expiry_years"] == best_expiry_years]

    # ATM strike
    strikes = expiry_data["strike"].unique()
    if len(strikes) == 0:
        return 0.0, 0
    atm_strike = strikes[np.argmin(np.abs(strikes - spot))]

    atm = expiry_data[expiry_data["strike"] == atm_strike]
    ivs = atm["implied_vol"].values
    ivs = ivs[ivs > 0]
    if len(ivs) == 0:
        return 0.0, 0

    return float(np.mean(ivs)), best_dte


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

    # Idempotency
    history_file = module_data_dir / f"{ticker}_ff_history_thetadata.csv"
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

    from lib.python.data_fetcher.thetadata_provider import ThetaDataProvider
    provider = ThetaDataProvider()

    added = 0
    for date_str in new_dates:
        spot = provider._fetch_underlying_price(ticker, date_str.replace("-", ""))
        if spot == 0.0:
            continue

        chain_df = parse_chain_with_iv(raw_df, date_str, spot)
        if chain_df.empty:
            continue

        rows = []
        for front_target, back_target in DTE_PAIRS:
            front_iv, front_dte = find_atm_iv_for_dte(chain_df, spot, front_target)
            back_iv, back_dte = find_atm_iv_for_dte(chain_df, spot, back_target)

            if front_iv <= 0 or back_iv <= 0:
                continue

            forward_vol, ff = calculate_forward_factor(front_iv, back_iv, front_dte, back_dte)
            if forward_vol <= 0:
                continue

            rows.append({
                "date": date_str,
                "ticker": ticker,
                "dte_pair": f"{front_dte}-{back_dte}",
                "front_dte": front_dte,
                "back_dte": back_dte,
                "front_iv": front_iv,
                "back_iv": back_iv,
                "forward_vol": forward_vol,
                "forward_factor": ff,
            })

        if rows:
            append_to_history_thetadata(rows, ticker, module_data_dir)
            added += 1

    if not quiet:
        print(f"  {ticker}: added {added}/{len(new_dates)} new dates ({len(existing_dates)} existing)")
    return added


def main():
    parser = argparse.ArgumentParser(description="Replay ThetaData into forward factor history")
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

    print(f"Replay: {len(tickers)} tickers → forward_factor history")
    print()

    total_added = 0
    for ticker in tickers:
        added = replay_ticker(ticker, THETADATA_DIR, module_data_dir, quiet=args.quiet)
        total_added += added

    print(f"\nDone: {total_added} new history rows added across {len(tickers)} tickers")


if __name__ == "__main__":
    main()

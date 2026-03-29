#!/usr/bin/env python3
"""Replay ThetaData raw EOD chains into dispersion trading history.

Computes index IV (SPY), weighted constituent IVs, dispersion level,
and implied/realized correlation for each trading day. Appends rows
to data/dispersion_history_thetadata.csv.

Idempotent. Zero fake data policy.

Usage:
    uv run pricing/dispersion_trading/python/fetch/replay_backfill.py
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.iv import implied_vol_newton_raphson
from pricing.dispersion_trading.python.fetch.collect_snapshot import (
    HISTORY_COLUMNS,
    DEFAULT_INDEX,
    DEFAULT_CONSTITUENTS,
    compute_implied_correlation,
    compute_realized_correlation,
)

THETADATA_DIR = Path(__file__).parents[4] / "pricing" / "thetadata" / "data"
MODULE_DATA_DIR = Path(__file__).parents[2] / "data"


def append_to_history_thetadata(row: dict, data_dir: Path) -> None:
    """Append one row to dispersion_history_thetadata.csv."""
    history_file = data_dir / "dispersion_history_thetadata.csv"
    df = pd.DataFrame([row], columns=HISTORY_COLUMNS)
    if history_file.exists():
        existing = pd.read_csv(history_file, usecols=["date"], dtype=str)
        if row["date"] in existing["date"].values:
            return
        df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        df.to_csv(history_file, index=False)


def compute_atm_iv_from_raw(raw_df: pd.DataFrame, date_str: str, spot: float) -> float:
    """Compute ATM IV from raw ThetaData chain for a single date."""
    df = raw_df[raw_df["_date"] == date_str].copy()
    if df.empty:
        return 0.0

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
        & (df["days_to_expiry"] >= 14) & (df["days_to_expiry"] <= 45)
    ]

    # OTM only
    df = df[
        ((df["option_type"] == "put") & (df["strike"] < spot))
        | ((df["option_type"] == "call") & (df["strike"] >= spot))
    ]

    if df.empty:
        return 0.0

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
        return 0.0

    # Pick nearest ~30d expiry
    best_expiry = df.iloc[(df["days_to_expiry"] - 30).abs().argsort()[:1]]["expiry_years"].values[0]
    exp_data = df[df["expiry_years"] == best_expiry]

    # ATM strike
    strikes = exp_data["strike"].unique()
    atm_strike = strikes[np.argmin(np.abs(strikes - spot))]
    atm = exp_data[exp_data["strike"] == atm_strike]
    return float(atm["iv"].mean()) if not atm.empty else 0.0


def main():
    parser = argparse.ArgumentParser(description="Replay ThetaData into dispersion history")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    module_data_dir = MODULE_DATA_DIR
    module_data_dir.mkdir(parents=True, exist_ok=True)

    from lib.python.data_fetcher.thetadata_provider import ThetaDataProvider
    provider = ThetaDataProvider()
    if not provider.is_available():
        print("Error: Theta Terminal not running", file=sys.stderr)
        sys.exit(1)

    # Load raw archives for index + constituents
    all_tickers = [DEFAULT_INDEX] + DEFAULT_CONSTITUENTS
    raw_data = {}
    for ticker in all_tickers:
        raw_file = THETADATA_DIR / f"{ticker}.csv"
        if not raw_file.exists():
            print(f"  Missing ThetaData archive for {ticker}, skipping")
            continue
        df = pd.read_csv(raw_file, dtype=str)
        df["_date"] = df["created"].str.strip('"').str.split("T").str[0]
        raw_data[ticker] = df

    if DEFAULT_INDEX not in raw_data:
        print(f"Error: no {DEFAULT_INDEX} archive", file=sys.stderr)
        sys.exit(1)

    # Find common dates across index
    index_dates = sorted(raw_data[DEFAULT_INDEX]["_date"].unique())

    # Idempotency
    history_file = module_data_dir / "dispersion_history_thetadata.csv"
    existing_dates = set()
    if history_file.exists():
        try:
            existing = pd.read_csv(history_file, usecols=["date"], dtype=str)
            existing_dates = set(existing["date"].values)
        except Exception:
            pass

    new_dates = [d for d in index_dates if d not in existing_dates]
    if not new_dates:
        print("All dates already in history")
        return

    # Fetch OHLCV for realized correlation
    earliest = datetime.strptime(new_dates[0], "%Y-%m-%d") - timedelta(days=30)
    latest = new_dates[-1].replace("-", "")
    ohlcv_data = {}
    for ticker in all_tickers:
        rows = provider._request_csv("/v3/stock/history/eod", {
            "symbol": ticker,
            "start_date": earliest.strftime("%Y%m%d"),
            "end_date": latest,
        })
        if rows:
            df = pd.DataFrame(rows)
            df["close"] = df["close"].astype(float)
            if "created" in df.columns:
                df["date_str"] = df["created"].str.split("T").str[0]
            else:
                df["date_str"] = df["date"]
            ohlcv_data[ticker] = df

    # Equal weights for constituents
    available_constituents = [c for c in DEFAULT_CONSTITUENTS if c in raw_data]
    n = len(available_constituents)
    weights = np.full(n, 1.0 / n)

    print(f"Replay: {len(new_dates)} dates, {DEFAULT_INDEX} + {n} constituents")
    print()

    added = 0
    for date_str in new_dates:
        # Index IV
        index_spot = provider._fetch_underlying_price(DEFAULT_INDEX, date_str.replace("-", ""))
        if index_spot == 0.0:
            continue
        index_iv = compute_atm_iv_from_raw(raw_data[DEFAULT_INDEX], date_str, index_spot)
        if index_iv <= 0:
            continue

        # Constituent IVs
        constituent_ivs = []
        for ticker in available_constituents:
            if ticker not in raw_data:
                constituent_ivs.append(0.0)
                continue
            spot = provider._fetch_underlying_price(ticker, date_str.replace("-", ""))
            if spot == 0.0:
                constituent_ivs.append(0.0)
                continue
            iv = compute_atm_iv_from_raw(raw_data[ticker], date_str, spot)
            constituent_ivs.append(iv)

        constituent_ivs = np.array(constituent_ivs)
        valid_mask = constituent_ivs > 0
        if valid_mask.sum() < 2:
            continue

        # Use only constituents with valid IV
        valid_ivs = constituent_ivs[valid_mask]
        valid_weights = weights[valid_mask]
        valid_weights = valid_weights / valid_weights.sum()  # renormalize

        weighted_avg_iv = float(np.average(valid_ivs, weights=valid_weights))
        dispersion = weighted_avg_iv - index_iv

        impl_corr = compute_implied_correlation(index_iv, valid_ivs, valid_weights)

        # Realized correlation from OHLCV
        real_corr = 0.0
        valid_tickers = [t for t, m in zip(available_constituents, valid_mask) if m]
        prices_dict = {}
        for t in valid_tickers:
            if t in ohlcv_data and "date_str" in ohlcv_data[t].columns:
                p = ohlcv_data[t][ohlcv_data[t]["date_str"] <= date_str]["close"].values
                if len(p) >= 16:
                    prices_dict[t] = p
        if len(prices_dict) >= 2:
            rc_weights = np.full(len(prices_dict), 1.0 / len(prices_dict))
            real_corr = compute_realized_correlation(prices_dict, rc_weights)

        row = {
            "date": date_str,
            "index": DEFAULT_INDEX,
            "index_iv": index_iv,
            "weighted_avg_iv": weighted_avg_iv,
            "dispersion_level": dispersion,
            "implied_correlation": impl_corr,
            "realized_correlation": real_corr,
        }
        append_to_history_thetadata(row, module_data_dir)
        added += 1

    print(f"\nDone: {added} new history rows added")


if __name__ == "__main__":
    main()

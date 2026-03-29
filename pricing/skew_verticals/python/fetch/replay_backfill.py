#!/usr/bin/env python3
"""Replay ThetaData raw EOD chains into skew verticals history CSVs.

Reads raw option chain archives, computes ATM IV, 25-delta IVs, skew
metrics, realized vol, and momentum for each trading day. Appends rows
to data/{TICKER}_skewvert_history_thetadata.csv.

Edge score is set to 0 during replay (it requires z-scores from
accumulated history). The scanner computes it when it runs.

Idempotent. Zero fake data policy.

Usage:
    uv run pricing/skew_verticals/python/fetch/replay_backfill.py --tickers SPY,AAPL
    uv run pricing/skew_verticals/python/fetch/replay_backfill.py --all
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.iv import implied_vol_newton_raphson
from pricing.skew_verticals.python.fetch.collect_snapshot import (
    HISTORY_COLUMNS,
    compute_skew_metrics,
    compute_realized_vol,
    compute_momentum,
)

THETADATA_DIR = Path(__file__).parents[4] / "pricing" / "thetadata" / "data"
MODULE_DATA_DIR = Path(__file__).parents[2] / "data"


def append_to_history_thetadata(row: dict, ticker: str, data_dir: Path) -> None:
    """Append one row to {TICKER}_skewvert_history_thetadata.csv."""
    history_file = data_dir / f"{ticker}_skewvert_history_thetadata.csv"
    df = pd.DataFrame([row], columns=HISTORY_COLUMNS)
    if history_file.exists():
        existing = pd.read_csv(history_file, usecols=["date"], dtype=str)
        if row["date"] in existing["date"].values:
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
        & (df["days_to_expiry"] >= 14)
        & (df["days_to_expiry"] <= 45)
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


def build_iv_maps(chain_df: pd.DataFrame, spot: float) -> tuple[dict, dict]:
    """Build strike→IV maps for calls and puts from nearest expiry."""
    if chain_df.empty:
        return {}, {}

    # Pick expiry closest to 30 days
    best_expiry = chain_df.iloc[
        (chain_df["days_to_expiry"] - 30).abs().argsort()[:1]
    ]["expiry_years"].values[0]

    exp_data = chain_df[chain_df["expiry_years"] == best_expiry]

    calls_iv = {}
    puts_iv = {}
    for _, row in exp_data.iterrows():
        if row["option_type"] == "call":
            calls_iv[row["strike"]] = row["implied_vol"]
        else:
            puts_iv[row["strike"]] = row["implied_vol"]

    return calls_iv, puts_iv


def fetch_ohlcv_history(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch OHLCV from ThetaData."""
    from lib.python.data_fetcher.thetadata_provider import ThetaDataProvider
    provider = ThetaDataProvider()
    if not provider.is_available():
        return pd.DataFrame()
    rows = provider._request_csv("/v3/stock/history/eod", {
        "symbol": ticker,
        "start_date": start_date,
        "end_date": end_date,
    })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = df[col].astype(float)
    df = df.rename(columns={"close": "Close"})
    if "created" in df.columns:
        df["date"] = df["created"].str.split("T").str[0]
    return df


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

    history_file = module_data_dir / f"{ticker}_skewvert_history_thetadata.csv"
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

    # Fetch OHLCV for the full range + lookback (one call per ticker)
    earliest = datetime.strptime(new_dates[0], "%Y-%m-%d") - timedelta(days=90)
    latest = new_dates[-1].replace("-", "")
    ohlcv = fetch_ohlcv_history(ticker, earliest.strftime("%Y%m%d"), latest)

    # SPY OHLCV for momentum alpha computation
    spy_ohlcv = fetch_ohlcv_history("SPY", earliest.strftime("%Y%m%d"), latest)

    added = 0
    for date_str in new_dates:
        spot = provider._fetch_underlying_price(ticker, date_str.replace("-", ""))
        if spot == 0.0:
            continue

        chain_df = parse_chain_with_iv(raw_df, date_str, spot)
        if chain_df.empty:
            continue

        calls_iv, puts_iv = build_iv_maps(chain_df, spot)
        skew = compute_skew_metrics(calls_iv, puts_iv, spot)
        if not skew or skew.get("atm_iv", 0) <= 0:
            continue

        # RV from OHLCV
        rv_30d = 0.0
        if not ohlcv.empty and "date" in ohlcv.columns:
            ohlcv_to_date = ohlcv[ohlcv["date"] <= date_str]
            if len(ohlcv_to_date) >= 31:
                rv_30d = compute_realized_vol(ohlcv_to_date["Close"].values, lookback=30)

        vrp = skew["atm_iv"] - rv_30d

        # Momentum
        momentum = {"return_1w": 0, "return_1m": 0, "return_3m": 0, "momentum_score": 0}
        if not ohlcv.empty and "date" in ohlcv.columns:
            ohlcv_to_date = ohlcv[ohlcv["date"] <= date_str]
            spy_to_date = spy_ohlcv[spy_ohlcv["date"] <= date_str] if not spy_ohlcv.empty and "date" in spy_ohlcv.columns else pd.DataFrame()
            if len(ohlcv_to_date) >= 5:
                spy_prices = spy_to_date["Close"].values if not spy_to_date.empty else np.array([])
                momentum = compute_momentum(ohlcv_to_date["Close"].values, spy_prices)

        row = {
            "date": date_str,
            "ticker": ticker,
            "spot": spot,
            "atm_iv": skew["atm_iv"],
            "call_25d_iv": skew["call_25d_iv"],
            "put_25d_iv": skew["put_25d_iv"],
            "call_skew": skew["call_skew"],
            "put_skew": skew["put_skew"],
            "rv_30d": rv_30d,
            "vrp": vrp,
            "return_1w": momentum["return_1w"],
            "return_1m": momentum["return_1m"],
            "return_3m": momentum["return_3m"],
            "momentum_score": momentum["momentum_score"],
            "edge_score": 0,  # Requires z-scores from history; scanner computes it
        }
        append_to_history_thetadata(row, ticker, module_data_dir)
        added += 1

    if not quiet:
        print(f"  {ticker}: added {added}/{len(new_dates)} new dates ({len(existing_dates)} existing)")
    return added


def main():
    parser = argparse.ArgumentParser(description="Replay ThetaData into skew verticals history")
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

    print(f"Replay: {len(tickers)} tickers → skew_verticals history")
    print()

    total_added = 0
    for ticker in tickers:
        added = replay_ticker(ticker, THETADATA_DIR, module_data_dir, quiet=args.quiet)
        total_added += added

    print(f"\nDone: {total_added} new history rows added across {len(tickers)} tickers")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Replay ThetaData raw EOD chains into volatility arbitrage history CSVs.

Reads raw option chain archives from pricing/thetadata/data/{TICKER}.csv,
computes ATM IV for each trading day, fetches historical OHLCV for RV
computation, and appends rows to data/{TICKER}_volarb_history_thetadata.csv.

Idempotent: skips dates already present in history.
Zero fake data: skips dates where ATM IV computation fails.

Usage:
    uv run pricing/volatility_arbitrage/python/fetch/replay_backfill.py --tickers SPY,AAPL
    uv run pricing/volatility_arbitrage/python/fetch/replay_backfill.py --all
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.iv import implied_vol_newton_raphson
from pricing.volatility_arbitrage.python.fetch.collect_snapshot import (
    HISTORY_COLUMNS,
    yang_zhang_rv,
    ewma_forecast,
    EWMA_LAMBDA,
)

THETADATA_DIR = Path(__file__).parents[4] / "pricing" / "thetadata" / "data"
MODULE_DATA_DIR = Path(__file__).parents[2] / "data"


def append_to_history_thetadata(row: dict, ticker: str, data_dir: Path) -> None:
    """Append one row to {TICKER}_volarb_history_thetadata.csv."""
    history_file = data_dir / f"{ticker}_volarb_history_thetadata.csv"
    df = pd.DataFrame([row], columns=HISTORY_COLUMNS)
    if history_file.exists():
        existing = pd.read_csv(history_file, usecols=["date"], dtype=str)
        if row["date"] in existing["date"].values:
            return
        df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        df.to_csv(history_file, index=False)


def compute_atm_iv_from_chain(chain_df: pd.DataFrame, spot: float) -> float:
    """Compute ATM IV from a day's option chain.

    Picks the nearest expiry 14-45 days out, finds ATM strike,
    averages call and put IV.
    """
    if chain_df.empty:
        return 0.0

    # Pick nearest expiry in 14-45 day range
    valid_expiries = chain_df[
        (chain_df["days_to_expiry"] >= 14) & (chain_df["days_to_expiry"] <= 45)
    ]
    if valid_expiries.empty:
        valid_expiries = chain_df[chain_df["days_to_expiry"] >= 7]
    if valid_expiries.empty:
        return 0.0

    target_dte = 30
    best_expiry = valid_expiries.iloc[
        (valid_expiries["days_to_expiry"] - target_dte).abs().argsort()[:1]
    ]["expiry_years"].values[0]

    expiry_data = chain_df[chain_df["expiry_years"] == best_expiry]

    # Find ATM strike
    strikes = expiry_data["strike"].unique()
    atm_strike = strikes[np.argmin(np.abs(strikes - spot))]

    atm = expiry_data[expiry_data["strike"] == atm_strike]
    call_iv = atm[atm["option_type"] == "call"]["implied_vol"]
    put_iv = atm[atm["option_type"] == "put"]["implied_vol"]

    ivs = []
    if not call_iv.empty and call_iv.iloc[0] > 0:
        ivs.append(call_iv.iloc[0])
    if not put_iv.empty and put_iv.iloc[0] > 0:
        ivs.append(put_iv.iloc[0])

    return float(np.mean(ivs)) if ivs else 0.0


def parse_thetadata_chain(raw_df: pd.DataFrame, date_str: str, spot: float) -> pd.DataFrame:
    """Parse one day of ThetaData EOD into a chain with computed IVs."""
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

    df["mid"] = (df["bid"] + df["ask"]) / 2

    # Quality filters
    df = df[
        (df["bid"] > 0)
        & (df["ask"] > df["bid"])
        & (df["mid"] > 0.05)
        & ((df["ask"] - df["bid"]) / df["mid"] < 1.0)
        & (df["days_to_expiry"] >= 14)
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


def fetch_ohlcv_history(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch OHLCV from ThetaData for the full date range (one API call)."""
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
    # Rename to match yfinance convention (capitalized)
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                            "close": "Close", "volume": "Volume"})
    # Extract date from 'created' column (format: "2026-03-27T17:15:27.387")
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

    # Idempotency
    history_file = module_data_dir / f"{ticker}_volarb_history_thetadata.csv"
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

    # Fetch OHLCV for the full range (one API call)
    # Need extra lookback for 21-day RV window
    earliest = datetime.strptime(new_dates[0], "%Y-%m-%d") - timedelta(days=45)
    latest = new_dates[-1].replace("-", "")
    ohlcv = fetch_ohlcv_history(ticker, earliest.strftime("%Y%m%d"), latest)
    if ohlcv.empty or len(ohlcv) < 22:
        if not quiet:
            print(f"  {ticker}: insufficient OHLCV history")
        return 0

    # Get spot prices for each date from ThetaData
    from lib.python.data_fetcher.thetadata_provider import ThetaDataProvider
    provider = ThetaDataProvider()

    added = 0
    for date_str in new_dates:
        spot = provider._fetch_underlying_price(ticker, date_str.replace("-", ""))
        if spot == 0.0:
            continue

        # Parse chain and compute ATM IV
        chain_df = parse_thetadata_chain(raw_df, date_str, spot)
        if chain_df.empty:
            continue

        atm_iv = compute_atm_iv_from_chain(chain_df, spot)
        if atm_iv <= 0:
            continue

        # Compute RV from OHLCV up to this date
        date_dt = pd.Timestamp(date_str)
        if "date" in ohlcv.columns:
            ohlcv_to_date = ohlcv[ohlcv["date"] <= date_str]
        else:
            ohlcv_to_date = ohlcv

        rv_yz = yang_zhang_rv(ohlcv_to_date, window=21)
        if rv_yz <= 0:
            closes = ohlcv_to_date["Close"].values
            if len(closes) >= 22:
                log_rets = np.diff(np.log(closes[-22:]))
                rv_yz = float(np.std(log_rets, ddof=1) * np.sqrt(252))
            else:
                continue

        closes = ohlcv_to_date["Close"].values
        log_returns = np.diff(np.log(closes))
        rv_ewma = ewma_forecast(log_returns, lam=EWMA_LAMBDA)
        rv_forecast = rv_ewma

        iv_rv_spread = atm_iv - rv_yz
        iv_rv_ratio = atm_iv / rv_yz if rv_yz > 0 else 0.0

        row = {
            "date": date_str,
            "ticker": ticker,
            "spot": spot,
            "atm_iv": atm_iv,
            "rv_yang_zhang": rv_yz,
            "rv_ewma": rv_ewma,
            "rv_forecast": rv_forecast,
            "iv_rv_spread": iv_rv_spread,
            "iv_rv_ratio": iv_rv_ratio,
        }
        append_to_history_thetadata(row, ticker, module_data_dir)
        added += 1

    if not quiet:
        print(f"  {ticker}: added {added}/{len(new_dates)} new dates ({len(existing_dates)} existing)")
    return added


def main():
    parser = argparse.ArgumentParser(description="Replay ThetaData into vol arb history")
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

    print(f"Replay: {len(tickers)} tickers → volatility_arbitrage history")
    print()

    total_added = 0
    for ticker in tickers:
        added = replay_ticker(ticker, THETADATA_DIR, module_data_dir, quiet=args.quiet)
        total_added += added

    print(f"\nDone: {total_added} new history rows added across {len(tickers)} tickers")


if __name__ == "__main__":
    main()

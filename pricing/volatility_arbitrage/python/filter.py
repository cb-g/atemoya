#!/usr/bin/env python3
"""
volatility_arbitrage as a cross-module FILTER, not a standalone signal source.

The module's standalone arbitrage signals (butterfly/calendar/parity violations)
get eaten by bid-ask in liquid markets; its durable value is as a pre-trade
context check for signals that originate elsewhere. The highest-leverage piece is
the IV-vs-RV "environment dial": is implied vol rich or cheap vs recent realized
right now? Every other module's signal reads better with it attached.

`vol_environment(ticker)` is fast (one file read, no network) and importable from
any module's notify path:

    from pricing.volatility_arbitrage.python.filter import vol_environment
    env = vol_environment(ticker)
    if env: msg += "\\n" + env["line"]

It reuses the shared variance_swaps 1-yr history (atm_iv + spot_price), so IV and
realized vol come from one consistent series.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
VARSWAP_DATA = PROJECT_ROOT / "pricing" / "variance_swaps" / "data"
TRADING_DAYS = 252


def _load_history(ticker: str):
    """Merged 1-yr history (date, spot_price, atm_iv) from the variance_swaps
    backfill, thetadata preferred on overlap. None if too little data."""
    frames = []
    for src in (f"{ticker}_iv_history_thetadata.csv", f"{ticker}_iv_history_yfinance.csv"):
        f = VARSWAP_DATA / src
        if not f.exists():
            continue
        try:
            df = pd.read_csv(f)
            if {"date", "spot_price", "atm_iv"} <= set(df.columns):
                frames.append(df[["date", "spot_price", "atm_iv"]])
        except Exception:
            pass
    if not frames:
        return None
    h = pd.concat(frames, ignore_index=True).dropna()
    h = h[(h["spot_price"] > 0) & (h["atm_iv"] > 0)]
    h = h.drop_duplicates(subset=["date"], keep="first").sort_values("date").reset_index(drop=True)
    return h if len(h) >= 22 else None


def realized_vol(spot, window: int = 21):
    """Annualized close-to-close realized vol over the trailing `window` days."""
    s = pd.Series(spot, dtype=float)
    logret = np.log(s / s.shift(1)).dropna()
    if len(logret) < 2:
        return None
    window = min(window, len(logret))
    return float(logret.iloc[-window:].std(ddof=1) * np.sqrt(TRADING_DAYS))


def vol_environment(ticker: str, rv_window: int = 21):
    """IV-vs-RV environment dial for a ticker. Returns a dict (or None if no
    history): atm_iv, realized_vol, iv_rv_ratio, verdict (RICH/FAIR/CHEAP), bias,
    as_of, and a ready-to-append one-line `line` for notifications."""
    h = _load_history(ticker.upper())
    if h is None:
        return None
    iv = float(h["atm_iv"].iloc[-1])
    rv = realized_vol(h["spot_price"].to_numpy(), rv_window)
    if rv is None or rv <= 0:
        return None
    ratio = iv / rv
    if ratio >= 1.25:
        verdict, bias = "RICH", "favor selling premium / short-vol"
    elif ratio <= 0.90:
        verdict, bias = "CHEAP", "favor buying premium / long-vol"
    else:
        verdict, bias = "FAIR", "no strong vol-carry edge"
    return {
        "ticker": ticker.upper(),
        "atm_iv": iv,
        "realized_vol": rv,
        "iv_rv_ratio": ratio,
        "verdict": verdict,
        "bias": bias,
        "as_of": h["date"].iloc[-1],
        "tag": f"IV/RV {ratio:.2f}x {verdict}",
        "line": f"vol env: IV {iv * 100:.0f}% / RV{rv_window} {rv * 100:.0f}% = {ratio:.2f}x {verdict} ({bias})",
    }


def vol_env_block(df, ticker_col: str = "ticker", signal_col: str = "signal") -> str:
    """Compact IV-vs-RV context block to append to a module's notification.

    Pass the module's signal-scan DataFrame; this annotates its actionable
    tickers (non-NEUTRAL rows when a signal column exists, else all) with each
    one's vol environment. Returns "" when nothing to add. One-liner for any
    module's notify path:  message += vol_env_block(df)
    """
    try:
        if ticker_col not in df.columns:
            return ""
        sub = df
        if signal_col in df.columns:
            sub = df[~df[signal_col].astype(str).str.contains("NEUTRAL", case=False, na=False)]
        tickers = list(dict.fromkeys(sub[ticker_col].dropna().tolist()))  # preserve order, unique
    except Exception:
        return ""
    envs = [vol_environment(t) for t in tickers]
    parts = [f"{e['ticker']} {e['iv_rv_ratio']:.2f}x {e['verdict']}" for e in envs if e]
    if not parts:
        return ""
    return "\n--- vol env (IV/RV, vs trailing realized) ---\n" + " · ".join(parts)


def main():
    ap = argparse.ArgumentParser(description="IV-vs-RV vol environment dial (cross-module filter)")
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--rv-window", type=int, default=21)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    env = vol_environment(args.ticker, args.rv_window)
    if env is None:
        print(f"No vol history for {args.ticker.upper()} (not in the variance_swaps backfill)",
              file=sys.stderr)
        sys.exit(1)
    if args.json:
        print(json.dumps(env, indent=2))
    else:
        print(f"\n=== Vol environment: {env['ticker']} (as of {env['as_of']}) ===")
        print(f"  {env['line']}")


if __name__ == "__main__":
    main()

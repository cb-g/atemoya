#!/usr/bin/env python3
"""
ATM IV percentile for hedging timing.

Answers "is this ticker's protection cheap or rich right now vs its own trailing
~1-year volatility?" before you pay for a hedge — the timing lens that the
hedging tools otherwise lack.

- History (the distribution to rank against): the canonical 1-yr ATM IV series
  produced by the variance_swaps ThetaData backfill
  ({TICKER}_iv_history_{thetadata,yfinance}.csv, merged by date, thetadata
  preferred). This is reused as the shared ATM-IV series rather than recomputed.
- Current ATM IV: computed fresh from the latest ThetaData chain (the expiry
  nearest ~30 DTE, averaging the nearest-the-money call & put IVs, inverted from
  mid-quotes via the shared Newton-Raphson solver). Override with --current-iv.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Add project root to path for lib imports (this file is at
# pricing/options_hedging/python/, so repo root is parents[3])
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from lib.python.data_fetcher.thetadata_provider import ThetaDataProvider
from lib.python.iv import implied_vol_newton_raphson

PROJECT_ROOT = Path(__file__).resolve().parents[3]
VARSWAP_DATA = PROJECT_ROOT / "pricing" / "variance_swaps" / "data"
RISK_FREE_RATE = 0.043  # short-rate; IV is weakly sensitive to r


def load_atm_iv_history(ticker: str, min_days: int = 30):
    """Load the merged 1-yr ATM IV series for a ticker from the variance_swaps
    backfill (thetadata preferred on overlap). Returns a DataFrame[date, atm_iv]
    or None if too little history."""
    frames = []
    for src in (f"{ticker}_iv_history_thetadata.csv", f"{ticker}_iv_history_yfinance.csv"):
        f = VARSWAP_DATA / src
        if not f.exists():
            continue
        try:
            df = pd.read_csv(f)
            if "date" in df.columns and "atm_iv" in df.columns:
                frames.append(df[["date", "atm_iv"]])
        except Exception:
            pass
    if not frames:
        return None
    h = pd.concat(frames, ignore_index=True)
    h = h.dropna(subset=["atm_iv"])
    h = h[h["atm_iv"] > 0]
    h = h.drop_duplicates(subset=["date"], keep="first").sort_values("date").reset_index(drop=True)
    return h if len(h) >= min_days else None


def current_atm_iv(ticker: str, target_dte: int = 30):
    """Compute current ATM IV from the latest available ThetaData chain.

    Returns (atm_iv_decimal, as_of_date_str) or (None, as_of) on failure.
    """
    provider = ThetaDataProvider()
    if not provider.is_available():
        return None, None

    chain, snap = None, None
    for back in range(6):  # walk back to the most recent EOD (weekends/holidays)
        d = datetime.now() - timedelta(days=back)
        cand = provider.fetch_option_chain_historical(ticker, d.strftime("%Y%m%d"))
        if cand is not None and (cand.calls or cand.puts):
            chain, snap = cand, d
            break
    if chain is None or chain.underlying_price <= 0:
        return None, (snap.strftime("%Y-%m-%d") if snap else None)

    spot = chain.underlying_price
    contracts = list(chain.calls) + list(chain.puts)

    # Pick the expiry nearest target_dte.
    exp_dte = {}
    for c in contracts:
        try:
            dte = (datetime.strptime(c.expiry, "%Y-%m-%d") - snap).days
        except ValueError:
            continue
        if dte >= 7:
            exp_dte.setdefault(c.expiry, dte)
    if not exp_dte:
        return None, snap.strftime("%Y-%m-%d")
    target_exp = min(exp_dte, key=lambda e: abs(exp_dte[e] - target_dte))
    dte_years = exp_dte[target_exp] / 365.0

    # Nearest-the-money legs on that expiry (a few closest strikes to spot).
    legs = []
    for c in contracts:
        if c.expiry != target_exp or c.bid <= 0 or c.ask <= c.bid:
            continue
        mid = 0.5 * (c.bid + c.ask)
        if mid < 0.05:
            continue
        legs.append((abs(c.strike - spot), c.option_type, c.strike, mid))
    if not legs:
        return None, snap.strftime("%Y-%m-%d")
    legs.sort()
    near = legs[:4]
    ivs = implied_vol_newton_raphson(
        prices=np.array([x[3] for x in near], dtype=float),
        spots=np.full(len(near), spot, dtype=float),
        strikes=np.array([x[2] for x in near], dtype=float),
        expiries=np.full(len(near), dte_years, dtype=float),
        rates=np.full(len(near), RISK_FREE_RATE, dtype=float),
        option_types=np.array([x[1] for x in near]),
    )
    ivs = ivs[~np.isnan(ivs)]
    if len(ivs) == 0:
        return None, snap.strftime("%Y-%m-%d")
    return float(np.mean(ivs)), snap.strftime("%Y-%m-%d")


def classify(pct: float) -> str:
    if pct < 20:
        return "VERY CHEAP — protection unusually cheap vs its year (good time to hedge)"
    if pct < 40:
        return "CHEAP — below-median vol, favorable to buy protection"
    if pct < 60:
        return "FAIR — mid-range vol"
    if pct < 80:
        return "ELEVATED — above-median vol, protection getting pricey"
    return "EXPENSIVE — protection rich vs its year (prefer spreads / consider selling vol)"


def main():
    ap = argparse.ArgumentParser(description="ATM IV percentile vs trailing 1-yr history")
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--current-iv", type=float, default=None,
                    help="Override current ATM IV (decimal); else computed from the latest ThetaData chain")
    ap.add_argument("--window", type=int, default=0,
                    help="Trailing window in observations (0 = full history)")
    ap.add_argument("--output-dir", default="pricing/options_hedging/output")
    args = ap.parse_args()
    t = args.ticker.upper()

    hist = load_atm_iv_history(t)
    if hist is None:
        print(f"Error: no ATM IV history for {t} (not in the variance_swaps backfill universe)",
              file=sys.stderr)
        sys.exit(1)

    series = hist["atm_iv"]
    hist_start, hist_end = hist["date"].iloc[0], hist["date"].iloc[-1]
    if args.window > 0 and len(series) > args.window:
        series = series.iloc[-args.window:]

    if args.current_iv is not None:
        cur, cur_src = args.current_iv, "override"
    else:
        cur, as_of = current_atm_iv(t)
        if cur is None:
            cur = float(hist["atm_iv"].iloc[-1])
            cur_src = f"latest history ({hist_end})"
        else:
            cur_src = f"ThetaData chain ({as_of})"

    pct = float((series.to_numpy() <= cur).mean() * 100.0)

    print(f"\n=== ATM IV percentile: {t} ===")
    print(f"  Current ATM IV : {cur * 100:.1f}%   (source: {cur_src})")
    print(f"  Percentile     : {pct:.0f}th  over {len(series)} obs ({hist_start} -> {hist_end})")
    print(f"  History min/med/max: {series.min() * 100:.1f}% / {series.median() * 100:.1f}% / {series.max() * 100:.1f}%")
    print(f"  Verdict        : {classify(pct)}")

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    of = out / f"{t}_iv_percentile.json"
    of.write_text(json.dumps({
        "ticker": t,
        "current_atm_iv": cur,
        "current_source": cur_src,
        "percentile": round(pct, 1),
        "n_obs": int(len(series)),
        "history_start": hist_start,
        "history_end": hist_end,
        "iv_min": float(series.min()),
        "iv_median": float(series.median()),
        "iv_max": float(series.max()),
        "verdict": classify(pct),
    }, indent=2))
    print(f"\n✓ Saved to {of}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Turn actionable skew_verticals signals into placeable vertical spreads.

For each actionable signal (PUT/CALL VERTICAL), fetch a FRESH option chain
(ThetaData-first, yfinance fallback), pick a ~30-DTE expiry, hand the chain to the
OCaml strike selector (strike_select.exe, which reuses spreads.ml) and write the
placeable result to output/vertical_trades_<date>.{csv,json}. Read directly — no
notification (that path is left untouched for later).

Signal/direction come from the (clean, ThetaData-history) Python scanner; this only
adds the strikes. Run via ``uv run`` (build the selector first:
``dune build pricing/skew_verticals/ocaml/``).
"""

import argparse
import json
import math
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from scipy.stats import norm

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = Path(__file__).resolve().parents[1]
WORKDIR = MODULE_DIR / "data" / "_strike_chains"
OUTPUT_DIR = MODULE_DIR / "output"
EXE = PROJECT_ROOT / "_build" / "default" / "pricing" / "skew_verticals" / "ocaml" / "bin" / "strike_select.exe"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "pricing" / "options_hedging" / "python" / "fetch"))
import fetch_options as fo  # noqa: E402  (reuse the ThetaData/yfinance chain fetchers)

DIRECTION = {"PUT VERTICAL": "bullish", "CALL VERTICAL": "bearish"}
CHAIN_HEADER = "strike,option_type,implied_vol,bid,ask,open_interest,volume,mid_price,delta"


def bs_delta(opt_type, S, K, T, sigma, r=fo.RISK_FREE_RATE):
    """Black-Scholes delta (ThetaData carries no greeks, and the OCaml chain CSV
    reports a delta column)."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return float(norm.cdf(d1)) if opt_type == "call" else float(norm.cdf(d1) - 1.0)


def fetch_chain(ticker):
    """Fresh full chain (not OTM-only — debit-spread long legs need near-ATM strikes)."""
    try:
        df = fo.fetch_chain_thetadata(ticker, otm_only=False)
    except Exception:
        df = None
    if df is None or df.empty:
        try:
            df = fo.fetch_chain_yfinance(ticker)
        except Exception:
            df = None
    return df


def pick_expiry(df, target_dte):
    df = df.copy()
    df["dte"] = (df["expiry"] * 365.0).round().astype(int)
    counts = df.groupby("dte").size()
    eligible = counts[counts >= 4].index.tolist()
    if not eligible:
        return None, None
    chosen = min(eligible, key=lambda d: abs(d - target_dte))
    return chosen, df[df["dte"] == chosen]


def get_spot(row, ticker):
    if row is not None and "spot" in row and pd.notna(row.get("spot")) and row["spot"] > 0:
        return float(row["spot"])
    try:
        import yfinance as yf
        p = yf.Ticker(ticker).fast_info.get("lastPrice")
        return float(p) if p else 0.0
    except Exception:
        return 0.0


def write_chain_csvs(ticker, exp_tag, sub, spot, dte):
    WORKDIR.mkdir(parents=True, exist_ok=True)
    T = max(dte / 365.0, 1e-6)

    def write(side, leg):
        lines = [CHAIN_HEADER]
        for _, r in leg.iterrows():
            mid = 0.5 * (r["bid"] + r["ask"])
            delta = bs_delta(r["option_type"], spot, r["strike"], T, r["implied_volatility"])
            lines.append(
                f"{r['strike']},{r['option_type']},{r['implied_volatility']:.6f},"
                f"{r['bid']:.4f},{r['ask']:.4f},0,0,{mid:.4f},{delta:.4f}"
            )
        (WORKDIR / f"{ticker}_{exp_tag}_{side}.csv").write_text("\n".join(lines) + "\n")

    write("calls", sub[sub["option_type"] == "call"])
    write("puts", sub[sub["option_type"] == "put"])
    atm = float(sub.loc[(sub["strike"] - spot).abs().idxmin(), "strike"])
    (WORKDIR / f"{ticker}_{exp_tag}_metadata.csv").write_text(
        f"ticker,spot,expiration,days,atm\n{ticker},{spot},{exp_tag},{dte},{atm}\n"
    )


def run_strike_select(ticker, direction, exp_tag):
    res = subprocess.run(
        [str(EXE), ticker, "--direction", direction, "--expiration", exp_tag, "--data", str(WORKDIR)],
        capture_output=True, text=True,
    )
    for line in reversed(res.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                pass
    return {"ticker": ticker, "direction": direction, "found": False,
            "error": (res.stderr or "no json from selector").strip()[:200]}


def actionable_rows(args):
    if args.tickers:
        rows = []
        for spec in args.tickers.split(","):
            spec = spec.strip()
            if not spec:
                continue
            t, _, d = spec.partition(":")
            rows.append({"ticker": t.strip().upper(), "direction": (d.strip() or "bullish"),
                         "signal": "", "spot": float("nan")})
        return pd.DataFrame(rows)
    df = pd.read_csv(args.scan)
    df = df[df["signal"].astype(str).str.contains("VERTICAL")].copy()
    df["direction"] = df["signal"].map(lambda s: DIRECTION.get(str(s).strip(), None))
    return df[df["direction"].notna()]


def main():
    ap = argparse.ArgumentParser(description="Build placeable vertical spreads from actionable signals")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--scan", help="path to scan_signals output CSV")
    g.add_argument("--tickers", help="ad-hoc: TICKER:bullish,TICKER:bearish")
    ap.add_argument("--target-dte", type=int, default=30)
    args = ap.parse_args()

    if not EXE.exists():
        print(f"strike selector not built: {EXE}\n  run: dune build pricing/skew_verticals/ocaml/", file=sys.stderr)
        sys.exit(1)

    rows = actionable_rows(args)
    if rows.empty:
        print("no actionable signals", file=sys.stderr)
        return

    results = []
    for _, row in rows.iterrows():
        ticker, direction = row["ticker"], row["direction"]
        chain = fetch_chain(ticker)
        if chain is None or chain.empty:
            results.append({"ticker": ticker, "direction": direction, "found": False, "error": "no chain"})
            print(f"  {ticker}: no chain", file=sys.stderr)
            continue
        spot = get_spot(row, ticker)
        dte, sub = pick_expiry(chain, args.target_dte)
        if sub is None or spot <= 0:
            results.append({"ticker": ticker, "direction": direction, "found": False, "error": "no expiry/spot"})
            print(f"  {ticker}: no usable expiry/spot", file=sys.stderr)
            continue
        exp_tag = (date.today() + timedelta(days=int(dte))).isoformat()
        write_chain_csvs(ticker, exp_tag, sub, spot, int(dte))
        sel = run_strike_select(ticker, direction, exp_tag)
        for k in ("signal", "edge_score", "call_skew_z", "put_skew_z", "vrp", "momentum_score", "atm_iv"):
            if k in row and pd.notna(row.get(k)):
                sel[k] = row[k]
        sel["spot"] = spot
        results.append(sel)
        print(f"  {ticker} {direction}: {sel.get('spread_type') if sel.get('found') else 'no-spread'}", file=sys.stderr)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"vertical_trades_{date.today()}.json").write_text(json.dumps(results, indent=2, default=str))
    placeable = [r for r in results if r.get("found")]
    if placeable:
        cols = ["ticker", "direction", "signal", "spread_type", "expiration", "days_to_expiry",
                "long_strike", "short_strike", "width", "debit", "max_profit", "max_loss",
                "reward_risk_ratio", "breakeven", "prob_profit", "expected_value",
                "edge_score", "vrp", "momentum_score", "spot", "atm_iv"]
        df = pd.DataFrame(placeable)
        df = df[[c for c in cols if c in df.columns]]
        out_csv = OUTPUT_DIR / f"vertical_trades_{date.today()}.csv"
        df.to_csv(out_csv, index=False)
        print(f"\nwrote {len(placeable)}/{len(results)} placeable spreads -> {out_csv}")
        pd.set_option("display.width", 220)
        print(df.to_string(index=False))
    else:
        print(f"\nno placeable spreads (of {len(results)} signals)")


if __name__ == "__main__":
    main()

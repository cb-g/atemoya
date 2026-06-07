#!/usr/bin/env python3
"""Point-in-time (diagnostic) backtest of the factor ranks vs forward returns.

Reconstructs an approximate point-in-time panel at each annual rebalance using
yfinance's historical annual statements (columns = period-end dates), with a strict
filing-availability lag so we never use a statement before it was filed. At each
rebalance it invokes the SAME OCaml ranker the live path uses, joins forward 12-month
returns, and reports Spearman rank IC + quintile spread for value / quality / combined.

HONEST CAVEATS (also printed in the report): yfinance statements go ~5y deep -> only
~3-4 non-overlapping annual observations (diagnostic, not Sharpe-quotable); the
universe is today's survivors (survivorship bias -> trust the spread/IC ORDERING, not
absolute returns); statements are as-currently-reported (mild restatement look-ahead);
market cap uses CURRENT shares x historical price (level error, mostly cancels in the
cross-section, but makes the shareholder-yield factor's backtest indicative only).
Restricted to same-reporting-currency names to avoid historical-FX reconstruction.

Run via ``uv run`` (build the OCaml ranker first: ``dune build valuation/factor_rank/ocaml/``).
"""

import argparse
import glob
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf
from scipy.stats import spearmanr

MODULE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = MODULE_DIR / "output"
TMP_DIR = MODULE_DIR / "data" / "_backtest_tmp"
EXE = PROJECT_ROOT / "_build" / "default" / "valuation" / "factor_rank" / "ocaml" / "bin" / "main.exe"
DEFAULT_UNIVERSE = PROJECT_ROOT / "pricing" / "liquidity" / "data" / "liquid_tickers.txt"
LAG_DAYS = 90  # filing-availability lag (annual)

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(MODULE_DIR / "python" / "fetch"))
from lib.python.yfinance_utils import financial_fx_factor  # noqa: E402
import fetch_panel as fp  # noqa: E402  (reuse the statement row-label schema)


def cell(df, labels, col):
    if df is None or getattr(df, "empty", True) or col is None:
        return None
    for lab in labels:
        if lab in df.index:
            try:
                v = df.loc[lab, col]
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    return float(v)
            except Exception:
                continue
    return None


def pick_col(df, asof):
    """Newest statement column whose period-end + LAG <= asof (else None). Never the
    blind most-recent column — that is the classic look-ahead leak."""
    if df is None or getattr(df, "empty", True):
        return None
    elig = [c for c in df.columns if pd.Timestamp(c) + pd.Timedelta(days=LAG_DAYS) <= asof]
    return max(elig) if elig else None


def fetch_bundle(ticker):
    try:
        tk = yf.Ticker(ticker)
        info = tk.info
        if not info or not info.get("marketCap"):
            return None
        fx, trading, financial, _ = financial_fx_factor(info)
        if financial != trading:
            return None  # same-reporting-currency only (no historical FX)
        inc = tk.income_stmt
        if inc is None or getattr(inc, "empty", True):
            return None
        shares = info.get("sharesOutstanding")
        if not shares:
            return None
        return (ticker, {"inc": inc, "bs": tk.balance_sheet, "cf": tk.cash_flow,
                         "sector": info.get("sector") or "Unknown", "shares": float(shares), "fx": fx})
    except Exception:
        return None


def price_asof(series, d):
    s = series[series.index <= d]
    return float(s.iloc[-1]) if len(s) else None


def fwd_return(series, d, horizon_days=365):
    series = series.dropna()
    if len(series) == 0:
        return None
    target = d + pd.Timedelta(days=horizon_days)
    if series.index.max() < target - pd.Timedelta(days=10):
        return None  # no forward data (would otherwise truncate the horizon)
    p0, p1 = price_asof(series, d), price_asof(series, target)
    return (p1 / p0 - 1.0) if (p0 and p1) else None


def build_record(ticker, b, d, close):
    ci, cb, cc = pick_col(b["inc"], d), pick_col(b["bs"], d), pick_col(b["cf"], d)
    if ci is None or cb is None:
        return None
    if ticker not in close.columns:
        return None
    px = price_asof(close[ticker].dropna(), d)
    if not px:
        return None
    fx = b["fx"]
    raw = {}
    for n, l in fp.INCOME.items():
        raw[n] = cell(b["inc"], l, ci)
    for n, l in fp.BALANCE.items():
        raw[n] = cell(b["bs"], l, cb)
    for n, l in fp.CASHFLOW.items():
        raw[n] = cell(b["cf"], l, cc)
    ocf, capex = raw.get("operating_cash_flow"), raw.get("capex")
    fcf = ocf - abs(capex) if (ocf is not None and capex is not None) else None
    div, bb = raw.get("dividends_paid"), raw.get("buybacks")
    payout = None
    if div is not None or bb is not None:
        payout = (abs(div) if div is not None else 0.0) + (max(0.0, -bb) if bb is not None else 0.0)
    rec = {"ticker": ticker, "sector": b["sector"], "market_cap": b["shares"] * px}
    for k in fp.MONETARY:
        v = raw.get(k)
        if v is not None:
            rec[k] = v * fx
    if fcf is not None:
        rec["free_cash_flow"] = fcf * fx
    if payout is not None:
        rec["shareholder_payout"] = payout * fx
    return rec


def rank_via_ocaml(records, tag):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    for old in glob.glob(str(TMP_DIR / "factor_ranks_*.csv")):
        os.remove(old)  # avoid reading a prior rebalance's ranks if this call fails
    panel = TMP_DIR / f"panel_{tag}.json"
    with open(panel, "w") as f:
        json.dump(records, f)
    subprocess.run([str(EXE), "--panel", str(panel), "--output", str(TMP_DIR)],
                   cwd=str(PROJECT_ROOT), capture_output=True)
    csvs = sorted(glob.glob(str(TMP_DIR / "factor_ranks_*.csv")))
    if not csvs:
        return None
    df = pd.read_csv(csvs[-1])
    for c in ["value_pct", "quality_pct", "combined_pct"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.set_index("ticker")


def main():
    ap = argparse.ArgumentParser(description="Diagnostic point-in-time factor backtest")
    ap.add_argument("--tickers", default="")
    ap.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--rebal-month", type=int, default=4, help="annual rebalance month (default Apr)")
    ap.add_argument("--usd-only", action="store_true", default=True,
                    help="same-reporting-currency subset only (always on; avoids historical FX)")
    args = ap.parse_args()

    if not EXE.exists():
        print(f"OCaml ranker not built: {EXE}\n  run: dune build valuation/factor_rank/ocaml/", file=sys.stderr)
        sys.exit(1)

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = [t.strip() for t in Path(args.universe).read_text().splitlines() if t.strip()]
        if args.limit:
            tickers = tickers[: args.limit]

    print(f"fetching bundles for {len(tickers)} names (same-ccy subset)...", file=sys.stderr)
    bundles = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(fetch_bundle, tickers):
            if res:
                bundles[res[0]] = res[1]
    print(f"  {len(bundles)} usable bundles", file=sys.stderr)
    if not bundles:
        print("no usable bundles", file=sys.stderr); sys.exit(1)

    close = yf.download(list(bundles), period="5y", auto_adjust=True, progress=False)["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame()

    years = sorted({pd.Timestamp(c).year for b in bundles.values() for c in b["inc"].columns})
    rebal_dates = [pd.Timestamp(y, args.rebal_month, 1) for y in range(min(years) + 1, max(years) + 2)]
    rebal_dates = [d for d in rebal_dates if d <= close.index.max()]

    per_period = []   # (date, n, ic_value, ic_quality, ic_combined, spread, n_dropped)
    pooled = []       # rows of (combined_pct, value_pct, quality_pct, fwd_ret)
    for d in rebal_dates:
        records = [r for r in (build_record(t, b, d, close) for t, b in bundles.items()) if r]
        if len(records) < 10:
            continue
        ranks = rank_via_ocaml(records, d.strftime("%Y%m%d"))
        if ranks is None:
            continue
        rets, dropped = {}, 0
        for t in ranks.index:
            r = fwd_return(close[t].dropna(), d) if t in close.columns else None
            if r is None:
                dropped += 1
            else:
                rets[t] = r
        joined = ranks.join(pd.Series(rets, name="fwd_ret"), how="inner").dropna(subset=["fwd_ret"])
        if len(joined) < 10:
            continue
        ic = {c: spearmanr(joined[c], joined["fwd_ret"], nan_policy="omit").correlation
              for c in ["value_pct", "quality_pct", "combined_pct"]}
        spread = None
        cj = joined.dropna(subset=["combined_pct"])
        if len(cj) >= 10:
            q = pd.qcut(cj["combined_pct"], 5, labels=False, duplicates="drop")
            gm = cj.groupby(q)["fwd_ret"].mean()
            if len(gm) >= 2:
                spread = float(gm.iloc[-1] - gm.iloc[0])
        per_period.append((d.date(), len(joined), ic["value_pct"], ic["quality_pct"],
                           ic["combined_pct"], spread, dropped))
        for _, row in joined.iterrows():
            pooled.append((row.get("combined_pct"), row.get("value_pct"),
                           row.get("quality_pct"), row["fwd_ret"]))

    # ---- report ----
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"backtest_{date.today()}.txt"
    lines = []
    add = lines.append
    add("factor_rank backtest (diagnostic, point-in-time)")
    add(f"universe usable: {len(bundles)}   rebalances: {len(per_period)}   lag: {LAG_DAYS}d   horizon: 12m\n")
    add(f"{'date':12s} {'N':>4s} {'IC_val':>7s} {'IC_qual':>8s} {'IC_comb':>8s} {'Q5-Q1':>8s} {'dropped':>8s}")
    fmt = lambda x: "  n/a " if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:+.3f}"
    for (dt, n, iv, iq, ic, sp, dr) in per_period:
        add(f"{str(dt):12s} {n:>4d} {fmt(iv):>7s} {fmt(iq):>8s} {fmt(ic):>8s} "
            f"{('  n/a ' if sp is None else f'{sp:+.2%}'):>8s} {dr:>8d}")

    def pooled_ic(idx):
        vals = [p[idx] for p in per_period if p[idx] is not None and not math.isnan(p[idx])]
        if not vals:
            return "n/a"
        m = sum(vals) / len(vals)
        sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
        t = (m / sd * math.sqrt(len(vals))) if sd > 0 else float("nan")
        return f"mean {m:+.3f}  (per-period N={len(vals)}, t={t:+.2f}; tiny-N — diagnostic only)"

    add("\npooled rank IC (mean of per-period):")
    add(f"  value:    {pooled_ic(2)}")
    add(f"  quality:  {pooled_ic(3)}")
    add(f"  combined: {pooled_ic(4)}")

    if pooled:
        pdf = pd.DataFrame(pooled, columns=["combined_pct", "value_pct", "quality_pct", "fwd_ret"]).dropna(
            subset=["combined_pct"])
        if len(pdf) >= 10:
            q = pd.qcut(pdf["combined_pct"], 5, labels=False, duplicates="drop")
            gm = pdf.groupby(q)["fwd_ret"].mean()
            add("\npooled quintile mean forward return (by combined_pct, Q1=worst .. Q5=best):")
            for qi, v in gm.items():
                add(f"  Q{int(qi)+1}: {v:+.2%}")
            add("  (monotone increasing = the rank orders forward returns; trust ORDERING not levels)")

    add("\nCAVEATS: survivorship-biased (today's liquid names; absolute returns inflated — trust the")
    add("spread/IC ordering); ~5y statements => tiny N; as-reported statements (mild restatement look-")
    add("ahead); current-shares x historical price (shareholder-yield backtest indicative only); same-")
    add("reporting-currency subset (no historical FX).")

    report = "\n".join(lines)
    print(report)
    with open(out, "w") as f:
        f.write(report + "\n")
    print(f"\nwrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()

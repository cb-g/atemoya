#!/usr/bin/env python3
"""Assemble a universe-wide cross-sectional fundamentals panel (point-in-time snapshot).

Pulls annual financial statements + market data for a universe, FX-converts the
statement totals onto the trading-currency basis (FIX2 machinery) so every factor
downstream is a currency-neutral ratio, sign-normalizes the tricky cash-flow lines,
and writes ONE JSON array of raw trading-basis records to
``data/factor_panel_<date>.json``. The OCaml ranker (ocaml/bin/main.exe) reads that
file and computes the value/quality percentiles.

Statement-based (not the ``.info`` ratio fields) so the same fields can be
reconstructed historically by the backtest. Run via ``uv run``.
"""

import argparse
import json
import math
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[4]
MODULE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = MODULE_DIR / "data"
DEFAULT_UNIVERSE = PROJECT_ROOT / "pricing" / "liquidity" / "data" / "liquid_tickers.txt"

sys.path.insert(0, str(PROJECT_ROOT))
from lib.python.yfinance_utils import financial_fx_factor  # noqa: E402

# statement -> {panel field: [candidate row labels, first match wins]}
INCOME = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "ebit": ["EBIT", "Operating Income", "Operating Income Loss"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "gross_profit": ["Gross Profit"],
    "net_income": ["Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations"],
    "pretax_income": ["Pretax Income", "Pre Tax Income"],
    "tax_provision": ["Tax Provision", "Income Tax Expense Benefit"],
}
BALANCE = {
    "total_assets": ["Total Assets"],
    "total_equity": ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"],
    "total_debt": ["Total Debt", "Total Debt And Capital Lease Obligation"],
    "total_cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
}
CASHFLOW = {
    "operating_cash_flow": ["Operating Cash Flow", "Total Cash From Operating Activities",
                            "Cash Flow From Continuing Operating Activities"],
    "capex": ["Capital Expenditure", "Capital Expenditure Reported"],
    "dividends_paid": ["Cash Dividends Paid", "Common Stock Dividend Paid"],
    "buybacks": ["Repurchase Of Capital Stock", "Common Stock Payments"],
}
# monetary fields that must be FX-scaled (market_cap is already trading-currency)
MONETARY = ["revenue", "ebit", "ebitda", "gross_profit", "net_income", "pretax_income",
            "tax_provision", "total_assets", "total_equity", "total_debt", "total_cash",
            "operating_cash_flow"]


def get_row(df, labels):
    """Most-recent (column 0) value for the first matching row label, else None."""
    if df is None or getattr(df, "empty", True):
        return None
    for lab in labels:
        if lab in df.index:
            try:
                v = df.loc[lab].iloc[0]
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    return float(v)
            except Exception:
                continue
    return None


def fetch_one(ticker):
    info = inc = bs = cf = None
    for attempt in range(2):
        try:
            tk = yf.Ticker(ticker)
            info = tk.info
            if not info or not info.get("marketCap"):
                return None
            inc, bs, cf = tk.income_stmt, tk.balance_sheet, tk.cash_flow
            break
        except Exception:
            if attempt == 0:
                time.sleep(0.5 + random.random())
                continue
            return None

    fx, trading, financial, ok = financial_fx_factor(info)
    if financial != trading and not ok:
        return None  # cross-currency name we couldn't FX-convert: drop rather than mis-scale

    raw = {}
    for name, labels in INCOME.items():
        raw[name] = get_row(inc, labels)
    for name, labels in BALANCE.items():
        raw[name] = get_row(bs, labels)
    for name, labels in CASHFLOW.items():
        raw[name] = get_row(cf, labels)

    # sign-normalized derivations (positive = good)
    ocf, capex = raw.get("operating_cash_flow"), raw.get("capex")
    fcf = ocf - abs(capex) if (ocf is not None and capex is not None) else None
    div, bb = raw.get("dividends_paid"), raw.get("buybacks")
    payout = None
    if div is not None or bb is not None:
        payout = (abs(div) if div is not None else 0.0) + (max(0.0, -bb) if bb is not None else 0.0)

    rec = {
        "ticker": ticker,
        "sector": info.get("sector") or "Unknown",
        "currency": trading,
        "financial_currency": financial,
        "fx": fx,
        "fx_ok": ok,
        "market_cap": float(info["marketCap"]),
    }
    for k in MONETARY:
        v = raw.get(k)
        if v is not None:
            rec[k] = v * fx
    if fcf is not None:
        rec["free_cash_flow"] = fcf * fx
    if payout is not None:
        rec["shareholder_payout"] = payout * fx
    return rec


def load_universe(args):
    if args.tickers:
        return [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    path = Path(args.universe)
    tickers = [t.strip() for t in path.read_text().splitlines() if t.strip()]
    return tickers[: args.limit] if args.limit else tickers


def main():
    ap = argparse.ArgumentParser(description="Assemble the factor_rank fundamentals panel")
    ap.add_argument("--tickers", default="", help="comma-separated tickers (overrides --universe)")
    ap.add_argument("--universe", default=str(DEFAULT_UNIVERSE), help="ticker list file")
    ap.add_argument("--limit", type=int, default=0, help="cap number of tickers (0=all)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    tickers = load_universe(args)
    print(f"fetching {len(tickers)} tickers...", file=sys.stderr)
    records, done = [], 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for rec in ex.map(fetch_one, tickers):
            done += 1
            if rec:
                records.append(rec)
            if done % 25 == 0:
                print(f"  {done}/{len(tickers)}  ok={len(records)}", file=sys.stderr)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else DATA_DIR / f"factor_panel_{date.today()}.json"
    with open(out, "w") as f:
        json.dump(records, f)
    print(f"wrote {len(records)}/{len(tickers)} records -> {out}")


if __name__ == "__main__":
    main()

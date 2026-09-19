"""The point-in-time panel (17): every quarter-end from 2022-03-31 to 2026-06-30, valued
as of that date with only what was known then, and the forward 12-month return.

    uv run python/build_panel.py [--dates D1 D2 ...] [--binary PATH]

Per date: python/pit.py writes data/pit/<D>/ (facts filed by D, the split-corrected close,
cover-page shares, FRED rates and FX observed by D), the batch runs on it with --reference
data/pit/<D>/reference --today D into output/pit/<D>/, and output/pit/panel.jsonl gets one
row per (ticker, D) with status, fair value, price, margin of safety, signal, the three
implied readouts, anachronistic_inputs and the forward 12-month return from the same
split-corrected closes (null where D + 365 days is after the last close).
output/pit/panel_summary.txt is one descriptive table per date: the count Ok, the median
margin of safety and the signal counts. No statistic: overlapping forward returns on this
many names cannot support one, and that is a decision for a wider universe.
The companyfacts, submissions and FRED series are fetched once per name or series, not once
per date.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import fetch
import pit
import universe as universe_file
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UNIVERSE = REPO_ROOT / "reference" / "universe.json"
OUT = REPO_ROOT / "output" / "pit"
BINARY = REPO_ROOT / "_build" / "default" / "ocaml" / "bin" / "main.exe"
QUARTER_ENDS = [date(y, m, d) for y in range(2022, 2027) for m, d in ((3, 31), (6, 30), (9, 30), (12, 31))
                if date(2022, 3, 31) <= date(y, m, d) <= date(2026, 6, 30)]


def as_dict(value: object) -> dict[str, object]:
    return {str(k): v for k, v in value.items()} if isinstance(value, dict) else {}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType, reportUnknownMemberType]


def forward_return(history: pit.History, d: date, days: int = 365) -> float | None:
    """Close on the last trading day on or before D + days over the close at D, both as
    served (the same split basis), null when the end lies after the last close."""
    start = pit.price_on(history, d)
    end_day = d + timedelta(days=days)
    if start is None or end_day > max(history.closes):
        return None
    end = pit.price_on(history, end_day)
    if end is None:
        return None
    return end[1] / start[1] - 1.0


def run_batch(pit_dir: Path, d: date, binary: Path) -> Path:
    out = OUT / d.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(binary), str(pit_dir), "--reference", str(pit_dir / "reference"), "--today", d.isoformat(), "--out", str(out)],
                   check=True, capture_output=True, cwd=REPO_ROOT)
    return out / "valuations.jsonl"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--dates", nargs="*", type=date.fromisoformat, default=QUARTER_ENDS)
    parser.add_argument("--binary", type=Path, default=BINARY)
    args = parser.parse_args(argv)
    universe_path: Path = args.universe
    dates: list[date] = sorted(args.dates)
    binary: Path = args.binary
    if not binary.exists():
        print(f"{binary} not built: run dune build first", file=sys.stderr)
        return 2
    tickers = [e.ticker for e in universe_file.load(universe_path).tickers]
    sec = fetch.SecContext()
    histories: dict[str, pit.History] = {}
    quotes: dict[str, tuple[fetch.Quote | None, fetch.Profile | None]] = {}
    vendors: dict[str, list[pit.boundary.FiscalPeriod]] = {}
    for symbol in tickers:
        ticker = yf.Ticker(symbol)
        histories[symbol] = pit.History.fetch(symbol)
        quotes[symbol] = fetch._info(ticker, [])  # pyright: ignore[reportPrivateUsage]
        vendors[symbol] = fetch.vendor_periods(ticker, [])
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    summary: list[str] = ["point-in-time panel: one descriptive table per date, no statistic", ""]
    for d in dates:
        pit_dir = pit.run_date(d, tickers, histories=histories, quotes=quotes, sec=sec, vendors=vendors)
        valuations = run_batch(pit_dir, d, binary)
        day_rows: list[dict[str, object]] = []
        for line in valuations.read_text().splitlines():
            v = as_dict(json.loads(line))
            implied = as_dict(v.get("implied"))
            block = as_dict(v.get("point_in_time"))
            ticker = str(v["ticker"])
            day_rows.append({
                "ticker": ticker, "as_of": d.isoformat(), "status": v["status"], "fair_value": v["fair_value"], "price": v["price"],
                "margin_of_safety": v["margin_of_safety"], "signal": v["signal"], "failed_reason": v["failed_reason"],
                "implied_level": as_dict(implied.get("level")).get("value"),
                "implied_half_life_years": as_dict(implied.get("half_life_years")).get("value"),
                "implied_horizon_years": as_dict(implied.get("horizon_years")).get("value"),
                "meaningful_readout": implied.get("meaningful_readout"),
                "anachronistic_inputs": block.get("anachronistic_inputs", []),
                "price_date": block.get("price_date"),
                "forward_12m_return": forward_return(histories[ticker], d),
            })
        rows.extend(day_rows)
        ok = [r for r in day_rows if r["status"] == "Ok"]
        mos = [float(r["margin_of_safety"]) for r in ok if isinstance(r["margin_of_safety"], float)]
        signals = {s: sum(1 for r in ok if r["signal"] == s) for s in ("Buy", "Hold", "Sell")}
        summary.append(f"{d}: Ok {len(ok)} of {len(day_rows)}; median margin of safety {statistics.median(mos):+.3f}" if mos else f"{d}: Ok 0 of {len(day_rows)}")
        summary[-1] += f"; Buy {signals['Buy']}, Hold {signals['Hold']}, Sell {signals['Sell']}"
        print(summary[-1])
    (OUT / "panel.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (OUT / "panel_summary.txt").write_text("\n".join(summary) + "\n")
    print(f"{len(rows)} rows -> {OUT / 'panel.jsonl'}; {OUT / 'panel_summary.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

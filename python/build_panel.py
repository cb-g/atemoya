"""The point-in-time panel (17): every quarter-end from 2022-03-31 to 2026-06-30, valued
as of that date with only what was known then, and the forward 12-month return.

    uv run python/build_panel.py [--dates D1 D2 ...] [--binary PATH] [--options data/options]

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

With --options DIR (37) the batch runs with the store and --options-max-age 7, the
no-lookahead rule: at D the chain is the store's latest snapshot on or before D and no
older than seven calendar days, else the row carries the reason. Each row then gains
market_snapshot_date, horizon_years, p_below_anchor_path (the anchor path on D's own fair
value and rate), price_quantiles, implied_growth_quantiles (approximate), risk_neutral,
market_implied_reason, and probability_overpaid under the confirmed beliefs on D.
output/pit/market_summary.txt is one descriptive table per date: names with a block, the
median p_below_anchor_path, the median probability_overpaid, and the count of names where
the market's number is below 0.5 while the belief's is at 1.0, a disagreement stated, not
tested. Every market-implied number is risk-neutral: the market's risk pricing, not a
forecast.
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


OPTIONS_MAX_AGE_DAYS = 7  # the no-lookahead window (37): a snapshot older than this before D is not used


def run_batch(pit_dir: Path, d: date, binary: Path, options: Path | None = None, out_root: Path = OUT) -> Path:
    out = out_root / d.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    args = [str(binary), str(pit_dir), "--reference", str(pit_dir / "reference"), "--fetched", str(pit_dir / "reference"), "--today", d.isoformat(), "--out", str(out)]
    if options is not None:
        args += ["--options", str(options), "--options-max-age", str(OPTIONS_MAX_AGE_DAYS)]
    subprocess.run(args, check=True, capture_output=True, cwd=REPO_ROOT)
    return out / "valuations.jsonl"


def quantiles(entries: object) -> list[dict[str, object]] | None:
    """[{p, price}] or [{p, growth}] carried as filed; None where the record has none."""
    if not isinstance(entries, list):
        return None
    items: list[object] = list(entries)  # pyright: ignore[reportUnknownArgumentType]
    return [as_dict(e) for e in items]


def market_fields(v: dict[str, object]) -> dict[str, object]:
    """The panel row's market-implied columns (37) from a record valued with --options: the
    block's numbers, or null with the record's reason; nothing when the run had no store."""
    m = as_dict(v.get("market_implied"))
    belief = as_dict(v.get("belief"))
    if not m:
        return {"market_snapshot_date": None, "horizon_years": None, "p_below_anchor_path": None, "price_quantiles": None,
                "implied_growth_quantiles": None, "risk_neutral": True, "market_implied_reason": v.get("market_implied_reason"),
                "probability_overpaid": belief.get("probability_overpaid")}
    return {"market_snapshot_date": m.get("snapshot_date"), "horizon_years": m.get("horizon_years"), "p_below_anchor_path": m.get("p_below_anchor_path"),
            "price_quantiles": quantiles(m.get("price_quantiles")), "implied_growth_quantiles": quantiles(m.get("implied_growth_quantiles")),
            "risk_neutral": True, "market_implied_reason": None, "probability_overpaid": belief.get("probability_overpaid")}


def panel_row(v: dict[str, object], d: date, forward: float | None, *, with_options: bool) -> dict[str, object]:
    implied = as_dict(v.get("implied"))
    block = as_dict(v.get("point_in_time"))
    row: dict[str, object] = {
        "ticker": str(v["ticker"]), "as_of": d.isoformat(), "status": v["status"], "fair_value": v["fair_value"], "price": v["price"],
        "margin_of_safety": v["margin_of_safety"], "signal": v["signal"], "failed_reason": v["failed_reason"],
        "implied_level": as_dict(implied.get("level")).get("value"),
        "implied_half_life_years": as_dict(implied.get("half_life_years")).get("value"),
        "implied_horizon_years": as_dict(implied.get("horizon_years")).get("value"),
        "meaningful_readout": implied.get("meaningful_readout"),
        "anachronistic_inputs": block.get("anachronistic_inputs", []),
        "price_date": block.get("price_date"),
        "forward_12m_return": forward,
    }
    if with_options:
        row.update(market_fields(v))
    return row


def market_table(d: date, day_rows: list[dict[str, object]]) -> str:
    """One line per date (37): names with a block, the two medians, the disagreement count."""
    with_block = [r for r in day_rows if isinstance(r.get("p_below_anchor_path"), float)]
    if not with_block:
        reasons = sorted({str(r.get("market_implied_reason")) for r in day_rows if r.get("status") == "Ok" and r.get("market_implied_reason")})
        return f"{d}: no market-implied block on any name ({'; '.join(reasons) if reasons else 'no Ok record'})"
    market = [float(r["p_below_anchor_path"]) for r in with_block]  # pyright: ignore[reportArgumentType]
    both = [(float(r["p_below_anchor_path"]), float(r["probability_overpaid"])) for r in with_block if isinstance(r.get("probability_overpaid"), float)]  # pyright: ignore[reportArgumentType]
    disagree = sum(1 for m, b in both if m < 0.5 and b >= 1.0)
    belief_text = f"median probability_overpaid {statistics.median(b for _, b in both):.2f} on the {len(both)} with a belief" if both else "no name with both a block and a belief"
    return (f"{d}: {len(with_block)} names with a market-implied block; median p_below_anchor_path {statistics.median(market):.2f}; "
            f"{belief_text}; market below 0.5 while the belief is at 1.0 on {disagree} of {len(both)}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--dates", nargs="*", type=date.fromisoformat, default=QUARTER_ENDS)
    parser.add_argument("--binary", type=Path, default=BINARY)
    parser.add_argument("--options", type=Path, default=None, help="the options store (37); the batch runs with --options-max-age 7")
    args = parser.parse_args(argv)
    universe_path: Path = args.universe
    dates: list[date] = sorted(args.dates)
    binary: Path = args.binary
    options: Path | None = args.options
    if not binary.exists():
        print(f"{binary} not built: run dune build first", file=sys.stderr)
        return 2
    entries = universe_file.load(universe_path).tickers
    tickers = [e.ticker for e in entries]
    ciks = {e.ticker: e.cik for e in entries if e.cik}
    ratios = {e.ticker: e.adr_ratio for e in entries if e.adr_ratio is not None}
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
    market: list[str] = ["point-in-time market-implied (37): one descriptive table per date, no statistic; every number risk-neutral, the market's risk pricing and not a forecast", ""]
    for d in dates:
        pit_dir = pit.run_date(d, tickers, histories=histories, quotes=quotes, sec=sec, vendors=vendors, ciks=ciks, ratios=ratios)
        valuations = run_batch(pit_dir, d, binary, options)
        day_rows: list[dict[str, object]] = []
        for line in valuations.read_text().splitlines():
            v = as_dict(json.loads(line))
            day_rows.append(panel_row(v, d, forward_return(histories[str(v["ticker"])], d), with_options=options is not None))
        rows.extend(day_rows)
        if options is not None:
            market.append(market_table(d, day_rows))
            print(market[-1])
        ok = [r for r in day_rows if r["status"] == "Ok"]
        mos = [float(r["margin_of_safety"]) for r in ok if isinstance(r["margin_of_safety"], float)]
        signals = {s: sum(1 for r in ok if r["signal"] == s) for s in ("Buy", "Hold", "Sell")}
        summary.append(f"{d}: Ok {len(ok)} of {len(day_rows)}; median margin of safety {statistics.median(mos):+.3f}" if mos else f"{d}: Ok 0 of {len(day_rows)}")
        summary[-1] += f"; Buy {signals['Buy']}, Hold {signals['Hold']}, Sell {signals['Sell']}"
        print(summary[-1])
    (OUT / "panel.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (OUT / "panel_summary.txt").write_text("\n".join(summary) + "\n")
    if options is not None:
        (OUT / "market_summary.txt").write_text("\n".join(market) + "\n")
    print(f"{len(rows)} rows -> {OUT / 'panel.jsonl'}; {OUT / 'panel_summary.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

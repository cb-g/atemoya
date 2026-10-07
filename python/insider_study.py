"""The insider study (83): what routine and opportunistic trades preceded, on this tool's own names.

    uv run python/insider_study.py [--as-of 2026-09-30] [--first 2024-03-31] [--out output/insider_study]

The insiders block tells a routine trader from an opportunistic one by the rule in Cohen,
Malloy and Pomorski, "Decoding Inside Information", NBER Working Paper 16454, October 2010,
doi:10.3386/w16454, in whose data the trades of opportunistic insiders preceded the price,
sales as well as purchases, and the trades of routine insiders preceded nothing. Whether
that holds on the names this tool values, large companies in the years since 2024, is the
question here, and the downstream reader's reason for ignoring every sale today is the
reason to ask it.

For every universe name with an SEC filer, at every quarter-end from --first to the last
date before the holdout, the trailing ninety days of Form 4 are read from the cache (the
documents python/insider_history.py and the runs have put there; nothing is fetched here)
and every buyer and seller is classified from the three calendar years before the date's
year, exactly as the block does it. A name and date is then one row in one of four groups
on the selling side, an opportunistic seller present, routine sellers only, unclassified
sellers only, no seller, and in the same four on the buying side; and its excess return
over SPY at 63, 126 and 252 trading days after the date is read from the anchor study's
closes. Dates whose history the cache does not hold in full are left out and counted.

**Descriptive only**, under the anchor study's limits and three of its own: ten dates at
most and a single market; the three prior years must all be on disk, which they are for
dates from 2024; and a cell with fewer than MIN_CELL rows is a count alone. Nothing here
feeds a model, a belief or a signal."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import anchor_study as study
import fetch
import fetch_sec
import insiders
import universe as universe_file

OUT = study.REPO_ROOT / "output" / "insider_study"
WINDOW_DAYS = 90
MIN_CELL = study.MIN_CELL
HORIZONS = study.HORIZONS
BENCHMARK = study.BENCHMARK
GROUPS = ("opportunistic present", "routine only", "unclassified only", "none")


@dataclass
class Row:
    ticker: str
    as_of: str
    sellers: dict[str, int]          # kind -> distinct sellers in the window
    buyers: dict[str, int]
    excess: dict[str, float | None] = field(default_factory=lambda: {})


def group_of(counts: dict[str, int]) -> str:
    if counts.get(insiders.OPPORTUNISTIC, 0):
        return "opportunistic present"
    if counts.get(insiders.ROUTINE, 0):
        return "routine only"
    if counts.get(insiders.UNCLASSIFIED, 0):
        return "unclassified only"
    return "none"


def quarter_ends(first: date, last: date) -> list[date]:
    out: list[date] = []
    d = first
    while d <= last:
        out.append(d)
        year, month = (d.year + 1, 3) if d.month == 12 else (d.year, d.month + 3)
        d = date(year, month, 1) + timedelta(days=32)
        d = d.replace(day=1) - timedelta(days=1)
    return out


def classify_window(transactions: list[insiders.Transaction], history: insiders.History, as_of: date) -> tuple[dict[str, int], dict[str, int]]:
    """(sellers by kind, buyers by kind), distinct owners, over the window ending at as_of."""
    traders = insiders.classify(history.transactions, as_of)
    start = as_of - timedelta(days=WINDOW_DAYS)
    sellers: dict[str, set[str]] = {}
    buyers: dict[str, set[str]] = {}
    for t in insiders.deduplicate(transactions):
        if not start <= t.transaction_date <= as_of:
            continue
        kind, _why = insiders.trader_of(t, traders, None)
        (sellers if t.code == insiders.SALE else buyers).setdefault(kind, set()).add(insiders.owner_key(t))
    return {k: len(v) for k, v in sellers.items()}, {k: len(v) for k, v in buyers.items()}


def rows_for(ciks: dict[str, str], dates: list[date], user_agent: str) -> tuple[list[Row], int, int]:
    """One row per name and date whose window and history are on disk in full; with the
    count of name-dates left out for an incomplete history and for a window with a document
    the cache lacks."""
    rows: list[Row] = []
    incomplete = short = 0
    for ticker, cik in sorted(ciks.items()):
        index = fetch_sec.submissions(cik, user_agent)
        if index is None:
            continue
        for d in dates:
            history = fetch_sec.insider_history_cached(cik, index, d)
            if history is None or not history.complete:
                incomplete += 1
                continue
            filings, absent = fetch_sec.form4_filings_cached(cik, index, d - timedelta(days=WINDOW_DAYS + fetch_sec.INSIDER_FILING_LAG_DAYS), d)
            transactions, _excluded, _read, missing = fetch_sec.insiders_cached(cik, filings)
            if absent or missing:
                short += 1
                continue
            sellers, buyers = classify_window(transactions, history, d)
            rows.append(Row(ticker=ticker, as_of=d.isoformat(), sellers=sellers, buyers=buyers))
    return rows, incomplete, short


def attach_forward(rows: list[Row], as_of: date) -> None:
    bench = study.closes_of(BENCHMARK, as_of)
    by_ticker: dict[str, dict[date, float]] = {}
    for r in rows:
        if r.ticker not in by_ticker:
            by_ticker[r.ticker] = study.closes_of(r.ticker, as_of)
        closes = by_ticker[r.ticker]
        start = date.fromisoformat(r.as_of)
        for h in HORIZONS:
            own, end = study.forward_return(closes, start, h)
            b = None if own is None or end is None else study.benchmark_return(bench, start, end)
            r.excess[str(h)] = None if own is None or b is None else own - b


def cell(rows: list[Row], horizon: int) -> str:
    values = [x for r in rows if (x := r.excess.get(str(horizon))) is not None]
    if len(values) < MIN_CELL:
        return f"n={len(values)}"
    med, q1, q3 = study.quantiles(values)
    return f"n={len(values)} median {med:+.3f} (IQR {q1:+.3f} to {q3:+.3f}), positive {sum(1 for x in values if x > 0)}/{len(values)}"


def block(title: str, rows: list[Row], side: str) -> list[str]:
    lines = [title, "-" * len(title)]
    for name in GROUPS:
        mine = [r for r in rows if group_of(r.sellers if side == "sellers" else r.buyers) == name]
        if not mine:
            continue
        lines.append(f"{name}: {len(mine)} rows on {len({r.ticker for r in mine})} names")
        for h in HORIZONS:
            lines.append(f"  +{h:>3}d excess over {BENCHMARK}: {cell(mine, h)}")
    return lines


def report(rows: list[Row], incomplete: int, short: int, dates: list[date]) -> str:
    kinds: dict[str, int] = {}
    for r in rows:
        for k, n in r.sellers.items():
            kinds[k] = kinds.get(k, 0) + n
    total = sum(kinds.values())
    lines = [
        f"The insider study: {len(rows)} name-dates on {len({r.ticker for r in rows})} names over {len(dates)} quarter-ends, {dates[0]} to {dates[-1]}; "
        f"{incomplete} name-dates left out for a history the cache does not hold in full, {short} for a window with a document it lacks.",
        "Descriptive only, under the anchor study's limits: a cell under the small-cell floor is a count alone, no statistic is claimed, nothing feeds back. "
        f"A name-date's sellers and buyers are the distinct insiders with an open-market sale or purchase in the {WINDOW_DAYS} days to the date, each classified from the three calendar years before the date's year.",
        "After Cohen, Malloy and Pomorski, \"Decoding Inside Information\", NBER Working Paper 16454, October 2010, doi:10.3386/w16454.",
        "",
        f"sellers in the windows by kind: {', '.join(f'{k} {n} ({100 * n / total:.0f}%)' for k, n in sorted(kinds.items()))}" if total else "sellers in the windows by kind: none",
        "",
        *block("by the sellers in the window", rows, "sellers"), "",
        *block("by the buyers in the window", rows, "buyers"), "",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 9, 30), help="the anchor study's close cut: forward windows run to it")
    parser.add_argument("--first", type=date.fromisoformat, default=date(2024, 3, 31), help="the first quarter-end read")
    parser.add_argument("--universe", type=Path, default=study.REPO_ROOT / "reference" / "universe.json")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    out: Path = args.out
    holdout = study.load_holdout()
    last = date.fromisoformat(holdout.dates_after)
    dates = [d for d in quarter_ends(args.first, args.as_of) if d <= last]
    if not dates:
        print("no quarter-end between --first and the holdout's first date", file=sys.stderr)
        return 2
    sec = fetch.SecContext()
    ciks: dict[str, str] = {}
    for e in universe_file.load(args.universe).tickers:
        if e.ticker in holdout.names:
            continue
        cik, _source = fetch.cik_of(e.ticker, sec.tickers, e.cik)
        if cik is not None:
            ciks[e.ticker] = cik
    rows, incomplete, short = rows_for(ciks, dates, sec.user_agent)
    attach_forward(rows, args.as_of)
    text = report(rows, incomplete, short, dates)
    out.mkdir(parents=True, exist_ok=True)
    (out / "tables.txt").write_text(text)
    (out / "rows.jsonl").write_text("".join(json.dumps({"ticker": r.ticker, "as_of": r.as_of, "sellers": r.sellers, "buyers": r.buyers, "excess": r.excess}) + "\n" for r in rows))
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

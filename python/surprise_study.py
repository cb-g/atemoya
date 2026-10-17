"""What the surprise history preceded: does a name's last surprise say anything about its next,
or about the return that followed?

    uv run python/surprise_study.py [--holdout] [--out output/surprise_study]

The consensus tool keeps every universe name's past releases with the Street's final estimate
and the reported figure (82), and the record's summary reads the last eight and twelve as a
pattern. A pattern is only worth reading if it persists. Bordalo, Gennaioli, La Porta and
Shleifer, "Finance Without Exotic Risk", NBER Working Paper 33004, September 2024,
doi:10.3386/w33004, account for the returns of characteristic sorts by the forecast errors
that followed them under one required return for every firm, and find at the firm level that
a name's forecast-error rank a year earlier predicts its expectations-based return over the
next year positively (their Table C4, 0.033 standardised) and over three and five years
negatively; the whole firm-level prediction reaches an adjusted R-squared of three per cent.
Their errors are on fiscal-year earnings against the consensus of a year before; ours are the
quarterly release against the last consensus before it, which is what the tool holds, so this
is the question in the tool's own terms and not the paper's test.

What it does. Every release in the history with an estimate and a reported figure, the
estimate not zero, is a surprise in per cent of the estimate's magnitude, as the summary reads
it, with its sign; the held-out names and every release after the holdout's date are set aside
unless --holdout opens them, and the opening is said first. Then three questions. Persistence:
whether a beat is followed by a beat more often than a miss is (the transition rates against
the base rate); the pooled slope of the next surprise on the last, and on the mean of the
trailing four, both winsorised at the first and ninety-ninth percentile; and whether what
persists is the name or the quarter, the next surprise on the name's trailing mean over every
earlier release beside the last one. The return after: each release's excess over SPY from
the second close after the report date, so the move across the release itself is left out,
to 63, 126 and 252 trading days on, by fifths of the surprise within the calendar quarter of
the release, read from the anchor study's closes cache; the paper's sign is positive at a
year. And the arms of the margin sort: on the anchor panel's quarter-ends, the valued names
split into fifths on the margin of safety within the date, each fifth's mean surprise over the
releases in the twelve months after and its beat rate, against the fifth's excess return, which
asks whether the dear fifth's lead since 2022 was the Street being beaten more on that side.

What it is not. Street-adjusted EPS against the Street's own last estimate, on the vendor's
dated table, which carries about fifty releases a name; the closes reach back to 2020 and the
return questions are read on the releases since. Nothing feeds back: the surprise history
stays a readout and no model, belief or signal reads it; this says only how it should be read.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import numpy as np

import anchor_study as study
import consensus
import rule_betas as rbs
import rule_growth as rg

OUT = study.REPO_ROOT / "output" / "surprise_study"
HORIZONS = (63, 126, 252)
SKIP_DAYS = 2            # the forward return starts at the second close after the report date: the move across the release is left out
TRAILING = 4
FIFTHS = 5
BENCHMARK = "SPY"
Json = dict[str, object]


@dataclass
class Release:
    ticker: str
    report_date: str
    estimate: float
    reported: float

    @property
    def surprise(self) -> float:
        return (self.reported - self.estimate) / abs(self.estimate) * 100.0

    @property
    def sign(self) -> str:
        return consensus_outcome(self.estimate, self.reported)


def consensus_outcome(estimate: float, reported: float) -> str:
    return "beat" if reported > estimate else "miss" if reported < estimate else "meet"


@dataclass
class Row:
    release: Release
    previous: float | None = None                    # the name's last surprise before this release
    trailing: float | None = None                    # the mean of its TRAILING earlier surprises, all present
    history: float | None = None                     # the mean of every earlier surprise, at least TRAILING of them
    next: float | None = None
    next_sign: str | None = None
    excess: dict[int, float] = field(default_factory=lambda: {})
    quarter: str = ""
    fifth: int | None = None


def load_releases(history_dir: Path) -> list[Release]:
    out: list[Release] = []
    for path in sorted(history_dir.glob("*.json")):
        d = cast(Json, json.loads(path.read_text()))
        if d.get("status") != "ok":
            continue
        for r in cast(list[Json], d.get("releases", [])):
            est, rep = study.as_float(r.get("eps_estimate")), study.as_float(r.get("eps_reported"))
            if est is None or rep is None or est == 0:
                continue
            out.append(Release(ticker=str(d["ticker"]), report_date=str(r["report_date"]), estimate=est, reported=rep))
    return out


def set_aside(releases: list[Release], holdout: study.Holdout, *, opened: bool) -> tuple[list[Release], str]:
    held = [r for r in releases if holdout.holds(r.ticker, r.report_date)]
    if opened:
        return releases, f"HOLDOUT OPENED: {len(held)} held-out releases on {len({r.ticker for r in held})} names are in the tables below; record the opening in reference/holdout.json."
    return [r for r in releases if not holdout.holds(r.ticker, r.report_date)], \
        f"Holdout (reference/holdout.json): {len(held)} releases set aside, {len(holdout.names)} names and every release after {holdout.dates_after}; not read."


def rows_of(releases: list[Release]) -> list[Row]:
    """One row per release with what the name's history said before it and what came next."""
    out: list[Row] = []
    by_name: dict[str, list[Release]] = {}
    for r in releases:
        by_name.setdefault(r.ticker, []).append(r)
    for series in by_name.values():
        series.sort(key=lambda r: r.report_date)
        surprises = [r.surprise for r in series]
        for i, r in enumerate(series):
            row = Row(release=r, quarter=f"{r.report_date[:4]}Q{(int(r.report_date[5:7]) - 1) // 3 + 1}")
            if i >= 1:
                row.previous = surprises[i - 1]
            if i >= TRAILING:
                row.trailing = statistics.fmean(surprises[i - TRAILING:i])
                row.history = statistics.fmean(surprises[:i])
            if i + 1 < len(series):
                row.next, row.next_sign = surprises[i + 1], series[i + 1].sign
            out.append(row)
    return out


def load_closes(cache: Path, ticker: str) -> dict[date, float] | None:
    """The newest cached closes file for the name; None where there is none. Never fetches."""
    files = sorted(cache.glob(f"{ticker}-*.json"))
    if not files:
        return None
    stored = cast(dict[str, float], json.loads(files[-1].read_text()))
    return {date.fromisoformat(d): float(v) for d, v in stored.items()}


def attach_excess(rows: list[Row], cache: Path) -> int:
    """Each release's excess over the benchmark from the second close after the report date to each
    horizon; the count of rows with at least one."""
    spy = load_closes(cache, BENCHMARK)
    if spy is None:
        return 0
    spy_days = sorted(spy)
    closes: dict[str, dict[date, float] | None] = {}
    attached = 0
    for row in rows:
        t = row.release.ticker
        if t not in closes:
            closes[t] = load_closes(cache, t)
        own = closes[t]
        if own is None:
            continue
        reported = date.fromisoformat(row.release.report_date)
        i = study.start_index(spy_days, reported)
        if i is None or i + SKIP_DAYS >= len(spy_days):
            continue
        start = spy_days[i + SKIP_DAYS]
        for k in HORIZONS:
            r_own, end = study.forward_return(own, start, k)
            r_spy = study.benchmark_return(spy, start, end) if end is not None else None
            if r_own is not None and r_spy is not None:
                row.excess[k] = r_own - r_spy
        attached += bool(row.excess)
    return attached


def assign_fifths(rows: list[Row]) -> None:
    """Fifths of the surprise within the calendar quarter of the release, one the lowest."""
    for quarter in {r.quarter for r in rows}:
        group = sorted((r for r in rows if r.quarter == quarter), key=lambda r: r.release.surprise)
        if len(group) < FIFTHS * study.MIN_CELL:
            continue
        for i, r in enumerate(group):
            r.fifth = min(FIFTHS, i * FIFTHS // len(group) + 1)


def transition_block(rows: list[Row]) -> list[str]:
    lines = ["does a beat follow a beat: the next release's outcome by this one's", "-" * 100]
    nexts = [r for r in rows if r.next_sign is not None]
    base = sum(1 for r in nexts if r.next_sign == "beat")
    lines.append(f"  base rate: {base} beats in {len(nexts)} next releases, {100 * base / len(nexts):.1f}%" if nexts else "  no pairs")
    for sign in ("beat", "meet", "miss"):
        group = [r for r in nexts if r.release.sign == sign]
        if len(group) < study.MIN_CELL:
            lines.append(f"  after a {sign}: n={len(group)}")
            continue
        beats = sum(1 for r in group if r.next_sign == "beat")
        lines.append(f"  after a {sign}: {beats} beats in {len(group)}, {100 * beats / len(group):.1f}%")
    return lines


def persistence_block(rows: list[Row]) -> list[str]:
    lines = ["the next surprise on what the name's history said, pooled, both sides winsorised at the first and ninety-ninth percentile", "-" * 100]
    predictors: tuple[tuple[str, str], ...] = (("the last surprise", "previous"), (f"the mean of the trailing {TRAILING}", "trailing"), ("the mean of every earlier one", "history"))
    for label, attribute in predictors:
        pairs = [(cast(float, getattr(r, attribute)), r.next) for r in rows if getattr(r, attribute) is not None and r.next is not None]
        pairs, moved = rg.winsorise(pairs)
        f = rbs.forecast([x for x, _ in pairs], [y for _, y in pairs])
        rho = rbs.spearman(pairs)
        lines.append(f"  on {label:<30} " + (f"fewer than {rbs.MIN_PAIRS} pairs" if f is None else
                     f"{f.pairs} pairs ({moved} winsorised): slope {f.slope + 0.0:+.3f}, intercept {f.intercept + 0.0:+.2f}, R2 {100 * f.r2_fitted + 0.0:.1f}%, rank correlation {('n/a' if rho is None else f'{rho:+.2f}')}"))
    both = [r for r in rows if r.previous is not None and r.history is not None and r.next is not None]
    if len(both) >= rbs.MIN_PAIRS:
        xs = np.column_stack([np.ones(len(both)), [cast(float, r.previous) for r in both], [cast(float, r.history) for r in both]])
        ys = np.asarray([cast(float, r.next) for r in both])
        lo, hi = np.percentile(ys, (1, 99))
        ys = np.clip(ys, lo, hi)
        for j in (1, 2):
            lo, hi = np.percentile(xs[:, j], (1, 99))
            xs[:, j] = np.clip(xs[:, j], lo, hi)
        coef, *_ = np.linalg.lstsq(xs, ys, rcond=None)
        lines.append(f"  on both together, {len(both)} rows: the last surprise {coef[1] + 0.0:+.3f}, the name's mean of every earlier one {coef[2] + 0.0:+.3f}")
    lines.append("  the paper's firm-level prediction, on fiscal-year errors a year apart: the error rank a year earlier enters the next year's expectations-based return at +0.033 standardised, "
                 "three and five years at -0.047 and -0.084 (Table C4); the whole regression reaches an adjusted R2 of 3%")
    return lines


def drift_block(rows: list[Row]) -> list[str]:
    lines = [f"the excess return over {BENCHMARK} after the release, from the second close after the report date, by fifths of the surprise within the calendar quarter (median; positive share)",
             "-" * 100, f"  {'fifth':<8} {'rows':>5}  " + "  ".join(f"{k:>5} days: median (positive)" for k in HORIZONS)]
    assigned = [r for r in rows if r.fifth is not None and r.excess]
    for q in range(1, FIFTHS + 1):
        group = [r for r in assigned if r.fifth == q]
        cells: list[str] = []
        for k in HORIZONS:
            xs = [r.excess[k] for r in group if k in r.excess]
            cells.append(f"{'n=' + str(len(xs)):>27}" if len(xs) < study.MIN_CELL else
                         f"{statistics.median(xs) + 0.0:>+8.3f} ({sum(1 for x in xs if x > 0)}/{len(xs)})".rjust(27))
        lines.append(f"  {q:<8} {len(group):>5}  " + "  ".join(cells))
    top, bottom = [r for r in assigned if r.fifth == FIFTHS], [r for r in assigned if r.fifth == 1]
    gaps: list[str] = []
    for k in HORIZONS:
        a, b = [r.excess[k] for r in top if k in r.excess], [r.excess[k] for r in bottom if k in r.excess]
        gaps.append(f"{k} days {statistics.median(a) - statistics.median(b):+.3f}" if min(len(a), len(b)) >= study.MIN_CELL else f"{k} days n/a")
    lines.append("  highest less lowest fifth: " + ", ".join(gaps))
    quarters = sorted({r.quarter for r in assigned})
    lines.append(f"  {len(assigned)} releases in {len(quarters)} quarters" + (f", {quarters[0]} to {quarters[-1]}" if quarters else "") +
                 f"; a quarter under {FIFTHS * study.MIN_CELL} releases assigns no fifth; the paper's sign at a year is positive")
    return lines


def contemporaneous_block(rows: list[Row]) -> list[str]:
    """The excess return over the year after a release on the surprises of the releases inside that year, the paper's contemporaneous reading."""
    lines = ["contemporaneous, the paper's own reading: the excess return over the 252 days after a release on the mean surprise of the releases inside that window", "-" * 100]
    by_name: dict[str, list[Row]] = {}
    for r in rows:
        by_name.setdefault(r.release.ticker, []).append(r)
    pairs: list[tuple[float, float]] = []
    for series in by_name.values():
        series.sort(key=lambda r: r.release.report_date)
        for i, r in enumerate(series):
            if 252 not in r.excess:
                continue
            end = date.fromisoformat(r.release.report_date) + timedelta(days=365)
            inside = [s.release.surprise for s in series[i + 1:] if date.fromisoformat(s.release.report_date) <= end]
            if len(inside) >= 3:
                pairs.append((statistics.fmean(inside), r.excess[252]))
    pairs, moved = rg.winsorise(pairs)
    f = rbs.forecast([x for x, _ in pairs], [y for _, y in pairs])
    rho = rbs.spearman(pairs)
    lines.append(f"  " + (f"fewer than {rbs.MIN_PAIRS} pairs" if f is None else
                 f"{f.pairs} pairs ({moved} winsorised): slope {f.slope + 0.0:+.4f} per point of surprise, R2 {100 * f.r2_fitted + 0.0:.1f}%, rank correlation {('n/a' if rho is None else f'{rho:+.2f}')}"))
    lines.append("  the paper's: realised returns on the year's forecast errors reach a slope of 0.29 standardised and an R2 of 28% at the firm level (Table B7); a year's surprises moving its return is not in dispute, the question above is whether they are foreseeable")
    return lines


@dataclass
class ArmRow:
    ticker: str
    as_of: str
    margin: float
    excess: float | None
    fifth: int | None = None
    surprises: list[float] = field(default_factory=lambda: [])


def load_arms(panel: Path, rows: list[Row], holdout: study.Holdout, cache: Path, *, opened: bool) -> list[ArmRow]:
    """The anchor panel's valued rows with the surprises of the twelve months after each date and the
    row's twelve-month return less the benchmark's over the same window."""
    by_name: dict[str, list[Row]] = {}
    for r in rows:
        by_name.setdefault(r.release.ticker, []).append(r)
    spy = load_closes(cache, BENCHMARK) or {}
    out: list[ArmRow] = []
    for line in panel.read_text().splitlines():
        d = cast(Json, json.loads(line))
        ticker, as_of = str(d["ticker"]), str(d["as_of"])
        margin = study.as_float(d.get("margin_of_safety"))
        if d.get("status") != "Ok" or margin is None or (not opened and holdout.holds(ticker, as_of)):
            continue
        end = (date.fromisoformat(as_of) + timedelta(days=365)).isoformat()
        after = [r.release.surprise for r in by_name.get(ticker, []) if as_of < r.release.report_date <= end]
        forward = study.as_float(d.get("forward_12m_return"))
        benchmark, _ = study.forward_return(spy, date.fromisoformat(as_of), 252) if spy else (None, None)
        excess = forward - benchmark if forward is not None and benchmark is not None else None
        out.append(ArmRow(ticker=ticker, as_of=as_of, margin=margin, excess=excess, surprises=after))
    for as_of in {a.as_of for a in out}:
        group = sorted((a for a in out if a.as_of == as_of), key=lambda a: a.margin)
        if len(group) < FIFTHS * study.MIN_CELL:
            continue
        for i, a in enumerate(group):
            a.fifth = min(FIFTHS, i * FIFTHS // len(group) + 1)
    return out


def arms_block(arms: list[ArmRow]) -> list[str]:
    lines = ["the arms of the margin sort on the anchor panel: each fifth's surprises over the twelve months after the date (mean of the names' mean surprise; beat share), beside its excess return (median)",
             "-" * 100, f"  {'fifth':<8} {'rows':>5} {'with releases':>13}   {'mean surprise %':>15}   {'beats / releases':>16}   {'excess 12m':>10}"]
    for q in range(1, FIFTHS + 1):
        group = [a for a in arms if a.fifth == q]
        with_releases = [a for a in group if len(a.surprises) >= 3]
        if len(with_releases) < study.MIN_CELL:
            lines.append(f"  {q:<8} {len(group):>5} {len(with_releases):>13}   fewer than {study.MIN_CELL}")
            continue
        means = [statistics.fmean(a.surprises) for a in with_releases]
        lo, hi = np.percentile(means, (1, 99))
        beats = sum(1 for a in with_releases for s in a.surprises if s > 0)
        releases = sum(len(a.surprises) for a in with_releases)
        excess = [a.excess for a in group if a.excess is not None]
        lines.append(f"  {q:<8} {len(group):>5} {len(with_releases):>13}   {float(np.clip(means, lo, hi).mean()):>+15.1f}   {beats:>6} / {releases:<7}   "
                     + (f"{statistics.median(excess):>+10.3f}" if len(excess) >= study.MIN_CELL else f"{'n=' + str(len(excess)):>10}"))
    lines.append("  fifth 1 is the lowest margin of safety, the dearest names; the mean surprise is winsorised at the first and ninety-ninth percentile of the names' means; "
                 "the paper's account has the dear arm's lead come from its forecasts being beaten while the cheap arm's disappoint")
    return lines


def report(rows: list[Row], arms: list[ArmRow], holdout_line: str, attached: int) -> str:
    names = {r.release.ticker for r in rows}
    dates = sorted(r.release.report_date for r in rows)
    lines = [f"what the surprise history preceded: {len(rows)} releases on {len(names)} names, {dates[0]} to {dates[-1]}; {attached} with a forward return", holdout_line, ""]
    lines += transition_block(rows) + [""] + persistence_block(rows) + [""] + drift_block(rows) + [""] + contemporaneous_block(rows) + [""] + arms_block(arms)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--history", type=Path, default=consensus.DATA / "history")
    parser.add_argument("--closes", type=Path, default=study.CACHE)
    parser.add_argument("--panel", type=Path, default=study.PANEL)
    parser.add_argument("--holdout-file", type=Path, default=study.HOLDOUT)
    parser.add_argument("--holdout", action="store_true", help="read the held-out names and dates too, and say so")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    if not args.history.is_dir() or not any(args.history.glob("*.json")):
        print(f"no consensus history under {args.history}: run `uv run python/consensus.py --only history` first", file=sys.stderr)
        return 2
    if not args.closes.is_dir() or not any(args.closes.glob(f"{BENCHMARK}-*.json")):
        print(f"no closes cache under {args.closes}: run `uv run python/anchor_study.py` first", file=sys.stderr)
        return 2
    holdout = study.load_holdout(args.holdout_file)
    releases, holdout_line = set_aside(load_releases(args.history), holdout, opened=args.holdout)
    if not releases:
        print("no release with an estimate and a reported figure", file=sys.stderr)
        return 2
    rows = rows_of(releases)
    attached = attach_excess(rows, args.closes)
    assign_fifths(rows)
    arms = load_arms(args.panel, rows, holdout, args.closes, opened=args.holdout) if args.panel.exists() else []
    text = report(rows, arms, holdout_line, attached)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "tables.txt").write_text(text)
    with (args.out / "rows.jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps({"ticker": r.release.ticker, "report_date": r.release.report_date, "surprise_pct": r.release.surprise, "sign": r.release.sign,
                                 "previous": r.previous, "trailing": r.trailing, "history": r.history, "next": r.next, "fifth": r.fifth,
                                 "excess": {str(k): v for k, v in r.excess.items()}}) + "\n")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

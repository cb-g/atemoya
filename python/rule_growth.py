"""Growth on the rule panel: does the starting growth forecast the growth that followed?

    uv run python/rule_growth.py [--out output/rule_growth]

Every generic DCF record starts its projection from one of two estimates, the fundamental
one, the return on invested capital times the reinvestment rate, taken where after-tax
operating profit and net reinvestment are both positive, and otherwise the historical
revenue growth held to the return on capital; the growth shadow carries the higher of the
two beside the headline. The projection then fades the starting growth toward the terminal
rate, a quarter of the gap closing each year. None of that has been tested against what the
companies then did. Weber, "Cash Flow Duration and the Term Structure of Equity Returns",
NBER Working Paper 22520, August 2016, doi:10.3386/w22520, sorts US stocks on a duration
built from the same kind of projection and finds, in his Table 7, that the realised
five-year earnings growth of the sorted tenths ran from 7 to 31 per cent a year before the
sort and from 10 to 11 after it: the past growth that the sort read did not persist, and
the pooled year-on-year persistence he uses, 0.41 for the return on equity and 0.24 for
growth, says most of a year's growth is gone the next. This asks the same of the rule panel.

What it does. For every generic DCF record in the rule panel, each June 2013 to 2025, the
record's own estimates are read as the model computed them at the date: `fundamental`, the
return on capital times the reinvestment rate; `historical`, the revenue growth over the
record's fiscal periods; `headline`, the one the rule chose after the clamp; `shadow`, the
higher one; `path`, the growth the model projected over the horizon, the geometric mean of
its faded path; and `terminal`, the terminal rate alone, the forecast of knowing nothing
about the name. The outcome is what the filer then reported, read from the SEC frames the
broad panel cached: revenue, on the broad panel's chain of revenue elements, and operating
income, each at the record's base fiscal year end and at the end one, three and five years
after it, within FRAME_TOLERANCE_DAYS of the anniversary. Realised growth is the annualised
ratio where both figures are positive; a base or an end at or below zero is counted and left
out, since no rate describes it. Both sides are winsorised at the first and ninety-ninth
percentile of the pooled sample, as the paper does with its variables, and the count of
values moved is printed. Each estimate is then scored at forecasting realised revenue growth
and realised operating income growth the way the betas were: as it is, one less the squared
errors over the squared deviations from the realised mean and the root mean squared error,
and fitted, with the intercept, the slope and the fitted R-squared. The same is shown within
each growth source, since the question for the headline is whether the fundamental estimate
forecasts where the rule picked it. Then the paper's table: the records sorted into fifths
on the headline each June, with the mean headline, the mean historical growth, the mean
path over five years and the mean realised growth at one, three and five years; and the
persistence, the slope of each estimate on the same name's estimate the June before.

What it is not. Survivors only, twice: a name is in the panel while it is among the largest
five hundred, and its outcome is read while it still files; a filer bought or delisted inside
the horizon has no end figure and is counted among the unmatched. The frames carry the latest
figure reported for a period, so the base and the end are both as restated, and the record's
estimates were computed from what was filed by the date. A revenue element changed between
the base and the end is read from the chain in the same order on both; a filer that moved
between elements is read on the first that carries each year. Operating income before tax
stands for after-tax operating profit, whose growth it equals under a steady tax rate. The
five-year horizon reaches only the formations whose fifth year has been filed. Nothing here
moves a record or a parameter; the headline's rule is the user's decision of the third of
October, and this is the measure it was to be weighed on.
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
import broad_panel
import rule_betas as rbs
import rule_panel

OUT = study.REPO_ROOT / "output" / "rule_growth"
HORIZONS = (1, 3, 5)
FRAME_TOLERANCE_DAYS = 45       # a fiscal year end moves a week or two; a 53-week year a little more
WINSOR_PERCENTILES = (1.0, 99.0)
ESTIMATES = ("fundamental", "historical", "headline", "shadow", "path", "terminal")
OUTCOMES = ("revenue", "operating_income")
SOURCES = ("fundamental", "historical", "historical_capped_at_roic")
FIFTHS = 5
Json = dict[str, object]


@dataclass
class Record:
    ticker: str
    cik: int
    year: int
    base_end: str                       # the record's fiscal period end, the base of every growth below
    source: str
    fundamental: float | None
    historical: float | None
    headline: float
    shadow: float
    terminal: float
    growth_path: list[float]
    realised: dict[tuple[str, int], float] = field(default_factory=lambda: {})      # (outcome, horizon) -> annualised growth
    unmatched: dict[tuple[str, int], str] = field(default_factory=lambda: {})       # (outcome, horizon) -> why no growth

    def estimate(self, name: str, horizon: int) -> float | None:
        if name == "fundamental":
            return self.fundamental
        if name == "historical":
            return self.historical
        if name == "headline":
            return self.headline
        if name == "shadow":
            return self.shadow
        if name == "terminal":
            return self.terminal
        return path_mean(self.growth_path, horizon)


def path_mean(growth_path: list[float], horizon: int) -> float | None:
    """The annualised growth the projection carries over the first [horizon] years; None where the
    path is shorter than the horizon."""
    if horizon < 1 or len(growth_path) < horizon:
        return None
    product = 1.0
    for g in growth_path[:horizon]:
        product *= 1.0 + g
    return product ** (1.0 / horizon) - 1.0


def annualised(base: float, end: float, years: int) -> float | None:
    """The growth rate from [base] to [end] over [years]; None where either is at or below zero."""
    if base <= 0 or end <= 0 or years < 1:
        return None
    return (end / base) ** (1.0 / years) - 1.0


def load_frames(frames_dir: Path) -> dict[str, dict[tuple[int, str], float]]:
    """outcome -> (cik, fiscal year end) -> the figure, read from every cached annual frame on the
    broad panel's chain of elements, the first element carrying a filer-year winning."""
    out: dict[str, dict[tuple[int, str], float]] = {name: {} for name in OUTCOMES}
    for name in OUTCOMES:
        for tag in broad_panel.FLOWS[name]:
            for path in sorted(frames_dir.glob(f"us-gaap-{tag}-CY????.json")):
                for row in cast(list[Json], json.loads(path.read_text()).get("data", [])):
                    cik, end, val = row.get("cik"), row.get("end"), broad_panel.number(row)
                    if isinstance(cik, int) and isinstance(end, str) and val is not None:
                        out[name].setdefault((cik, end), val)
    return out


def nearest(series: dict[tuple[int, str], float], cik: int, around: date, tolerance: int = FRAME_TOLERANCE_DAYS) -> tuple[str, float] | None:
    """The filer's figure whose period end is closest to [around] within the tolerance."""
    best: tuple[int, str, float] | None = None
    for (c, end), val in series.items():
        if c != cik:
            continue
        gap = abs((date.fromisoformat(end) - around).days)
        if gap <= tolerance and (best is None or gap < best[0]):
            best = (gap, end, val)
    return None if best is None else (best[1], best[2])


def by_cik(series: dict[tuple[int, str], float]) -> dict[int, dict[str, float]]:
    out: dict[int, dict[str, float]] = {}
    for (cik, end), val in series.items():
        out.setdefault(cik, {})[end] = val
    return out


def realise(records: list[Record], frames: dict[str, dict[tuple[int, str], float]]) -> None:
    """Attach each record's realised growth at every horizon, or the reason there is none."""
    indexed = {name: by_cik(series) for name, series in frames.items()}
    for r in records:
        base_day = date.fromisoformat(r.base_end)
        for name in OUTCOMES:
            own = indexed[name].get(r.cik, {})
            series = {(r.cik, end): val for end, val in own.items()}
            base = nearest(series, r.cik, base_day, tolerance=7)
            for k in HORIZONS:
                if base is None:
                    r.unmatched[(name, k)] = "no base figure in the frames"
                    continue
                end = nearest(series, r.cik, base_day + timedelta(days=round(365.25 * k)))
                if end is None:
                    r.unmatched[(name, k)] = "no figure at the horizon"
                    continue
                g = annualised(base[1], end[1], k)
                if g is None:
                    r.unmatched[(name, k)] = "a figure at or below zero"
                else:
                    r.realised[(name, k)] = g


def load_records(panel_out: Path, universe_dir: Path) -> list[Record]:
    """Every generic DCF record of the rule panel with its growth fields as the model computed them."""
    out: list[Record] = []
    for day_dir in sorted(panel_out.iterdir()):
        path = day_dir / "valuations.jsonl"
        universe = universe_dir / f"{day_dir.name}.json"
        if not path.exists() or not universe.exists():
            continue
        ciks = {str(u["ticker"]): int(str(u["cik"])) for u in cast(list[Json], json.loads(universe.read_text()))}
        for line in path.read_text().splitlines():
            d = cast(Json, json.loads(line))
            inputs = d.get("inputs")
            shadow = cast(Json | None, d.get("growth_shadow"))
            if not (isinstance(inputs, list) and inputs and inputs[0] == "dcf" and shadow):
                continue
            x = cast(Json, inputs[1])
            ticker = str(d["ticker"])
            if ticker not in ciks:
                continue
            terminal = cast(Json, x["terminal_growth_rate"])["value"]
            out.append(Record(
                ticker=ticker, cik=ciks[ticker], year=int(day_dir.name[:4]), base_end=str(x["fiscal_period_end"]),
                source=str(x["growth_source"]), fundamental=study.as_float(x.get("g_fundamental")),
                historical=study.as_float(x.get("g_historical")), headline=float(cast(float, x["g0"])),
                shadow=float(cast(float, shadow["g0_shadow"])), terminal=float(cast(float, terminal)),
                growth_path=[float(g) for g in cast(list[float], x["growth_path"])]))
    return out


def winsorise(pairs: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], int]:
    """Both sides held to the pooled percentiles; the count of values moved."""
    if len(pairs) < rbs.MIN_PAIRS:
        return pairs, 0
    xs, ys = np.asarray([x for x, _ in pairs]), np.asarray([y for _, y in pairs])
    moved = 0
    out: list[np.ndarray] = []
    for column in (xs, ys):
        lo, hi = np.percentile(column, WINSOR_PERCENTILES)
        clipped = np.clip(column, lo, hi)
        moved += int((clipped != column).sum())
        out.append(clipped)
    return list(zip(out[0].tolist(), out[1].tolist())), moved


def pairs_of(records: list[Record], name: str, outcome: str, horizon: int) -> list[tuple[float, float]]:
    return [(e, r.realised[(outcome, horizon)]) for r in records
            if (outcome, horizon) in r.realised and (e := r.estimate(name, horizon)) is not None]


def forecast_block(records: list[Record], outcome: str, label: str) -> list[str]:
    lines = [f"which estimate forecasts realised {outcome.replace('_', ' ')} growth, {label}",
             "-" * 110]
    for k in HORIZONS:
        realised = [r.realised[(outcome, k)] for r in records if (outcome, k) in r.realised]
        if len(realised) < rbs.MIN_PAIRS:
            lines.append(f"  {k} year(s): {len(realised)} rows with a realised figure, fewer than {rbs.MIN_PAIRS}")
            continue
        sd = statistics.pstdev(realised)
        lines.append(f"  {k} year(s) ahead: {len(realised)} rows with a realised figure, mean {statistics.fmean(realised) + 0.0:+.3f}, standard deviation {sd:.3f}")
        lines.append(f"  {'estimate':<12} {'pairs':>6} {'moved':>6}   as it is: R2    rmse   fitted: intercept  slope   R2")
        for name in ESTIMATES:
            raw = pairs_of(records, name, outcome, k)
            pairs, moved = winsorise(raw)
            f = rbs.forecast([x for x, _ in pairs], [y for _, y in pairs])
            if f is None:
                lines.append(f"  {name:<12} {len(pairs):>6} {moved:>6}   fewer than {rbs.MIN_PAIRS} pairs or no variation")
                continue
            lines.append(f"  {name:<12} {f.pairs:>6} {moved:>6}   {100 * f.r2_as_is + 0.0:>13.1f}%  {f.rmse_as_is:.3f}   {f.intercept + 0.0:>17.3f}  {f.slope + 0.0:>5.2f}  {100 * f.r2_fitted + 0.0:.1f}%")
        lines.append("")
    return lines


def unmatched_block(records: list[Record]) -> list[str]:
    lines = ["rows without a realised figure, by reason", "-" * 110]
    for outcome in OUTCOMES:
        for k in HORIZONS:
            reasons: dict[str, int] = {}
            for r in records:
                why = r.unmatched.get((outcome, k))
                if why is not None:
                    reasons[why] = reasons.get(why, 0) + 1
            total = sum(1 for r in records if (outcome, k) in r.realised)
            text = ", ".join(f"{why} {n}" for why, n in sorted(reasons.items()))
            lines.append(f"  {outcome.replace('_', ' ')}, {k} year(s): {total} realised; {text or 'none unmatched'}")
    return lines


def median_of(values: list[float]) -> str:
    return f"{statistics.median(values) + 0.0:>+8.3f}" if len(values) >= study.MIN_CELL else f"{'n=' + str(len(values)):>8}"


def columns_of(rows: list[Record]) -> list[str]:
    """The medians a group of records reads and realised: headline, historical, fundamental, the
    five-year path, then realised revenue and operating income growth at each horizon."""
    read = [median_of([r.headline for r in rows]),
            median_of([h for r in rows if (h := r.historical) is not None]),
            median_of([f for r in rows if (f := r.fundamental) is not None]),
            median_of([p for r in rows if (p := path_mean(r.growth_path, 5)) is not None])]
    realised = [median_of([r.realised[(o, k)] for r in rows if (o, k) in r.realised]) for o in OUTCOMES for k in HORIZONS]
    return [" ".join(read), " ".join(realised[:3]), " ".join(realised[3:])]


HEADER = f"  {'group':<22} {'rows':>5}  {'headline':>8} {'histor.':>8} {'fundam.':>8} {'path 5y':>8} | revenue {'1y':>7} {'3y':>7} {'5y':>7} | op. income {'1y':>7} {'3y':>7} {'5y':>7}"


def fifths(records: list[Record]) -> dict[tuple[str, int], int]:
    """Each record's fifth on the headline within its June, one to five; a June under
    FIFTHS * MIN_CELL records assigns none."""
    assigned: dict[tuple[str, int], int] = {}
    for year in sorted({r.year for r in records}):
        rows = sorted((r for r in records if r.year == year), key=lambda r: r.headline)
        if len(rows) < FIFTHS * study.MIN_CELL:
            continue
        for i, r in enumerate(rows):
            assigned[(r.ticker, r.year)] = min(FIFTHS, i * FIFTHS // len(rows) + 1)
    return assigned


def fifths_block(records: list[Record]) -> list[str]:
    """The paper's table on the panel: fifths on the headline within each June, what each fifth read
    and what followed, medians; the paper reads the realised gap closing."""
    lines = ["fifths on the headline growth within the date: what the fifth read, and what followed (medians)", "-" * 110, HEADER]
    assigned = fifths(records)
    groups = {q: [r for r in records if assigned.get((r.ticker, r.year)) == q] for q in range(1, FIFTHS + 1)}
    for q, rows in groups.items():
        if rows:
            lines.append(f"  {'fifth ' + str(q):<22} {len(rows):>5}  {' | '.join(columns_of(rows))}")
    top, bottom = groups[FIFTHS], groups[1]
    if len(top) >= study.MIN_CELL and len(bottom) >= study.MIN_CELL:
        gap = [statistics.median([r.headline for r in top]) - statistics.median([r.headline for r in bottom])]
        for o in OUTCOMES:
            for k in HORIZONS:
                a, b = [r.realised[(o, k)] for r in top if (o, k) in r.realised], [r.realised[(o, k)] for r in bottom if (o, k) in r.realised]
                gap.append(statistics.median(a) - statistics.median(b) if min(len(a), len(b)) >= study.MIN_CELL else float("nan"))
        lines.append(f"  {'fifth 5 less fifth 1':<22} {'':>5}  {gap[0] + 0.0:>+8.3f} {'':>8} {'':>8} {'':>8} | "
                     + " ".join(f"{g + 0.0:>+8.3f}" for g in gap[1:4]) + " | " + " ".join(f"{g + 0.0:>+8.3f}" for g in gap[4:]))
    lines.append(f"  the fifths are formed within each June with at least {FIFTHS * study.MIN_CELL} rows; the fundamental and historical columns read the rows that carry each")
    return lines


def level_block(records: list[Record]) -> list[str]:
    """What each growth source read against what followed, medians; and the share of records whose
    realised five-year revenue growth was above the headline."""
    lines = ["the level: what the headline read by its source, and what followed (medians)", "-" * 110, HEADER]
    for source in SOURCES:
        rows = [r for r in records if r.source == source]
        if rows:
            lines.append(f"  {source.replace('_', ' '):<22} {len(rows):>5}  {' | '.join(columns_of(rows))}")
    lines.append(f"  {'every record':<22} {len(records):>5}  {' | '.join(columns_of(records))}")
    for source in SOURCES:
        rows = [r for r in records if r.source == source and ("revenue", 5) in r.realised]
        if len(rows) >= study.MIN_CELL:
            above = sum(1 for r in rows if r.realised[("revenue", 5)] > r.headline)
            lines.append(f"  realised five-year revenue growth above the headline: {above} of {len(rows)} records whose headline is the {source.replace('_', ' ')} estimate")
    return lines


def persistence_block(records: list[Record]) -> list[str]:
    """The slope of each estimate on the same name's a year earlier, the paper's pooled AR(1)."""
    lines = ["persistence: each estimate on the same name's estimate the June before (pooled slope)", "-" * 110]
    by_key = {(r.ticker, r.year): r for r in records}
    for name in ("fundamental", "historical", "headline"):
        pairs: list[tuple[float, float]] = []
        for r in records:
            prior = by_key.get((r.ticker, r.year - 1))
            if prior is None:
                continue
            a, b = prior.estimate(name, 1), r.estimate(name, 1)
            if a is not None and b is not None:
                pairs.append((a, b))
        pairs, moved = winsorise(pairs)
        f = rbs.forecast([x for x, _ in pairs], [y for _, y in pairs])
        lines.append(f"  {name:<12} " + (f"fewer than {rbs.MIN_PAIRS} pairs" if f is None else
                     f"{f.pairs} pairs ({moved} values winsorised), slope {f.slope + 0.0:.2f}, intercept {f.intercept + 0.0:+.3f}, R2 {100 * f.r2_fitted + 0.0:.1f}%"))
    for outcome in OUTCOMES:
        pairs = []
        for r in records:
            prior = by_key.get((r.ticker, r.year - 1))
            if prior is not None and (outcome, 1) in prior.realised and (outcome, 1) in r.realised:
                pairs.append((prior.realised[(outcome, 1)], r.realised[(outcome, 1)]))
        pairs, moved = winsorise(pairs)
        f = rbs.forecast([x for x, _ in pairs], [y for _, y in pairs])
        lines.append(f"  realised {outcome.replace('_', ' ')} growth, one year on the year before: "
                     + (f"fewer than {rbs.MIN_PAIRS} pairs" if f is None else
                        f"{f.pairs} pairs ({moved} values winsorised), slope {f.slope + 0.0:.2f}, intercept {f.intercept + 0.0:+.3f}, R2 {100 * f.r2_fitted + 0.0:.1f}%"))
    lines.append("  the historical estimate is a growth rate over the record's fiscal periods, so one June's shares most of its span with the next; "
                 "the realised rows are the year-on-year persistence the paper's 0.24 for growth measures (p.7); the model's fade keeps 0.78 of the gap to terminal each year")
    return lines


def report(records: list[Record]) -> str:
    lines = [f"growth on the rule panel: {len(records)} generic DCF records on {len({r.ticker for r in records})} names, "
             f"{min(r.year for r in records)} to {max(r.year for r in records)}; sources: "
             + ", ".join(f"{s} {sum(1 for r in records if r.source == s)}" for s in SOURCES), ""]
    lines += unmatched_block(records) + [""]
    for outcome in OUTCOMES:
        lines += forecast_block(records, outcome, "every record") + [""]
    for source in SOURCES:
        subset = [r for r in records if r.source == source]
        lines += forecast_block(subset, "revenue", f"records whose headline is the {source.replace('_', ' ')} estimate") + [""]
    lines += level_block(records) + [""] + fifths_block(records) + [""] + persistence_block(records)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel-out", type=Path, default=rule_panel.OUT)
    parser.add_argument("--universe-dir", type=Path, default=rule_panel.ROOT / "universe")
    parser.add_argument("--frames", type=Path, default=broad_panel.FRAMES)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    if not args.panel_out.is_dir() or not any(args.panel_out.glob("*/valuations.jsonl")):
        print(f"no rule panel records under {args.panel_out}: run `uv run python/rule_panel.py` first", file=sys.stderr)
        return 2
    if not args.frames.is_dir() or not any(args.frames.glob("us-gaap-OperatingIncomeLoss-CY*.json")):
        print(f"no SEC frames under {args.frames}: run `uv run python/broad_panel.py` first", file=sys.stderr)
        return 2
    records = load_records(args.panel_out, args.universe_dir)
    if not records:
        print("no generic DCF record in the rule panel", file=sys.stderr)
        return 2
    realise(records, load_frames(args.frames))
    args.out.mkdir(parents=True, exist_ok=True)
    text = report(records)
    (args.out / "tables.txt").write_text(text)
    with (args.out / "growth.jsonl").open("w") as fh:
        for r in records:
            fh.write(json.dumps({"ticker": r.ticker, "year": r.year, "base_end": r.base_end, "source": r.source, "fundamental": r.fundamental,
                                 "historical": r.historical, "headline": r.headline, "shadow": r.shadow, "terminal": r.terminal,
                                 "path": {k: path_mean(r.growth_path, k) for k in HORIZONS},
                                 "realised": {f"{o}_{k}": g for (o, k), g in r.realised.items()},
                                 "unmatched": {f"{o}_{k}": why for (o, k), why in r.unmatched.items()}}) + "\n")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

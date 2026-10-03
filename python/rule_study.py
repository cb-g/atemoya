"""The rule study: does the generic DCF sort returns on a universe chosen by a rule?

    uv run python/rule_study.py [--panel data/broad/rule/panel.jsonl] [--out output/rule_study]

Reads the rule panel (python/rule_panel.py: each June, the largest filers by market value
that the industry-code rule admits, valued by the real pipeline on what was filed by the
date) and puts the record's margin of safety beside the plain earnings yield on the same
rows, with the growth shadow's margin and the nine-signal score, for the formations before
SPLIT_YEAR and from it. The question is the anchor study's, asked where the names were not
chosen in hindsight: do the rows the anchor called cheapest do better over the next twelve
months than the rows it called dearest, and does it sort any better than earnings over
price does.

Tables: per date, the records valued and refused and the median margin of safety, since
the level of the anchor moves with interest rates while the cut is always within the date;
then for each measure and stretch the quintiles within the date (5 the highest value) on
the valued rows, the top less the bottom pooled and year by year; the rank correlation of
the margin of safety with the earnings yield within the date; and the refused rows beside
the valued ones.

**Descriptive only**, under the broad study's limits and three of its own: survivors only;
one industry-code rule standing in for a person's class, right about five times in six on
this tool's own names; a beta of one on every name and no vendor cross-check, so a filer
with no filed operating income is refused; and parameter tables of the 2026 vintage beside
point-in-time rates. Nothing here feeds a model, a belief or a signal."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import cast

import anchor_study as study
import baseline_study
import broad_study as broad
from broad_study import Row

PANEL = study.REPO_ROOT / "data" / "broad" / "rule" / "panel.jsonl"
OUT = study.REPO_ROOT / "output" / "rule_study"
SPLIT_YEAR = broad.SPLIT_YEAR
MEASURES = ("margin_of_safety", "shadow_margin", "earnings_yield", "f_score")
Json = dict[str, object]


def load(path: Path) -> tuple[list[Row], list[Row], list[str]]:
    """(valued rows, refused rows, one line per date). A row's values are the measures it carries."""
    valued: list[Row] = []
    refused: list[Row] = []
    by_date: dict[str, list[Json]] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            raw = cast(Json, json.loads(line))
            by_date.setdefault(str(raw["date"]), []).append(raw)
    lines: list[str] = []
    for d in sorted(by_date):
        ok = 0
        margins: list[float] = []
        for raw in by_date[d]:
            forward, spy = study.as_float(raw.get("forward_12m")), study.as_float(raw.get("spy_12m"))
            values = {m: v for m in MEASURES if (v := study.as_float(raw.get(m))) is not None}
            row = Row(ticker=str(raw["ticker"]), year=int(d[:4]), excess=None if forward is None or spy is None else forward - spy,
                      non_financial=True, values=values)
            if raw["status"] == "Ok":
                ok += 1
                valued.append(row)
                if "margin_of_safety" in values:
                    margins.append(values["margin_of_safety"])
            else:
                refused.append(row)
        lines.append(f"  {d}: {len(by_date[d])} records, {ok} valued" + (f", median margin of safety {statistics.median(margins):+.2f}" if margins else ""))
    return valued, refused, lines


def correlation(rows: list[Row]) -> str:
    per_year: list[float] = []
    for year in sorted({r.year for r in rows}):
        pairs = [(r.values["margin_of_safety"], r.values["earnings_yield"]) for r in rows
                 if r.year == year and "margin_of_safety" in r.values and "earnings_yield" in r.values]
        rho = baseline_study.spearman([a for a, _ in pairs], [b for _, b in pairs])
        if rho is not None:
            per_year.append(rho)
    if not per_year:
        return "  rank correlation of the margin of safety with the earnings yield: no date ranks enough rows"
    return (f"  rank correlation of the margin of safety with the earnings yield, within the date: median {statistics.median(per_year):+.2f} "
            f"over {len(per_year)} dates (lowest {min(per_year):+.2f}, highest {max(per_year):+.2f})")


def status_block(valued: list[Row], refused: list[Row], label: str) -> list[str]:
    lines = [f"valued against refused, {label}", "-" * (len(label) + 25)]
    for name, rows in (("valued", valued), ("refused", refused)):
        n, med, positive = broad.cell(rows)
        lines.append(f"  {name}: n={n}" + ("" if med is None else f" median excess {med:+.3f}, positive {positive}/{n}"))
    return lines


def report(valued: list[Row], refused: list[Row], per_date: list[str]) -> str:
    years = sorted({r.year for r in valued + refused})
    lines = [
        f"The rule study: {len(valued) + len(refused)} records on {len({r.ticker for r in valued + refused})} filers, formed each June {years[0]} to {years[-1]}; {len(valued)} valued by the generic DCF.",
        "Descriptive only. A universe chosen by size on the day and an industry-code rule, survivors only, a beta of one on every name, no vendor cross-check, parameter tables of the 2026 vintage. Excess is over SPY across the next twelve months. No statistic is claimed.",
        "",
        "by date", "-------", *per_date, "",
    ]
    def before(r: Row) -> bool:
        return r.year < SPLIT_YEAR

    def since(r: Row) -> bool:
        return r.year >= SPLIT_YEAR

    stretches = ((f"formations before {SPLIT_YEAR}", before), (f"formations from {SPLIT_YEAR}", since))
    for measure in MEASURES:
        for label, keep in stretches:
            lines += broad.measure_block([r for r in valued if keep(r) and r.excess is not None], measure, f"valued rows, {label}") + [""]
    for label, keep in stretches:
        lines += [correlation([r for r in valued if keep(r)]) + f" ({label})"]
    lines.append("")
    for label, keep in stretches:
        lines += status_block([r for r in valued if keep(r)], [r for r in refused if keep(r)], label) + [""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", type=Path, default=PANEL)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    panel: Path = args.panel
    out: Path = args.out
    if not panel.exists():
        print(f"{panel} not built: run python/rule_panel.py first", file=sys.stderr)
        return 2
    text = report(*load(panel))
    out.mkdir(parents=True, exist_ok=True)
    (out / "tables.txt").write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

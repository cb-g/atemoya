"""The owed measurements on the rule panel: the four-quarter shadow and the two capital readouts
against what followed.

    uv run python/rule_shadow.py                 # -> output/rule_shadow/tables.txt; seconds

Three blocks were built on 2026-10-18 beside the headline and measured against nothing: the
four-quarter shadow (the generic DCF on the last four filed quarters), capital intensity
(spending against depreciation, with the free cash flow at maintenance capex) and the goodwill
readout (the return on capital with and without acquired goodwill). This asks the rule panel,
the five hundred largest filers each June since 2013 chosen by rule, what each preceded,
descriptively and under the panel's rules: medians and the share positive, fifths cut within
the date, a rank correlation where a date carries enough rows, no statistic the sample cannot
carry, a cell under ten rows its count alone.

Four questions.

1. The four-quarter shadow against the headline. On the valued generic-DCF rows carrying
   both: the within-date rank correlation of the two margins; how often they disagree on
   direction; the cheapest fifth less the dearest of the twelve-month excess over SPY under
   each margin, pooled and before and from the split year; and whether the shadow
   anticipates the next annual headline: for a name valued at two consecutive Junes, whether
   the shadow's fair value at the first is nearer the headline's fair value at the second
   than the first headline was, in log distance. On June dates a December filer has one
   quarter filed, so the shadow here is a quarter ahead of the base, not three.
2. Capital intensity against what followed: the excess by fifths of capex over depreciation
   within the date, and at or above twice depreciation against below.
3. The margin at maintenance capex: the headline's margin with the free cash flow at
   maintenance capex in place of the base, scaled linearly (fair value times
   fcff_maintenance over fcff, a proxy since the DCF is linear in its base), sorted against
   the headline's margin on the same rows.
4. Goodwill: the fundamental growth estimate on the return without goodwill, the return
   times the headline's reinvestment rate, scored at forecasting realised revenue and
   operating income growth at one, three and five years beside the headline's estimate on the
   same rows, as the growth study scores estimates (R² as it is, root mean squared error, and
   the fitted line), from the SEC frames.

Nothing here feeds a model, a belief or a signal; a finding is weighed by a person."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import anchor_study as study
import broad_panel
import broad_study as broad
import panel_stats as ps
import rule_growth
import rule_panel

PANEL = rule_panel.ROOT / "panel.jsonl"
OUT = study.REPO_ROOT / "output" / "rule_shadow"
SPLIT_YEAR = broad.SPLIT_YEAR
FIFTHS = 5
Json = dict[str, object]


@dataclass
class Row:
    ticker: str
    year: int
    excess: float | None
    margin: float
    fair_value: float
    price: float
    four_quarter_margin: float | None = None
    four_quarter_fair_value: float | None = None
    capex_over_depreciation: float | None = None
    fcff_maintenance: float | None = None
    fcff: float | None = None
    roic_ex_goodwill: float | None = None
    reinvestment_rate: float | None = None
    nopat: float | None = None
    g_fundamental: float | None = None
    extra: dict[str, float] = field(default_factory=lambda: {})

    @property
    def maintenance_margin(self) -> float | None:
        if self.fcff_maintenance is None or self.fcff is None or self.fcff <= 0 or self.price <= 0:
            return None
        return self.fair_value * (self.fcff_maintenance / self.fcff) / self.price - 1.0

    @property
    def g_ex_goodwill(self) -> float | None:
        if self.roic_ex_goodwill is None or self.reinvestment_rate is None or self.nopat is None:
            return None
        if self.nopat <= 0 or self.reinvestment_rate <= 0:
            return None
        return self.roic_ex_goodwill * self.reinvestment_rate


def load_rows(panel: Path, panel_out: Path) -> list[Row]:
    """The valued generic-DCF rows with the panel's fields and, from the date's own
    valuations, the headline's base free cash flow, after-tax operating profit and
    reinvestment rate."""
    inputs: dict[tuple[str, str], Json] = {}
    for day_dir in sorted(panel_out.iterdir()) if panel_out.is_dir() else []:
        path = day_dir / "valuations.jsonl"
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            v = cast(Json, json.loads(line))
            model = v.get("inputs")
            if isinstance(model, list) and model and model[0] == "dcf":
                inputs[(str(v["ticker"]), day_dir.name)] = cast(Json, model[1])
    rows: list[Row] = []
    for line in panel.read_text().splitlines():
        if not line.strip():
            continue
        raw = cast(Json, json.loads(line))
        if raw.get("status") != "Ok":
            continue
        margin, fair_value, price = study.as_float(raw.get("margin_of_safety")), study.as_float(raw.get("fair_value")), study.as_float(raw.get("price"))
        if margin is None or fair_value is None or price is None:
            continue
        d = str(raw["date"])
        x = inputs.get((str(raw["ticker"]), d), {})
        if not x:
            continue  # not a generic DCF record
        forward, spy = study.as_float(raw.get("forward_12m")), study.as_float(raw.get("spy_12m"))
        rows.append(Row(
            ticker=str(raw["ticker"]), year=int(d[:4]), excess=None if forward is None or spy is None else forward - spy,
            margin=margin, fair_value=fair_value, price=price,
            four_quarter_margin=study.as_float(raw.get("four_quarter_margin")),
            four_quarter_fair_value=study.as_float(raw.get("four_quarter_fair_value")),
            capex_over_depreciation=study.as_float(raw.get("capex_over_depreciation")),
            fcff_maintenance=study.as_float(raw.get("fcff_maintenance")),
            fcff=study.as_float(x.get("fcff")), nopat=study.as_float(x.get("nopat")),
            reinvestment_rate=study.as_float(x.get("reinvestment_rate")), g_fundamental=study.as_float(x.get("g_fundamental")),
            roic_ex_goodwill=study.as_float(raw.get("roic_ex_goodwill"))))
    return rows


def fifths_within_year(pairs: list[tuple[Row, float]]) -> dict[tuple[str, int], int]:
    """1 the lowest value to 5 the highest, cut within the year; a year under FIFTHS rows is skipped."""
    out: dict[tuple[str, int], int] = {}
    for year in sorted({r.year for r, _ in pairs}):
        own = sorted(((v, r) for r, v in pairs if r.year == year), key=lambda t: t[0])
        if len(own) < FIFTHS:
            continue
        for i, (_, r) in enumerate(own):
            out[(r.ticker, r.year)] = 1 + (i * FIFTHS) // len(own)
    return out


def cell(rows: list[Row]) -> str:
    xs = [r.excess for r in rows if r.excess is not None]
    if len(xs) < study.MIN_CELL:
        return f"n={len(xs)}"
    return f"n={len(xs)} median {statistics.median(xs):+.3f} positive {sum(1 for x in xs if x > 0)}/{len(xs)}"


def spread(label: str, rows: list[Row], fifths: dict[tuple[str, int], int], *, cheap_is_high: bool = True) -> str:
    """The top fifth's median excess less the bottom's, pooled, before and from the split year."""
    def part(sub: list[Row]) -> str:
        hi = [r.excess for r in sub if fifths.get((r.ticker, r.year)) == FIFTHS and r.excess is not None]
        lo = [r.excess for r in sub if fifths.get((r.ticker, r.year)) == 1 and r.excess is not None]
        if len(hi) < study.MIN_CELL or len(lo) < study.MIN_CELL:
            return f"n={len(hi)}/{len(lo)}"
        top, bottom = (hi, lo) if cheap_is_high else (lo, hi)
        return f"{statistics.median(top) - statistics.median(bottom):+.3f} (n={len(top)}/{len(bottom)})"
    before = [r for r in rows if r.year < SPLIT_YEAR]
    after = [r for r in rows if r.year >= SPLIT_YEAR]
    return f"  {label:<34} pooled {part(rows):>22}   before {SPLIT_YEAR} {part(before):>22}   from {SPLIT_YEAR} {part(after):>22}"


def rank_within_year(rows: list[Row], a: str, b: str) -> str:
    per_year: list[float] = []
    for year in sorted({r.year for r in rows}):
        pairs = [(float(getattr(r, a)), float(getattr(r, b))) for r in rows if r.year == year and getattr(r, a) is not None and getattr(r, b) is not None]
        rho = ps.spearman(pairs, min_pairs=study.MIN_CELL)
        if rho is not None:
            per_year.append(rho)
    if not per_year:
        return "  rank correlation within the date: no date ranks enough rows"
    return f"  rank correlation of {a} with {b}, within the date: median {statistics.median(per_year):+.2f} over {len(per_year)} dates (lowest {min(per_year):+.2f}, highest {max(per_year):+.2f})"


def four_quarter_section(rows: list[Row]) -> list[str]:
    both = [r for r in rows if r.four_quarter_margin is not None]
    title = f"1. the four-quarter shadow against the headline: {len(both)} of {len(rows)} valued generic-DCF rows carry one, on {len({r.ticker for r in both})} names"
    lines = [title, "-" * len(title)]
    if not both:
        return lines + ["  none: the panel was built before the shadow existed"]
    lines.append(rank_within_year(both, "four_quarter_margin", "margin"))
    disagree = [r for r in both if (cast(float, r.four_quarter_margin) > 0) != (r.margin > 0)]
    lines.append(f"  rows where the two margins disagree on direction: {len(disagree)} of {len(both)}")
    gaps = [cast(float, r.four_quarter_margin) - r.margin for r in both]
    lines.append(f"  the shadow's margin less the headline's: median {statistics.median(gaps):+.3f}, the shadow higher on {sum(1 for g in gaps if g > 0)} of {len(gaps)}")
    lines.append("  the cheapest fifth's median excess less the dearest's, fifths within the date on these rows:")
    lines.append(spread("by the headline's margin", both, fifths_within_year([(r, r.margin) for r in both])))
    lines.append(spread("by the shadow's margin", both, fifths_within_year([(r, cast(float, r.four_quarter_margin)) for r in both])))
    # anticipation: the next June's headline against this June's shadow and headline
    by_key = {(r.ticker, r.year): r for r in rows}
    nearer = 0
    gap_shadow: list[float] = []
    gap_head: list[float] = []
    for r in both:
        nxt = by_key.get((r.ticker, r.year + 1))
        fv_shadow = r.four_quarter_fair_value
        if nxt is None or fv_shadow is None or fv_shadow <= 0 or nxt.fair_value <= 0 or r.fair_value <= 0:
            continue
        gs, gh = abs(math.log(fv_shadow / nxt.fair_value)), abs(math.log(r.fair_value / nxt.fair_value))
        gap_shadow.append(gs)
        gap_head.append(gh)
        nearer += gs < gh
    if len(gap_shadow) >= study.MIN_CELL:
        lines.append(f"  against the next June's headline fair value, on {len(gap_shadow)} name-years valued at both: the shadow nearer on {nearer} ({100 * nearer / len(gap_shadow):.0f}%); "
                     f"median log distance shadow {statistics.median(gap_shadow):.3f}, headline {statistics.median(gap_head):.3f}")
    else:
        lines.append(f"  against the next June's headline: {len(gap_shadow)} name-years valued at both, fewer than {study.MIN_CELL}")
    return lines


def intensity_section(rows: list[Row]) -> list[str]:
    with_ratio = [r for r in rows if r.capex_over_depreciation is not None]
    title = f"2. capital intensity against what followed: {len(with_ratio)} of {len(rows)} valued generic-DCF rows carry capex over depreciation"
    lines = [title, "-" * len(title)]
    if not with_ratio:
        return lines + ["  none: the panel was built before the readout existed"]
    ratios = [cast(float, r.capex_over_depreciation) for r in with_ratio]
    lines.append(f"  capex over depreciation: median {statistics.median(ratios):.2f}, at or above two on {sum(1 for x in ratios if x >= 2)} rows")
    f = fifths_within_year([(r, cast(float, r.capex_over_depreciation)) for r in with_ratio])
    lines.append("  the twelve-month excess over SPY by fifths of capex over depreciation within the date, 1 the lightest spenders and 5 the heaviest:")
    for q in range(1, FIFTHS + 1):
        lines.append(f"    fifth {q}: {cell([r for r in with_ratio if f.get((r.ticker, r.year)) == q])}")
    lines.append(spread("heaviest fifth less lightest", with_ratio, f))
    heavy = [r for r in with_ratio if cast(float, r.capex_over_depreciation) >= 2]
    light = [r for r in with_ratio if cast(float, r.capex_over_depreciation) < 2]
    lines.append(f"  at or above twice depreciation: {cell(heavy)}; below: {cell(light)}")
    return lines


def maintenance_section(rows: list[Row]) -> list[str]:
    both = [r for r in rows if r.maintenance_margin is not None]
    title = f"3. the margin at maintenance capex against the headline's: {len(both)} of {len(rows)} rows carry the figure"
    lines = [title, "-" * len(title)]
    if not both:
        return lines + ["  none: the panel was built before the readout existed"]
    diffs = [cast(float, r.maintenance_margin) - r.margin for r in both]
    lines.append(f"  the maintenance margin less the headline's (a linear proxy: fair value scaled by fcff_maintenance over fcff): median {statistics.median(diffs):+.3f}, positive on {sum(1 for d in diffs if d > 0)} of {len(diffs)}")
    per_year: list[float] = []
    for year in sorted({r.year for r in both}):
        pairs = [(cast(float, r.maintenance_margin), r.margin) for r in both if r.year == year]
        rho = ps.spearman(pairs, min_pairs=study.MIN_CELL)
        if rho is not None:
            per_year.append(rho)
    if per_year:
        lines.append(f"  rank correlation with the headline's margin, within the date: median {statistics.median(per_year):+.2f} over {len(per_year)} dates (lowest {min(per_year):+.2f})")
    lines.append("  the cheapest fifth's median excess less the dearest's, fifths within the date on these rows:")
    lines.append(spread("by the headline's margin", both, fifths_within_year([(r, r.margin) for r in both])))
    lines.append(spread("by the maintenance margin", both, fifths_within_year([(r, cast(float, r.maintenance_margin)) for r in both])))
    return lines


def goodwill_section(rows: list[Row], frames_dir: Path, universe_dir: Path) -> list[str]:
    with_ex = [r for r in rows if r.g_ex_goodwill is not None and r.g_fundamental is not None]
    title = f"4. the fundamental growth estimate on the return without goodwill: {len(with_ex)} of {len(rows)} rows carry both returns with a positive reinvestment"
    lines = [title, "-" * len(title)]
    if not with_ex:
        return lines + ["  none: the panel was built before the readout existed"]
    diffs = [cast(float, r.g_ex_goodwill) - cast(float, r.g_fundamental) for r in with_ex]
    lines.append(f"  the estimate without goodwill less the headline's: median {statistics.median(diffs):+.3f}, higher on {sum(1 for d in diffs if d > 0)} of {len(diffs)}")
    if not frames_dir.is_dir() or not any(frames_dir.glob("us-gaap-OperatingIncomeLoss-CY*.json")):
        return lines + [f"  no SEC frames under {frames_dir}: run `uv run python/broad_panel.py` first; the forecast is not scored"]
    ciks: dict[tuple[str, int], int] = {}
    for path in sorted(universe_dir.glob("????-??-??.json")):
        year = int(path.name[:4])
        for u in cast(list[Json], json.loads(path.read_text())):
            ciks[(str(u["ticker"]), year)] = int(str(u["cik"]))
    # realised growth through the growth study's own machinery, on records that carry a base period
    base_ends: dict[tuple[str, int], str] = {}
    for day_dir in sorted(rule_panel.OUT.iterdir()) if rule_panel.OUT.is_dir() else []:
        path = day_dir / "valuations.jsonl"
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            v = cast(Json, json.loads(line))
            model = v.get("inputs")
            if isinstance(model, list) and model and model[0] == "dcf":
                base_ends[(str(v["ticker"]), int(day_dir.name[:4]))] = str(cast(Json, model[1])["fiscal_period_end"])
    records: list[rule_growth.Record] = []
    ex_of: dict[tuple[str, int], float] = {}
    for r in with_ex:
        key = (r.ticker, r.year)
        if key not in ciks or key not in base_ends:
            continue
        records.append(rule_growth.Record(ticker=r.ticker, cik=ciks[key], year=r.year, base_end=base_ends[key], source="fundamental",
                                          fundamental=r.g_fundamental, historical=None, headline=cast(float, r.g_fundamental), shadow=cast(float, r.g_ex_goodwill),
                                          terminal=0.0, growth_path=[]))
        ex_of[key] = cast(float, r.g_ex_goodwill)
    rule_growth.realise(records, rule_growth.load_frames(frames_dir))
    for outcome in rule_growth.OUTCOMES:
        lines.append(f"  which estimate forecasts realised {outcome.replace('_', ' ')} growth, on the same rows:")
        for k in rule_growth.HORIZONS:
            matched = [rec for rec in records if (outcome, k) in rec.realised and rec.fundamental is not None]
            if len(matched) < ps.MIN_PAIRS:
                lines.append(f"    {k} year(s): {len(matched)} rows with a realised figure, fewer than {ps.MIN_PAIRS}")
                continue
            lines.append(f"    {k} year(s) ahead, {len(matched)} rows:  {'estimate':<16} {'pairs':>6} {'moved':>6}   as it is: R2    rmse   fitted: intercept  slope   R2")
            estimates: dict[str, list[tuple[float, float]]] = {
                "with goodwill": [(cast(float, rec.fundamental), rec.realised[(outcome, k)]) for rec in matched],
                "without goodwill": [(rec.shadow, rec.realised[(outcome, k)]) for rec in matched],
            }
            for name, raw in estimates.items():
                pairs, moved = ps.winsorise_pairs(raw)
                f = ps.forecast([x for x, _ in pairs], [y for _, y in pairs])
                if f is None:
                    lines.append(f"      {name:<16} {len(pairs):>6} {moved:>6}   fewer than {ps.MIN_PAIRS} pairs or no variation")
                    continue
                lines.append(f"      {name:<16} {f.pairs:>6} {moved:>6}   {100 * f.r2_as_is + 0.0:>13.1f}%  {f.rmse_as_is:.3f}   {f.intercept + 0.0:>17.3f}  {f.slope + 0.0:>5.2f}  {100 * f.r2_fitted + 0.0:.1f}%")
    return lines


def report(rows: list[Row], frames_dir: Path, universe_dir: Path) -> str:
    years = sorted({r.year for r in rows})
    head = [f"The owed measurements on the rule panel: {len(rows)} valued generic-DCF rows on {len({r.ticker for r in rows})} names, {len(years)} Junes {years[0] if years else '-'} to {years[-1] if years else '-'}.",
            "Descriptive only, under the panel's rules: the twelve-month excess over SPY, fifths within the date, a cell under ten rows its count alone; the split year is the broad study's.",
            ""]
    body = four_quarter_section(rows) + [""] + intensity_section(rows) + [""] + maintenance_section(rows) + [""] + goodwill_section(rows, frames_dir, universe_dir)
    return "\n".join(head + body) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", type=Path, default=PANEL)
    parser.add_argument("--panel-out", type=Path, default=rule_panel.OUT)
    parser.add_argument("--universe-dir", type=Path, default=rule_panel.ROOT / "universe")
    parser.add_argument("--frames", type=Path, default=broad_panel.FRAMES)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    if not args.panel.exists():
        print(f"no rule panel at {args.panel}: run `uv run python/rule_panel.py` first", file=sys.stderr)
        return 2
    rows = load_rows(args.panel, args.panel_out)
    if not rows:
        print("no valued generic-DCF rows on the panel", file=sys.stderr)
        return 2
    text = report(rows, args.frames, args.universe_dir)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "tables.txt").write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
